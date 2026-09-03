from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def bitrate_kbps(value: str) -> int:
    match = re.search(r"(\d+)", value)
    return int(match.group(1)) if match else 320


def estimate_job(total_duration: float, bitrate: str, analysis: dict[str, Any] | None = None) -> dict[str, float]:
    analysis = analysis or {}
    output_mb = total_duration * bitrate_kbps(bitrate) * 1000 / 8 / 1024**2
    conversion_seconds = float(analysis.get("estimated_conversion_seconds", 0))
    analysis_elapsed = float(analysis.get("elapsed_seconds", 0))
    analyzed_duration = float(analysis.get("original_duration", 0))
    asr_ratio = analysis_elapsed / analyzed_duration if analyzed_duration > 0 else 0.15
    cached = bool(analysis)
    asr_seconds = 0.0 if cached else total_duration * max(0.03, asr_ratio)
    # Voice conversion speed varies greatly by backend; show a deliberately broad local estimate.
    minimum_seconds = asr_seconds + conversion_seconds * 0.5
    maximum_seconds = asr_seconds + conversion_seconds * 2.0
    return {
        "output_mb": round(output_mb, 1),
        "conversion_seconds": round(conversion_seconds, 1),
        "minimum_seconds": round(minimum_seconds, 1),
        "maximum_seconds": round(maximum_seconds, 1),
    }


def analysis_for_selection(report: dict[str, Any], filenames: set[str], convertible: set[str],
                           speaker_threshold: float, alignment_threshold: float) -> dict[str, Any]:
    files = [item for item in report.get("files", []) if Path(item.get("input", "")).name in filenames]
    duration = sum(float(item.get("duration", 0)) for item in files)
    report_duration = max(float(report.get("original_duration", 0)), 0.001)
    conversion = 0.0
    for item in files:
        for dialogue in item.get("dialogues", []):
            if (dialogue.get("speaker") in convertible
                    and float(dialogue.get("speaker_confidence", 0)) >= speaker_threshold
                    and float(dialogue.get("alignment_confidence", 0)) >= alignment_threshold):
                conversion += max(0.0, float(dialogue.get("end", 0)) - float(dialogue.get("start", 0)))
    return {
        "original_duration": duration,
        "elapsed_seconds": float(report.get("elapsed_seconds", 0)) * duration / report_duration,
        "estimated_conversion_seconds": conversion,
    }


def clock(seconds: float) -> str:
    seconds = max(0, round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
