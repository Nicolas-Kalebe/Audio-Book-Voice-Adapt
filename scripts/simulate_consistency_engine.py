"""Reapply the current consistency engine to a cold run made without it.

This is an offline development aid: it does not call Ollama, ASR, or conversion.
It reports the exact product metrics produced by the implementation in
``turn_consistency.py`` against an explicitly selected frozen gold file.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from audiobook_voice_enhancer.benchmark import evaluate, load_gold
from audiobook_voice_enhancer.book_speakers import project_to_audio
from audiobook_voice_enhancer.turn_consistency import apply_consistency


def product_row(metrics: dict) -> dict:
    return next(row for row in metrics["by_class"] if row["class"] == "dublavel")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()

    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    gold = load_gold(args.gold)
    chapter = analysis["files"][0]
    before = product_row(evaluate(gold, {"files": [{"dialogues": chapter["dialogues"]}]}))

    model = copy.deepcopy(chapter["book_speaker_analysis"])
    model["entities"] = {entity["id"]: entity for entity in model["entities"]}
    original = {turn["id"]: turn.get("speaker_entity_id") for turn in model["turns"]}
    stats = apply_consistency(model)
    dialogues = copy.deepcopy(chapter["dialogues"])
    project_to_audio(model, dialogues)
    after_metrics = evaluate(gold, {"files": [{"dialogues": dialogues}]})
    after = product_row(after_metrics)

    def render(label: str, row: dict) -> None:
        print(f"{label:12s} certos {row['correct_by_identity']:3d}  errados {row['wrong_by_identity']:3d}  "
              f"precisao {row['precision_by_identity'] * 100:6.2f}%  "
              f"cobertura {row['coverage'] * 100:6.2f}%")

    render("sem regras", before)
    render("motor atual", after)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if args.details:
        expected = {str(item): speaker for speaker, ids in gold["spoken_by"].items() for item in ids}
        for turn in model["turns"]:
            if original[turn["id"]] == turn.get("speaker_entity_id"):
                continue
            candidate = str(turn["fragments"][0]["candidate_id"])
            before_name = model["entities"].get(original[turn["id"]], {}).get("display_name", "-")
            after_name = model["entities"].get(turn.get("speaker_entity_id"), {}).get("display_name", "-")
            print(f"P{turn['fragments'][0]['paragraph']} {turn.get('consistency_rule', '-')}: "
                  f"{before_name} -> {after_name}; esperado={expected.get(candidate, '-')}; "
                  f"fragmentos={len(turn['fragments'])}")
        print("pendencias restantes:")
        for item in after_metrics["wrong_or_unassigned"]:
            print(f"  P{item['paragraph']}: esperado={item['expected']}; "
                  f"emitido={item['predicted'] or '-'}; sugestao={item.get('suggestion') or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
