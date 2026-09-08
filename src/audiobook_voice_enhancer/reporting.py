from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .dialogue import turn_representatives


def summarize(files: list[dict[str, Any]], hardware: dict[str, Any], cache: dict[str, int], elapsed: float,
              transcription_backend: str, vc_backend: str) -> dict[str, Any]:
    dialogues = [dialogue for item in files for dialogue in item.get("dialogues", [])]
    # Turn IDs are local to a file (especially transcript-only chapters).
    turns = [turn for item in files for turn in turn_representatives(item.get("dialogues", []))]
    detected = Counter(dialogue.get("speaker") or "unknown" for dialogue in turns)
    converted = [dialogue for dialogue in dialogues if dialogue.get("action") == "converted"]
    planned = [dialogue for dialogue in dialogues if dialogue.get("action") == "would_convert"]
    skipped = [dialogue for dialogue in dialogues if dialogue.get("action") == "skipped"]
    converted_by_character = Counter(d.get("speaker") for d in converted if d.get("speaker"))
    skipped_turns = [d for d in turns if d.get("action") == "skipped"]
    intentional = Counter(d.get("speaker") for d in skipped_turns
                          if d.get("speaker") and d.get("character_mode") in {"original", "ignore"})
    unknown = sum(1 for d in skipped_turns if not d.get("speaker") or not d.get("character_configured"))
    narration = sum(max(0, item.get("segments_analyzed", 0) - len({d.get("segment_id") for d in item.get("dialogues", [])})) for item in files)
    llm_runs = [item["llm_review"] for item in files if item.get("llm_review")]
    llm_review = None
    if llm_runs:
        llm_review = {
            "model": llm_runs[0].get("model"),
            "scenes_reviewed": sum(item.get("scenes_reviewed", 0) for item in llm_runs),
            "batches_reviewed": sum(item.get("batches_reviewed", 0) for item in llm_runs),
            "dialogues_reviewed": sum(item.get("dialogues_reviewed", 0) for item in llm_runs),
            "assigned": sum(item.get("assigned", 0) for item in llm_runs),
            "suggested_for_review": sum(item.get("suggested_for_review", 0) for item in llm_runs),
            "unresolved": sum(item.get("unresolved", 0) for item in llm_runs),
            "elapsed_seconds": round(sum(item.get("elapsed_seconds", 0) for item in llm_runs), 3),
            "errors": [error for item in llm_runs for error in item.get("errors", [])],
        }
    return {"original_duration": sum(item.get("duration", 0) for item in files),
            "final_duration": sum(item.get("final_duration", item.get("duration", 0)) for item in files),
            "segments_analyzed": sum(item.get("segments_analyzed", 0) for item in files),
            "dialogues_detected": len(turns), "dialogue_regions_detected": len(dialogues),
            "segments_converted": len(converted),
            "characters_detected": dict(detected), "segments_skipped": len(skipped),
            "characters_converted": dict(converted_by_character),
            "characters_planned_for_conversion": dict(Counter(d.get("speaker") for d in planned if d.get("speaker"))),
            "characters_intentionally_preserved": {**dict(intentional), "__narrator__": narration},
            "unknown_characters_preserved": unknown,
            "low_confidence_segments": sum(1 for d in dialogues if "confidence" in str(d.get("skip_reason", ""))),
            "estimated_conversion_seconds": round(sum(d["end"] - d["start"] for d in dialogues if d.get("eligible")), 3),
            "errors": [error for item in files for error in item.get("errors", [])],
            "warnings": [warning for item in files for warning in item.get("warnings", [])],
            "elapsed_seconds": round(elapsed, 3), "gpu": hardware.get("gpu"),
            "transcription_backend": transcription_backend, "voice_conversion_backend": vc_backend,
            "cache": cache, "alignment_success_rate": _alignment_rate(dialogues),
            "llm_contextual_review": llm_review, "files": files}


def _alignment_rate(dialogues: list[dict[str, Any]]) -> float | None:
    aligned = [d for d in dialogues if d.get("source") == "book"]
    if not aligned:
        return None
    return round(sum(d.get("alignment_confidence", 0) >= 0.8 for d in aligned) / len(aligned), 4)


def write_reports(report: dict[str, Any], output: Path, analysis_only: bool = False) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if analysis_only:
        (output / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = "".join(f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>" for key, value in report.items() if key != "files")
    details = "".join(f"<h2>{html.escape(item['input'])}</h2><pre>{html.escape(json.dumps(item, ensure_ascii=False, indent=2))}</pre>" for item in report["files"])
    document = f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Audiobook Voice Enhancer — relatório</title><style>body{{font:15px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#17202a}}table{{border-collapse:collapse;width:100%}}th,td{{padding:.55rem;border:1px solid #ccd;text-align:left}}th{{width:30%;background:#eef2f7}}pre{{white-space:pre-wrap;background:#f6f8fa;padding:1rem;overflow:auto}}</style>
<h1>Audiobook Voice Enhancer</h1><table>{rows}</table>{details}</html>"""
    (output / "report.html").write_text(document, encoding="utf-8")
