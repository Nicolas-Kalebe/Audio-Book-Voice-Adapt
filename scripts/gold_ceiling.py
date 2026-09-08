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
    dublavel = next(item for item in metrics["by_class"] if item["class"] == "dublavel")
    # Turno sem audio nunca pode ser atribuido: e o teto da cobertura, e e ele
    # que decide se a meta de cobertura cabe no gabarito.
    return {"gold_source_turns": total,
            "literal_ceiling": metrics["speaker_correct_turns"],
            "identity_ceiling": metrics["speaker_correct_turns_by_identity"],
            "literal_ceiling_accuracy": metrics["end_to_end_accuracy"],
            "identity_ceiling_accuracy": metrics["end_to_end_accuracy_by_identity"],
            "dublavel_turns": dublavel["total"],
            "dublavel_detected": dublavel["detected"],
            "dublavel_ceiling": dublavel["correct_by_identity"],
            "unreachable_labels": metrics["confusion"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=Path("benchmarks/part01_gold.yaml"))
    parser.add_argument("--target", type=float, default=0.95)
    args = parser.parse_args()
    result = ceiling(load_gold(args.gold))
    total, dublavel = result["gold_source_turns"], result["dublavel_turns"]
    detected = result["dublavel_detected"]
    up = lambda value: -(-int(round(value * 1e6)) // 10 ** 6)  # teto sem erro de float
    need_coverage = up(dublavel * args.target)
    need_correct = up(need_coverage * args.target)
    slack = detected - need_coverage

    print(f"Turnos no gabarito: {total}, dos quais {dublavel} sao dublaveis "
          f"({total - dublavel} figurantes de uma cena so, que nao ganham voz).")
    print(f"Teto de localizacao: {detected}/{dublavel} dublaveis tem audio; "
          f"{dublavel - detected} nunca poderao ser atribuidos.")
    print(f"\nMeta de {args.target * 100:.0f}% em tudo, sobre os dublaveis:")
    print(f"  cobertura: exige {need_coverage} atribuidos; o teto e {detected}, "
          f"logo sobram {slack} abstencoes.")
    print(f"  precisao:  exige {need_correct} corretos entre os {need_coverage} atribuidos, "
          f"logo sobram {need_coverage - need_correct} vozes trocadas erradas.")
    if slack < 0:
        print("\nA META DE COBERTURA NAO CABE NO GABARITO: nem atribuindo tudo que tem "
              "audio se alcanca o alvo. O problema e localizacao, nao identificacao.")
        for item in result["unreachable_labels"]:
            print(f"  {item['count']:3d}  esperado {item['expected']!r} -> emitido {item['predicted']!r}")
        return 1
    if result["identity_ceiling"] < result["dublavel_ceiling"]:
        print("\nRotulos que um oraculo perfeito ainda erraria:")
        for item in result["unreachable_labels"]:
            print(f"  {item['count']:3d}  esperado {item['expected']!r} -> emitido {item['predicted']!r}")
        return 1
    print(f"\nMeta alcancavel, com folga de {slack} abstencoes e "
          f"{need_coverage - need_correct} erros. A diferenca restante e identificacao, "
          f"nao nomenclatura.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
