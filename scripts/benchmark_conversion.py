"""Measure real VC samples from an existing analysis, without touching chapters.

This is a conversion-only measurement, NOT an end-to-end audiobook ETA.
Use separate output directories for persistent and CLI comparisons.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from audiobook_voice_enhancer.audio import conform_segment, extract_segment, probe
from audiobook_voice_enhancer.config import load_characters, load_config
from audiobook_voice_enhancer.voice_conversion import select_converter


def select_samples(report, characters, limit):
    groups = {}
    for chapter in report["files"]:
        for turn in chapter.get("dialogues", []):
            name = turn.get("speaker")
            if (turn.get("eligible") and name in characters and characters[name].get("mode") == "convert"
                    and 0 < turn["end"] - turn["start"] <= 60):
                groups.setdefault(name, []).append((chapter["input"], turn))
    # Round-robin across voices, alternating short/long samples within each.
    for items in groups.values():
        items.sort(key=lambda item: item[1]["end"] - item[1]["start"])
    selected = []
    longest = False
    while any(groups.values()) and len(selected) < limit:
        for name in sorted(groups):
            if groups[name] and len(selected) < limit:
                selected.append(groups[name].pop(-1 if longest else 0))
        longest = not longest
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "analysis", "config", "characters", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--mode", choices=("persistent", "cli"), default="persistent")
    args = parser.parse_args()
    if args.output.exists() or not 2 <= args.samples <= 64:
        parser.error("Use saída nova e entre 2 e 64 amostras")
    config = load_config(args.config)
    config["voice_conversion"]["persistent_worker"] = args.mode == "persistent"
    characters = load_characters(args.characters, project_root=args.root, require_references=True)
    report = json.loads(args.analysis.read_text(encoding="utf-8"))
    samples = select_samples(report, characters, args.samples)
    if len(samples) < 2:
        parser.error("O relatório precisa de pelo menos duas falas elegíveis de personagens em modo convert")
    converter = select_converter(config, args.root)
    if converter.name != "seedvc":
        parser.error("Esta comparação requer Seed-VC")
    args.output.mkdir(parents=True)
    rows = []
    began = time.monotonic()
    try:
        for index, (source, turn) in enumerate(samples):
            row = {"input": source, "id": turn["id"], "speaker": turn["speaker"]}
            started = time.monotonic()
            rows.append(row)
            try:
                character = characters[turn["speaker"]]
                padding = float(config.get("padding_ms", 150)) / 1000
                start = max(0, turn["start"] - padding)
                end = min(probe(Path(source)).duration, turn["end"] + padding)
                duration = end - start
                original = args.output / f"{index:02}-original.wav"
                raw = args.output / f"{index:02}-raw.wav"
                final = args.output / f"{index:02}-converted.wav"
                extract_segment(Path(source), original, start, end)
                conversion_started = time.monotonic()
                converter.convert(original, Path(character["_resolved_voice_reference"]), raw, character)
                row["backend_seconds"] = time.monotonic() - conversion_started
                crossfade = config.get("crossfade", {})
                fade = min(int(crossfade.get("max_ms", 150)),
                           max(int(crossfade.get("min_ms", 30)), max(1, round(duration * 1000)) // 10))
                conform_segment(raw, original, final, duration, fade)
                row.update(audio_seconds=duration, elapsed_seconds=time.monotonic() - started, ok=True)
            except Exception as exc:
                row.update(error=str(exc), ok=False, elapsed_seconds=time.monotonic() - started)
                raise
    finally:
        converter.close()
        measured = {"mode": args.mode, "samples": rows, "worker_timings": getattr(converter, "timings", []),
                    "elapsed_seconds": time.monotonic() - began,
                    "configuration": config["voice_conversion"], "audio_cache_reused": False,
                    "asr_and_attribution_executed": False, "full_chapter_export_executed": False,
                    "note": "Amostra estratificada de conversão; não é estimativa do livro inteiro."}
        (args.output / "timings.json").write_text(json.dumps(measured, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Medição salva em {args.output / 'timings.json'}")


if __name__ == "__main__":
    main()
