"""Controlled local replay of two engines; no ASR, voice conversion or input writes."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import requests

from audiobook_voice_enhancer import dialogue, llm
from audiobook_voice_enhancer.benchmark import evaluate, load_gold, render_markdown
from audiobook_voice_enhancer.book import load_book, paragraphs
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.config import load_config


def load_baseline(root: Path):
    package = root / "src/audiobook_voice_enhancer"
    spec = importlib.util.spec_from_file_location("speaker_baseline", package / "__init__.py",
                                                 submodule_search_locations=[str(package)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return importlib.import_module("speaker_baseline.dialogue"), importlib.import_module("speaker_baseline.llm")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline-root", "transcription", "alignment", "book", "gold", "config", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output directory; response caches must start empty")
    config = load_config(args.config)
    if config["llm"].get("provider") != "ollama":
        parser.error("This comparison is restricted to a local Ollama provider")
    from urllib.parse import urlsplit
    if urlsplit(config["llm"]["base_url"]).hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("The model endpoint must be loopback")
    baseline_dialogue, baseline_llm = load_baseline(args.baseline_root)
    transcript = json.loads(args.transcription.read_text(encoding="utf-8"))
    alignments = json.loads(args.alignment.read_text(encoding="utf-8"))
    blocks = paragraphs(load_book(args.book))
    gold = load_gold(args.gold)
    args.output.mkdir(parents=True)
    models = requests.get(config["llm"]["base_url"].rstrip("/") + "/api/tags", timeout=10).json()
    results = {"protocol": "development_regression_same_inputs_no_configured_aliases_or_overrides",
               "response_cache": "empty_per_engine", "model_loaded_before_each_timed_run": True,
               "asr_and_conversion_executed": False, "config": config["llm"],
               "model_metadata": models, "runs": {}}
    # A tiny original fixture loads the weights outside the timed chapter review.
    warmup = {"task": "Atribua a fala ao nome explícito.", "allowed_speakers": ["Iara"],
              "scene_text": [{"paragraph": 0, "text": "— Abra a porta — disse Iara."}],
              "target_dialogues": [{"id": "warmup", "text": "Abra a porta", "paragraph": 0}]}
    for label, detector, reviewer in (("baseline", baseline_dialogue, baseline_llm),
                                       ("candidate", dialogue, llm)):
        destination = args.output / label
        destination.mkdir()
        provider = reviewer.build_provider(config["llm"])
        print(f"{label}: loading model before timed run", flush=True)
        warm_started = time.perf_counter()
        review_timeout = provider.timeout
        provider.timeout = max(300, review_timeout)
        try:
            provider.infer(warmup)
        finally:
            provider.timeout = review_timeout
        warm_seconds = time.perf_counter() - warm_started
        started = time.perf_counter()
        found = detector.detect(copy.deepcopy(transcript), copy.deepcopy(alignments), {}, blocks)
        detection_seconds = time.perf_counter() - started
        report = {"files": [{"dialogues": found}]}
        before = evaluate(gold, copy.deepcopy(report))
        cache = Cache(destination / "cache")
        calls = []
        original_infer = provider.infer

        def timed_infer(payload):
            call_started = time.perf_counter()
            print(f"{label}: call {len(calls) + 1}, scene {payload.get('scene_id')}, "
                  f"{len(payload.get('target_dialogues', []))} targets", flush=True)
            entry = {"scene": payload.get("scene_id"), "targets": len(payload.get("target_dialogues", [])),
                     "pass": payload.get("review_pass", "critic" if "proposed_assignments" in payload else "first")}
            try:
                answer = original_infer(payload)
                entry["ok"] = True
                return answer
            except Exception as exc:
                entry.update(ok=False, error=str(exc))
                raise
            finally:
                entry["seconds"] = round(time.perf_counter() - call_started, 3)
                calls.append(entry)
                print(f"{label}: call completed in {entry['seconds']}s, ok={entry['ok']}", flush=True)

        provider.infer = timed_infer
        review_started = time.perf_counter()
        stats = reviewer.review_scenes(
            provider, cache, found, blocks, detector.book_character_names(blocks, {}),
            float(config["speaker_confidence_threshold"]),
            lambda position, total: print(f"{label}: batch {position}/{total}", flush=True),
            float(config["llm"].get("automatic_confidence", .98)),
            bool(config["llm"].get("critic_enabled", True)),
            float(config["llm"].get("consensus_confidence", .9)))
        detector.refine_speaker_sequence(found, {})
        review_seconds = time.perf_counter() - review_started
        metrics = evaluate(gold, report)
        report.update(benchmark=metrics, llm_review=stats)
        (destination / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (destination / "report.md").write_text(render_markdown(metrics), encoding="utf-8")
        results["runs"][label] = {"algorithm": detector.DIALOGUE_ALGORITHM_VERSION,
                                  "source_hashes": {Path(module.__file__).name: hashlib.sha256(
                                      Path(module.__file__).read_bytes()).hexdigest() for module in (detector, reviewer)},
                                  "model_load_seconds": round(warm_seconds, 3),
                                  "detection_seconds": round(detection_seconds, 3),
                                  "review_seconds": round(review_seconds, 3),
                                  "cache_hits": cache.hits, "cache_misses": cache.misses,
                                  "calls": calls, "stats": stats, "before": before, "after": metrics}
        (args.output / "comparison.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{label}: {metrics['speaker_correct_turns']}/{metrics['gold_source_turns']} correct; "
              f"review {review_seconds:.2f}s", flush=True)


if __name__ == "__main__":
    main()
