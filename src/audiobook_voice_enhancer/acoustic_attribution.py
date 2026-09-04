from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from .audio import require_ffmpeg
from .cache import Cache


ACOUSTIC_VERSION = "resemblyzer-dialogue-centroids-v1"


class AcousticAttributionError(RuntimeError):
    pass


def suggest_speakers(root: Path, source: Path, dialogues: list[dict[str, Any]], cache: Cache,
                     config: dict[str, Any]) -> int:
    settings = config.get("speaker_attribution", {})
    if not settings.get("acoustic_suggestions", True):
        return 0
    anchor_confidence = float(settings.get("acoustic_anchor_confidence", 0.90))
    anchors = [item for item in dialogues if item.get("speaker") and
               float(item.get("speaker_confidence", 0)) >= anchor_confidence and
               float(item["end"]) - float(item["start"]) >= 0.8]
    minimum_anchors = int(settings.get("minimum_acoustic_anchors", 2))
    counts: dict[str, int] = defaultdict(int)
    for item in anchors:
        counts[str(item["speaker"])] += 1
    eligible_speakers = {speaker for speaker, count in counts.items() if count >= minimum_anchors}
    if len(eligible_speakers) < 2:
        return 0
    candidates = [item for item in dialogues if item.get("dialogue_style") == "dash" and
                  0.8 <= float(item["end"]) - float(item["start"]) <= 60]
    fingerprint = cache.file_fingerprint(source)
    key = cache.digest(ACOUSTIC_VERSION, fingerprint,
                       [(item["id"], item["start"], item["end"]) for item in candidates])
    folder = cache.root / "speaker_analysis" / key
    embeddings_path = folder / "embeddings.json"
    if not embeddings_path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        normalized = folder / "source-16k.wav"
        require_ffmpeg()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-vn", "-ac", "1",
                                  "-ar", "16000", "-c:a", "pcm_s16le", str(normalized)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 creationflags=flags)
        if process.returncode:
            raise AcousticAttributionError(process.stderr.strip() or "FFmpeg não preparou o áudio")
        spans = folder / "dialogues.json"
        spans.write_text(json.dumps([{"id": item["id"], "start": item["start"], "end": item["end"]}
                                     for item in candidates]), encoding="utf-8")
        seed_python = root / "models" / "seed-vc" / ".venv" / "Scripts" / "python.exe"
        if not seed_python.is_file():
            raise AcousticAttributionError("ambiente do Seed-VC ausente")
        helper = Path(__file__).with_name("speaker_classifier.py")
        process = subprocess.run([str(seed_python), str(helper), str(normalized), str(spans), str(embeddings_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 creationflags=flags)
        if process.returncode or not embeddings_path.is_file():
            raise AcousticAttributionError((process.stderr or process.stdout).strip()[-2000:])
        normalized.unlink(missing_ok=True)
    vectors = {item["id"]: np.asarray(item["embedding"], dtype=np.float32)
               for item in json.loads(embeddings_path.read_text(encoding="utf-8"))}
    return assign_suggestions(dialogues, vectors, settings, eligible_speakers)


def assign_suggestions(dialogues: list[dict[str, Any]], vectors: dict[str, np.ndarray],
                       settings: dict[str, Any], eligible_speakers: set[str]) -> int:
    grouped: dict[str, list[np.ndarray]] = defaultdict(list)
    anchor_confidence = float(settings.get("acoustic_anchor_confidence", 0.90))
    anchors = [item for item in dialogues if item.get("speaker") in eligible_speakers and
               float(item.get("speaker_confidence", 0)) >= anchor_confidence]
    for item in anchors:
        if item["speaker"] in eligible_speakers and item["id"] in vectors:
            grouped[item["speaker"]].append(vectors[item["id"]])
    centroids = {}
    for speaker, values in grouped.items():
        centroid = np.mean(values, axis=0)
        centroids[speaker] = centroid / max(float(np.linalg.norm(centroid)), 1e-8)
    if len(centroids) < 2:
        return 0
    scene_speakers: dict[int, set[str]] = defaultdict(set)
    for item in anchors:
        scene_speakers[int(item.get("scene_id", -1))].add(str(item["speaker"]))
    minimum_similarity = float(settings.get("minimum_acoustic_similarity", 0.78))
    minimum_margin = float(settings.get("minimum_acoustic_margin", 0.06))
    suggested = 0
    for item in dialogues:
        vector = vectors.get(item["id"])
        if item.get("speaker") or vector is None:
            continue
        allowed = scene_speakers.get(int(item.get("scene_id", -1)), set()) & set(centroids)
        if len(allowed) < 2:
            continue
        ranked = sorted(((float(np.dot(vector, centroids[speaker])), speaker) for speaker in allowed),
                        reverse=True)
        best_score, best_speaker = ranked[0]
        margin = best_score - ranked[1][0]
        item["acoustic_best_candidate"] = best_speaker
        item["acoustic_similarity"] = round(best_score, 4)
        item["acoustic_margin"] = round(margin, 4)
        if best_score >= minimum_similarity and margin >= minimum_margin:
            item["acoustic_suggestion"] = best_speaker
            suggested += 1
    return suggested
