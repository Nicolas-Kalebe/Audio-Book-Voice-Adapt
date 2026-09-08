"""Teto do gabarito: quanto um motor PERFEITO marcaria com as regras atuais.

Um oraculo que acerta o falante de todos os turnos ainda perde pontos quando o
rotulo que o motor exibe nao pode casar com o rotulo escrito no gabarito. Rodar
isto antes de qualquer campanha diz se a meta e alcancavel; sem esse numero, uma
diferenca de nomenclatura vira meses de ajuste de prompt contra um limite fixo.

Uso:
    python scripts/gold_ceiling.py --gold benchmarks/part01_gold.yaml
"""
from __future__ import annotations

import argparse
from pathlib import Path

from audiobook_voice_enhancer.benchmark import evaluate, load_gold
from audiobook_voice_enhancer.book_speakers import build_book, _entity


def oracle_report(gold: dict) -> dict:
    """Relatorio em que cada turno recebe o falante verdadeiro do gabarito.

    O rotulo passa pelo mesmo caminho de nomeacao do motor, entao o resultado
    mede a nomenclatura, nao a identificacao.
    """
    spoken = {str(i): s for s, ids in gold["spoken_by"].items() for i in ids}
    for label, detail in (gold.get("ambiguous_spoken") or {}).items():
        for item in detail.get("ids", []):
            spoken[str(item)] = label
    anonymous = {str(label) for label in (gold.get("anonymous_role_labels") or [])}
    standalone = {str(v) for v in gold.get("standalone_quote_turn_ids", [])}
    missing = {str(m["id"]) for m in gold.get("missing_spoken", [])}
    dialogues = []
    for candidate, role in spoken.items():
        if candidate in missing:  # sem correspondencia no audio: nunca pontua
            continue
        paragraph = int(candidate.split("-")[0])
        model = {"book_id": "oracle", "aliases": {}, "entities": {}, "anonymous_scope": "scene"}
        kind = "anonymous" if role in anonymous else "named"
        identity = _entity(model, role, kind, 0, paragraph, fresh=kind == "anonymous")
        dialogues.append({"id": candidate, "source": "book", "book_paragraph_id": paragraph,
                          "turn_id": None if candidate in standalone else f"book-{paragraph}",
                          "fragment_index": 0, "start": 0.0, "text": "",
                          "speaker": model["entities"][identity]["display_name"]})
    for candidate in (str(i) for ids in gold["non_spoken"].values() for i in ids):
        paragraph = int(candidate.split("-")[0])
        dialogues.append({"id": candidate, "source": "book", "book_paragraph_id": paragraph,
                          "turn_id": f"book-{paragraph}-x", "fragment_index": 0,
                          "start": 0.0, "text": "", "speaker": None})
    return {"files": [{"dialogues": dialogues}]}


def ceiling(gold: dict) -> dict:
    metrics = evaluate(gold, oracle_report(gold))
    total = metrics["gold_source_turns"]
    return {"gold_source_turns": total,
            "literal_ceiling": metrics["speaker_correct_turns"],
            "identity_ceiling": metrics["speaker_correct_turns_by_identity"],
            "literal_ceiling_accuracy": metrics["end_to_end_accuracy"],
            "identity_ceiling_accuracy": metrics["end_to_end_accuracy_by_identity"],
            "unreachable_labels": metrics["confusion"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=Path("benchmarks/part01_gold.yaml"))
    parser.add_argument("--target", type=float, default=0.90)
    args = parser.parse_args()
    result = ceiling(load_gold(args.gold))
    total = result["gold_source_turns"]
    need = -(-int(total * args.target * 100) // 100)
    print(f"Turnos no gabarito: {total}")
    print(f"Teto com oraculo perfeito, comparacao literal:    "
          f"{result['literal_ceiling']}/{total} ({result['literal_ceiling_accuracy'] * 100:.2f}%)")
    print(f"Teto com oraculo perfeito, comparacao por identidade: "
          f"{result['identity_ceiling']}/{total} ({result['identity_ceiling_accuracy'] * 100:.2f}%)")
    print(f"Meta de {args.target * 100:.0f}% exige {need} turnos.")
    if result["identity_ceiling"] < need:
        print("\nA META NAO E ALCANCAVEL com este gabarito e estas regras de nomenclatura.")
        print("Rotulos que um oraculo perfeito ainda erraria:")
        for item in result["unreachable_labels"]:
            print(f"  {item['count']:3d}  esperado {item['expected']!r} -> emitido {item['predicted']!r}")
        return 1
    print("Meta alcancavel: a diferenca restante e identificacao, nao nomenclatura.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
