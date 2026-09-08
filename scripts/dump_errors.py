"""Uma linha por turno do gabarito, para a proxima rodada devolver dado em vez
de palpite.

Le o analysis.json de uma rodada do benchmark e escreve um CSV com os 255 turnos:
esperado, emitido, se acertou na coluna literal e na coluna por identidade, a
cena, a familia do erro e o texto. Quem analisa sem GPU so consegue agir sobre a
causa se enxergar turno a turno; a cegueira por turno foi o que deixou uma meta
aritmeticamente impossivel de pe por semanas.

Uso:
    python scripts/dump_errors.py --analysis output/<pasta>/analysis.json \
        --gold benchmarks/part01_gold.yaml --output output/<pasta>/erros.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from audiobook_voice_enhancer.benchmark import _fold, _role_key, evaluate, load_gold


def family(expected: str, predicted: str | None, anonymous: set[str]) -> str:
    """Familia do erro: agrupa o que se conserta junto."""
    if predicted is None:
        return "abstencao"
    if predicted == "NAO DETECTADA":
        return "nao_detectada"
    if _role_key(predicted) == _role_key(expected):
        return "so_o_rotulo_difere"
    if expected in anonymous and predicted in anonymous:
        return "anonimo_trocado_por_anonimo"
    if expected in anonymous:
        return "anonimo_virou_nomeado"
    if predicted in anonymous:
        return "nomeado_virou_anonimo"
    return "nomeado_trocado_por_nomeado"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--gold", type=Path, default=Path("benchmarks/part01_gold.yaml"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    gold = load_gold(args.gold)
    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    metrics = analysis.get("benchmark") or evaluate(gold, analysis)
    anonymous = {str(label) for label in (gold.get("anonymous_role_labels") or [])}
    klass = lambda expected: "figurante" if expected in anonymous else "dublavel"

    scene_of = {}
    for chapter in analysis.get("files", []):
        for item in chapter.get("dialogues", []):
            if item.get("book_paragraph_id") is not None:
                scene_of[int(item["book_paragraph_id"])] = item.get("scene_id")

    # Turnos que so a coluna por identidade salva: papel anonimo escrito com
    # outras palavras. Ficam visiveis para auditoria, nunca somados em silencio.
    identity_saved = {str(item["id"]) for item in metrics.get("literal_only_misses", [])}

    rows = []
    for item in metrics["wrong_or_unassigned"]:
        saved = str(item["id"]) in identity_saved
        rows.append({
            "paragrafo": item["paragraph"], "cena": scene_of.get(item["paragraph"], ""),
            "id": item["id"], "esperado": item["expected"],
            "emitido": item["predicted"] or "", "acertou_literal": 0,
            "acertou_identidade": int(saved), "sugestao_da_ia": item.get("suggestion") or "",
            "classe": klass(item["expected"]),
            "familia": "so_o_rotulo_difere" if saved
                       else family(item["expected"], item["predicted"], anonymous),
            "texto": (item.get("text") or "").replace("\n", " ")[:200],
        })
    for item in metrics["missing_spoken"]:
        rows.append({
            "paragrafo": item["book_paragraph_id"], "cena": scene_of.get(item["book_paragraph_id"], ""),
            "id": item["id"], "esperado": item["speaker"], "emitido": "NAO DETECTADA",
            "acertou_literal": 0, "acertou_identidade": 0, "sugestao_da_ia": "",
            "classe": klass(item["speaker"]), "familia": "nao_detectada",
            "texto": (item.get("text") or "").replace("\n", " ")[:200],
        })
    # Os acertos entram tambem: sem eles nao da para fatiar por cena nem por
    # personagem, e a conta de quanto cada cena ainda deve fica impossivel.
    listed = {str(row["id"]) for row in rows}
    for chapter in analysis.get("files", []):
        for item in chapter.get("dialogues", []):
            if str(item["id"]) in listed or int(item.get("fragment_index", 0)) != 0:
                continue
            if not item.get("speaker"):
                continue
            paragraph = int(item.get("book_paragraph_id") or -1)
            rows.append({
                "paragrafo": paragraph, "cena": scene_of.get(paragraph, ""),
                "id": str(item["id"]), "esperado": item["speaker"], "emitido": item["speaker"],
                "acertou_literal": 1, "acertou_identidade": 1,
                "sugestao_da_ia": item.get("llm_suggestion") or "",
                "classe": klass(item["speaker"]), "familia": "correto",
                "texto": (item.get("text") or "").replace("\n", " ")[:200],
            })
    rows.sort(key=lambda row: (str(row["cena"]), row["paragrafo"]))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else
                                ["paragrafo", "cena", "id", "esperado", "emitido",
                                 "sugestao_da_ia", "familia", "texto"])
        writer.writeheader()
        writer.writerows(rows)

    total = metrics["gold_source_turns"]
    print("O QUE DECIDE O PRODUTO — voz errada e o defeito; abster mantem o narrador")
    print(f"  Voz trocada errada:      {metrics.get('speaker_wrong_turns_by_identity', 0):3d} turnos")
    print(f"  Sem atribuicao (seguro): {metrics.get('speaker_abstained_turns', 0):3d} turnos")
    for item in metrics.get("by_class", []):
        print(f"  {item['class']:10s} precisao {item['precision_by_identity'] * 100:6.2f}%  "
              f"cobertura {item['coverage'] * 100:6.2f}%  "
              f"({item['correct_by_identity']} certos, {item['wrong_by_identity']} errados, "
              f"{item['abstained']} sem atribuicao, de {item['total']})")
    print(f"\nMetrica historica (abstencao contada como erro):")
    print(f"  literal    {metrics['speaker_correct_turns']}/{total} "
          f"({metrics['end_to_end_accuracy'] * 100:.2f}%)")
    identity = metrics.get("speaker_correct_turns_by_identity")
    if identity is not None:
        print(f"  identidade {identity}/{total} "
              f"({metrics['end_to_end_accuracy_by_identity'] * 100:.2f}%)")
    print(f"\n{len(rows)} turnos para revisar em {args.output}\n")
    print("Familia do erro                 Turnos")
    for name, count in Counter(row["familia"] for row in rows).most_common():
        print(f"  {name:30s} {count:4d}")
    print("\nCena                            Turnos")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
