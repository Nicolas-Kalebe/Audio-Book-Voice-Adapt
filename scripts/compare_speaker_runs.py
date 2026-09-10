"""Compare speaker engines turn by turn and record exactly where each one wins."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from audiobook_voice_enhancer.benchmark import load_gold
from audiobook_voice_enhancer.speaker_differential import compare_runs, render_markdown


def load_analysis(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", action="append", required=True,
                        help="NAME=path/to/analysis.json; may be repeated")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    candidates = {}
    for value in args.candidate:
        name, separator, path = value.partition("=")
        if not separator or not name or not path:
            parser.error("--candidate must use NAME=PATH")
        candidates[name] = load_analysis(Path(path))
    report = compare_runs(load_gold(args.gold), load_analysis(args.baseline), candidates)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "speaker-differential.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "speaker-differential.md").write_text(
        render_markdown(report), encoding="utf-8")
    rows = report["rows"]
    with (args.output / "speaker-differential.csv").open(
            "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
