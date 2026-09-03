from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from .alignment import align_blocks
from .audio import conform_segment, discover_audio, extract_segment, probe, reconstruct
from .book import load_book, paragraphs
from .cache import Cache
from .config import load_characters, load_config
from .dialogue import detect
from .hardware import detect_hardware
from .llm import build_provider, cached_infer
from .reporting import summarize, write_reports
from .transcription import transcribe
from .voice_conversion import VoiceConversionError, select_converter

LOG = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, root: Path, config_path: Path, characters_path: Path, output: Path, cache_root: Path):
        self.root = root.resolve()
        self.config = load_config(config_path)
        self.characters_path = characters_path.resolve()
        self.characters = load_characters(characters_path, project_root=self.root,
            allow_shared=bool(self.config.get("allow_shared_voice_references", True)), require_references=False)
        self.output = output.resolve()
        self.cache = Cache(cache_root.resolve())
        self.hardware = detect_hardware()
        self.converter = select_converter(self.config, self.root)
        self.llm = build_provider(self.config.get("llm", {}))

    def run(self, source: Path, *, command: str, language: str, book_text: Path | None, dry_run: bool) -> dict[str, Any]:
        started = time.monotonic()
        if command == "process" and not dry_run:
            # Conversion mode is a promise: fail before hours of ASR when a required voice is missing.
            load_characters(self.characters_path,
                            project_root=self.root,
                            allow_shared=bool(self.config.get("allow_shared_voice_references", True)),
                            require_references=True)
        files = discover_audio(source)
        book_blocks = paragraphs(load_book(book_text)) if book_text else []
        book_fingerprint = self.cache.file_fingerprint(book_text) if book_text else None
        results: list[dict[str, Any]] = []
        book_cursor = 0
        for path in files:
            item = self._one(path, command=command, language=language, book_blocks=book_blocks,
                             book_fingerprint=book_fingerprint, book_cursor=book_cursor, dry_run=dry_run)
            book_cursor = int(item.pop("_book_cursor", book_cursor))
            results.append(item)
        report = summarize(results, self.hardware, {"hits": self.cache.hits, "misses": self.cache.misses},
                           time.monotonic() - started, "faster-whisper", self.converter.name)
        analysis_only = command == "analyze" or dry_run
        write_reports(report, self.output, analysis_only=analysis_only)
        return report

    def _one(self, path: Path, *, command: str, language: str, book_blocks: list[str],
             book_fingerprint: dict[str, Any] | None, book_cursor: int, dry_run: bool) -> dict[str, Any]:
        info = probe(path)
        fingerprint = self.cache.file_fingerprint(path)
        trans_key = self.cache.digest(fingerprint, self.config.get("transcription", {}), language, self.config.get("device"))
        transcript = self.cache.json("transcription", trans_key, lambda: transcribe(path, self.config, language))
        alignments: list[dict[str, Any]] = []
        if book_blocks:
            align_key = self.cache.digest(trans_key, book_fingerprint, self.config.get("alignment", {}), book_cursor)
            alignments = self.cache.json("alignment", align_key, lambda: align_blocks(
                book_blocks, transcript, int(self.config.get("alignment", {}).get("block_window", 40)), book_cursor))
        dialogue_key = self.cache.digest(trans_key, alignments)
        dialogues = self.cache.json("dialogue_detection", dialogue_key, lambda: detect(transcript, alignments))
        self._resolve_ambiguous(dialogues, transcript)
        for dialogue in dialogues:
            self._eligibility(dialogue, bool(book_blocks))
        self._prevent_overlaps(dialogues)
        result: dict[str, Any] = {"input": str(path), "duration": info.duration, "sample_rate": info.sample_rate,
            "channels": info.channels, "codec": info.codec, "segments_analyzed": len(transcript.get("segments", [])),
            "dialogues": dialogues, "errors": [], "warnings": [], "final_duration": info.duration}
        confident_ids = [int(item["book_paragraph_id"]) for item in alignments if item.get("alignment_confidence", 0) >= 0.5]
        result["_book_cursor"] = max(confident_ids, default=book_cursor) + (1 if confident_ids else 0)
        if command == "analyze" or dry_run:
            for dialogue in dialogues:
                dialogue["action"] = "would_convert" if dialogue["eligible"] else "skipped"
            return result
        replacements: list[tuple[float, float, Path]] = []
        for dialogue in dialogues:
            if not dialogue["eligible"]:
                dialogue["action"] = "skipped"
                continue
            try:
                replacement = self._convert(path, dialogue)
                replacements.append((dialogue["start"], dialogue["end"], replacement))
                dialogue["action"] = "converted"
            except Exception as exc:
                dialogue["action"] = "skipped"
                dialogue["skip_reason"] = f"voice conversion failed: {exc}"
                result["errors"].append(f"{dialogue['id']}: {exc}")
                LOG.exception("Falha ao converter %s/%s; áudio original será preservado", path.name, dialogue["id"])
        extension = "." + str(self.config.get("output", {}).get("format", "mp3")).lstrip(".")
        target = self.output / f"{path.stem} Enhanced{extension}"
        reconstruct(path, replacements, target, str(self.config.get("output", {}).get("bitrate", "320k")))
        result["output"] = str(target)
        result["final_duration"] = probe(target).duration
        return result

    def _resolve_ambiguous(self, dialogues: list[dict[str, Any]], transcript: dict[str, Any]) -> None:
        if not self.llm:
            return
        segments = transcript.get("segments", [])
        for dialogue in dialogues:
            if dialogue.get("speaker_confidence", 0) >= float(self.config["speaker_confidence_threshold"]):
                continue
            index = int(dialogue["segment_id"])
            context = [segment.get("text", "") for segment in segments[max(0, index - 3):index + 4]]
            payload = {"context": context, "dialogue": dialogue["text"], "known_characters": list(self.characters)}
            try:
                answer = cached_infer(self.llm, self.cache, payload)
                if answer.get("speaker") in self.characters:
                    dialogue["speaker"] = answer["speaker"]
                    dialogue["speaker_confidence"] = min(1.0, max(0.0, float(answer.get("confidence", 0))))
                    dialogue["reason"] = f"LLM contextual: {answer.get('reason', '')}"
            except Exception as exc:
                dialogue["llm_error"] = str(exc)

    def _eligibility(self, dialogue: dict[str, Any], has_book: bool) -> None:
        reasons: list[str] = []
        speaker = dialogue.get("speaker")
        character = self.characters.get(speaker) if speaker else None
        dialogue["character_configured"] = character is not None
        if not speaker: reasons.append("speaker unidentified")
        elif not character: reasons.append("character not configured")
        mode = str((character or {}).get("mode", self.config.get("characters", {}).get("default_mode", "original")))
        dialogue["character_mode"] = mode
        if character and mode in {"original", "ignore"}: reasons.append(f"character mode is {mode}")
        elif character and mode == "auto" and not self.config.get("characters", {}).get("auto_convert_with_reference", False):
            reasons.append("character mode auto resolved to original")
        elif character and mode in {"convert", "auto"} and not Path(character.get("_resolved_voice_reference", "")).is_file():
            reasons.append("voice reference missing")
        if float(dialogue.get("speaker_confidence", 0)) < float(self.config["speaker_confidence_threshold"]):
            reasons.append("speaker confidence below threshold")
        if has_book and float(dialogue.get("alignment_confidence", 0)) < float(self.config["alignment_confidence_threshold"]):
            reasons.append("alignment confidence below threshold")
        minimum = float((character or {}).get("minimum_segment_duration", self.config.get("minimum_segment_duration", 0.8)))
        if dialogue["end"] - dialogue["start"] < minimum: reasons.append("segment too short")
        if dialogue.get("unsafe_short"): reasons.append("unsafe interjection/non-speech")
        dialogue["eligible"] = not reasons
        dialogue["skip_reason"] = "; ".join(reasons) if reasons else None

    def _convert(self, source: Path, dialogue: dict[str, Any]) -> Path:
        character = self.characters[dialogue["speaker"]]
        padding = float(self.config.get("padding_ms", 150)) / 1000
        start, end = max(0, dialogue["start"] - padding), dialogue["end"] + padding
        key = self.cache.digest(self.cache.file_fingerprint(source), dialogue, character, self.converter.name)
        final = self.cache.path("converted_audio", key, ".wav")
        if final.is_file():
            self.cache.hits += 1
            return final
        self.cache.misses += 1
        original = self.cache.path("converted_audio", key + "-original", ".wav")
        raw = self.cache.path("converted_audio", key + "-raw", ".wav")
        extract_segment(source, original, start, end)
        self.converter.convert(original, Path(character["_resolved_voice_reference"]), raw, character)
        crossfade = self.config.get("crossfade", {})
        duration_ms = max(1, round((end - start) * 1000))
        fade = min(int(crossfade.get("max_ms", 150)), max(int(crossfade.get("min_ms", 30)), duration_ms // 10))
        conform_segment(raw, original, final, end - start, fade)
        # Reconstruction coordinates include padding, making fades land in low-risk boundaries.
        dialogue["start"], dialogue["end"] = start, end
        return final

    def _prevent_overlaps(self, dialogues: list[dict[str, Any]]) -> None:
        padding = float(self.config.get("padding_ms", 150)) / 1000
        previous_end = -1.0
        for dialogue in sorted(dialogues, key=lambda item: (item["start"], item["end"])):
            if not dialogue.get("eligible"):
                continue
            planned_start, planned_end = max(0, dialogue["start"] - padding), dialogue["end"] + padding
            if planned_start < previous_end:
                dialogue["eligible"] = False
                dialogue["skip_reason"] = "overlapping conversion window"
            else:
                previous_end = planned_end
