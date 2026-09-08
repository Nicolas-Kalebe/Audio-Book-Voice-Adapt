"""Print expected and predicted speaker sequences for an existing benchmark run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audiobook_voice_enhancer.benchmark import load_gold


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    args = parser.parse_args()

    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    gold = load_gold(args.gold)
    model = analysis["files"][0]["book_speaker_analysis"]
    names = {entity["id"]: entity["display_name"] for entity in model["entities"]}
    expected = {str(item): speaker for speaker, ids in gold["spoken_by"].items() for item in ids}
    for label, detail in (gold.get("ambiguous_spoken") or {}).items():
        for item in detail.get("ids", []):
            expected[str(item)] = label

    print("para scene expected             predicted            raw                  status      rule                 text")
    for turn in model["turns"]:
        paragraph = int(turn["fragments"][0]["paragraph"])
        if args.start is not None and paragraph < args.start:
            continue
        if args.end is not None and paragraph > args.end:
            continue
        candidate = str(turn["fragments"][0]["candidate_id"])
        want = expected.get(candidate, "-")
        got = names.get(turn.get("speaker_entity_id"), "-")
        raw = names.get((turn.get("proposal") or {}).get("speaker_entity_id"), "-")
        text = " ".join(fragment["text"] for fragment in turn["fragments"])
        rule = str(turn.get("consistency_rule") or "-")
        print(f"{paragraph:4d} {turn['scene_id']:5d} {want[:20]:20s} {got[:20]:20s} "
              f"{raw[:20]:20s} {turn['status'][:10]:10s} {rule[:20]:20s} {text[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
