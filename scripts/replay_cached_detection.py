"""Replay only the deterministic engine; never starts ASR, LLM or conversion.

Input cache files are read-only. Output may contain book excerpts: keep it private.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from audiobook_voice_enhancer.benchmark import evaluate, load_gold
from audiobook_voice_enhancer.book import load_book, paragraphs
from audiobook_voice_enhancer.book_inventory import audio_coverage, dialogue_inventory
from audiobook_voice_enhancer.dialogue import DIALOGUE_ALGORITHM_VERSION, detect


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcription", required=True, type=Path)
    parser.add_argument("--alignment", required=True, type=Path)
    parser.add_argument("--book", required=True, type=Path)
    parser.add_argument("--aliases", type=Path, help="Optional JSON alias-to-name mapping")
    parser.add_argument("--gold", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    inputs = [args.transcription, args.alignment, args.book, args.aliases, args.gold]
    if output in [path.resolve() for path in inputs if path]:
        parser.error("Output must not overwrite an input")
    if output.exists():
        parser.error("Choose a new output path; an existing report will not be overwritten")
    transcript = json.loads(args.transcription.read_text(encoding="utf-8"))
    alignments = json.loads(args.alignment.read_text(encoding="utf-8"))
    blocks = paragraphs(load_book(args.book))
    aliases = json.loads(args.aliases.read_text(encoding="utf-8")) if args.aliases else {}
    started = time.perf_counter()
    inventory = dialogue_inventory(blocks)
    dialogues = detect(transcript, alignments, aliases, blocks)
    coverage = audio_coverage(inventory, alignments, dialogues)
    elapsed = time.perf_counter() - started
    report = {"algorithm": DIALOGUE_ALGORITHM_VERSION, "scope": "deterministic_replay_only",
              "elapsed_seconds": round(elapsed, 3), "asr_llm_conversion_executed": False,
              "inputs": {"transcription": args.transcription.name, "alignment": args.alignment.name},
              "files": [{"dialogues": dialogues, "book_dialogue_coverage": coverage}]}
    if args.gold:
        report["benchmark"] = evaluate(load_gold(args.gold), report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {key: value for key, value in report.items() if key not in {"files", "benchmark"}}
    summary["coverage"] = {key: value for key, value in coverage.items() if key != "candidates"}
    summary["recovered_short_paragraphs"] = [item["book_paragraph_id"] for item in dialogues
                                            if item.get("timing_method") == "exact_short_turn_between_anchors"]
    if args.gold:
        summary["benchmark"] = {key: value for key, value in report["benchmark"].items()
                                if isinstance(value, (int, float, str))}
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
