from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from .alignment import ALIGNMENT_ALGORITHM_VERSION, align_blocks
from .audio import conform_segment, discover_audio, extract_segment, probe, reconstruct
from .book import load_book, paragraphs
from .book_inventory import audio_coverage, dialogue_inventory
from .book_speakers import (VERSION as BOOK_SPEAKER_VERSION, BOOK_SYSTEM, BOOK_SCHEMA,
                            build_book, project_to_audio, review_book, scoped_report)
from .cache import Cache
from .compact_speakers import VERSION as COMPACT_VERSION, SYSTEM as COMPACT_SYSTEM, SCHEMA as COMPACT_SCHEMA
from .scene_context import VERSION as SCENE_VERSION, CAST_SYSTEM, CAST_SCHEMA, ATTRIBUTION_SUFFIX
from .lightweight_speakers import VERSION as LIGHT_VERSION, SUFFIX as LIGHT_SUFFIX
from .speaker_subjects import VERSION as SUBJECT_VERSION, SUFFIX as SUBJECT_SUFFIX
from .character_discovery import build_alias_map, merge_detected_characters
from .config import load_characters, load_config
from .dialogue import (DIALOGUE_ALGORITHM_VERSION, book_character_names, detect,
                       propagate_speaker_inside_turn, refine_speaker_sequence)
from .hardware import detect_hardware
from .llm import build_provider, review_cache_identity, review_scenes
from .reporting import summarize, write_reports
from .speaker_overrides import apply_overrides
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
        self.speaker_aliases = build_alias_map(self.characters)
        self.output = output.resolve()
        self.cache = Cache(cache_root.resolve())
        self.voice_fingerprints = self._voice_fingerprints()
        self.hardware = detect_hardware()
        self.converter = select_converter(self.config, self.root)
        self.llm = build_provider(self.config.get("llm", {}))
        self.book_characters: set[str] = set()

    def run(self, source: Path, *, command: str, language: str, book_text: Path | None, dry_run: bool,
            include: list[str] | None = None) -> dict[str, Any]:
        try:
            return self._run(source, command=command, language=language, book_text=book_text,
                             dry_run=dry_run, include=include)
        finally:
            self.converter.close()

    def _run(self, source: Path, *, command: str, language: str, book_text: Path | None, dry_run: bool,
             include: list[str] | None = None) -> dict[str, Any]:
        started = time.monotonic()
        if command == "process" and not dry_run:
            # Conversion mode is a promise: fail before hours of ASR when a required voice is missing.
            load_characters(self.characters_path,
                            project_root=self.root,
                            allow_shared=bool(self.config.get("allow_shared_voice_references", True)),
                            require_references=True)
        files = discover_audio(source, include)
        book_blocks = paragraphs(load_book(book_text)) if book_text else []
        self.book_inventory = dialogue_inventory(book_blocks)
        self.book_characters = book_character_names(book_blocks, getattr(self, "speaker_aliases", {}))
        book_fingerprint = self.cache.file_fingerprint(book_text) if book_text else None
        self.book_model = None
        if book_blocks and self.config.get("book_first", {}).get("enabled", False):
            text_key = self.cache.digest(BOOK_SPEAKER_VERSION, book_blocks, self.speaker_aliases)
            LOG.info("[BOOK] Construindo entidades e turnos do livro")
            self.book_model = self.cache.json("book_speakers", text_key,
                                             lambda: build_book(book_blocks, self.speaker_aliases))
        run_key = self.cache.digest(
            ALIGNMENT_ALGORITHM_VERSION, DIALOGUE_ALGORITHM_VERSION,
            [self.cache.file_fingerprint(path) for path in files], book_fingerprint, self.config,
            self.characters, self.voice_fingerprints, command, dry_run, language,
            review_cache_identity(self.llm),
            BOOK_SPEAKER_VERSION, BOOK_SYSTEM, BOOK_SCHEMA,
            COMPACT_VERSION, COMPACT_SYSTEM, COMPACT_SCHEMA,
            SCENE_VERSION, CAST_SYSTEM, CAST_SCHEMA, ATTRIBUTION_SUFFIX,
            LIGHT_VERSION, LIGHT_SUFFIX,
            SUBJECT_VERSION, SUBJECT_SUFFIX,
        )
        checkpoint_path = self.cache.path("checkpoints", run_key)
        checkpoint = self._load_checkpoint(checkpoint_path, command, dry_run)
        results: list[dict[str, Any]] = checkpoint.get("results", [])
        book_cursor = int(checkpoint.get("book_cursor", 0))
        next_index = min(int(checkpoint.get("next_index", 0)), len(files))
        total_files = len(files)
        for file_index, path in enumerate(files, 1):
            if file_index <= next_index:
                LOG.info("[PROGRESS] %.2f%% | capítulo %d/%d | %s | restaurado do checkpoint",
                         file_index * 100 / total_files, file_index, total_files, path.name)
                continue
            LOG.info("[PROGRESS] %.2f%% | capítulo %d/%d | %s | iniciando", (file_index - 1) * 100 / total_files,
                     file_index, total_files, path.name)
            item = self._one(path, command=command, language=language, book_blocks=book_blocks,
                             book_fingerprint=book_fingerprint, book_cursor=book_cursor, dry_run=dry_run,
                             file_index=file_index, total_files=total_files)
            # Release VC before the next chapter's ASR/LLM competes for VRAM.
            # Within the chapter every converted turn shares one loaded model.
            self.converter.close()
            book_cursor = int(item.pop("_book_cursor", book_cursor))
            results.append(item)
            self._save_checkpoint(checkpoint_path, file_index, book_cursor, results)
            LOG.info("[PROGRESS] %.2f%% | capítulo %d/%d | %s | concluído", file_index * 100 / total_files,
                     file_index, total_files, path.name)
        report = summarize(results, self.hardware, {"hits": self.cache.hits, "misses": self.cache.misses},
                           time.monotonic() - started, "faster-whisper", self.converter.name)
        report["voice_conversion_timings"] = getattr(self.converter, "timings", [])
        report["resumed_chapters"] = next_index
        report["timing_note"] = "Tempos por capítulo incluem leituras de cache; capítulos retomados mantêm tempos históricos."
        if command == "analyze":
            imported = merge_detected_characters(self.characters_path, report,
                                                  float(self.config["speaker_confidence_threshold"]))
            report["character_import"] = imported
            if imported["added"]:
                LOG.info("Personagens adicionados automaticamente: %s", ", ".join(imported["added"]))
        analysis_only = command == "analyze" or dry_run
        write_reports(report, self.output, analysis_only=analysis_only)
        return report

    def _one(self, path: Path, *, command: str, language: str, book_blocks: list[str],
             book_fingerprint: dict[str, Any] | None, book_cursor: int, dry_run: bool,
             file_index: int, total_files: int) -> dict[str, Any]:
        stage_started = time.monotonic()
        stage_hits, stage_misses = self.cache.hits, self.cache.misses
        stage_timings = {}

        def mark_stage(name):
            nonlocal stage_started, stage_hits, stage_misses
            now = time.monotonic()
            stage_timings[name] = {"seconds": round(now - stage_started, 3),
                "cache_hits": self.cache.hits - stage_hits, "cache_misses": self.cache.misses - stage_misses}
            stage_started, stage_hits, stage_misses = now, self.cache.hits, self.cache.misses

        info = probe(path)
        fingerprint = self.cache.file_fingerprint(path)
        trans_key = self.cache.digest(fingerprint, self.config.get("transcription", {}), language, self.config.get("device"))
        def transcription_progress(percent: float, processed: float, duration: float) -> None:
            transcription_share = 0.75 if command == "process" and not dry_run else 0.95
            overall = ((file_index - 1) + (percent / 100) * transcription_share) * 100 / total_files
            LOG.info("[PROGRESS] %.2f%% | capítulo %d/%d | %s | transcrição %.1f%% (%s / %s)", overall,
                     file_index, total_files, path.name, percent, _clock(processed), _clock(duration))

        transcript = self.cache.json("transcription", trans_key,
                                     lambda: transcribe(path, self.config, language, transcription_progress))
        mark_stage("probe_and_transcription")
        alignments: list[dict[str, Any]] = []
        if book_blocks:
            align_key = self.cache.digest(ALIGNMENT_ALGORITHM_VERSION, trans_key, book_fingerprint,
                                          self.config.get("alignment", {}), book_cursor)
            alignments = self.cache.json("alignment", align_key, lambda: align_blocks(
                book_blocks, transcript, int(self.config.get("alignment", {}).get("block_window", 40)), book_cursor))
        mark_stage("alignment")
        dialogue_key = self.cache.digest(DIALOGUE_ALGORITHM_VERSION, trans_key, book_fingerprint,
                                         alignments, self.speaker_aliases)
        dialogues = self.cache.json("dialogue_detection", dialogue_key,
                                    lambda: detect(transcript, alignments, self.speaker_aliases, book_blocks))
        mark_stage("dialogue_detection")
        warnings: list[str] = []
        textual_analysis = None
        book_first = bool(self.config.get("book_first", {}).get("enabled", False) and book_blocks)
        llm_review: dict[str, Any] | None = None
        if book_first:
            model = getattr(self, "book_model", None) or build_book(book_blocks, self.speaker_aliases)
            positions = [int(item["book_paragraph_id"]) for item in alignments
                         if float(item.get("alignment_confidence", 0)) >= .5]
            if positions:
                scope = (min(positions), max(positions))
                options = self.config.get("book_first", {})
                reviewed = review_book(
                    model, self.llm, self.cache, scope,
                    threshold=float(options.get("automatic_confidence", .90)),
                    max_turns=int(options.get("max_turns_per_window", 24)),
                    max_chars=int(options.get("max_context_characters", 14000)),
                    protocol=options.get("protocol", "evidence"),
                    source_subjects=bool(options.get("source_subjects", False)),
                    scene_max_chars=int(options.get("scene_context_characters", 36000)),
                    scene_repair=bool(options.get("scene_repair", True)),
                    turn_consistency=bool(options.get("turn_consistency", True)),
                    progress=lambda index, total: LOG.info(
                        "[BOOK] %s | atribuição textual %d/%d", path.name, index, total))
                project_to_audio(reviewed, dialogues)
                textual_analysis = scoped_report(reviewed, scope)
                llm_review = reviewed.get("review")
                if llm_review and llm_review["errors"]:
                    warnings.append(f"Atribuição textual: {len(llm_review['errors'])} bloco(s) pendente(s)")
            else:
                project_to_audio(model, dialogues)
                warnings.append("Sem intervalo alinhado confiável; revisão contextual do livro não executada")
        apply_overrides(path, dialogues, self.root / "config" / "speaker_overrides.json")
        propagate_speaker_inside_turn(dialogues)
        if self.llm and book_blocks and not book_first:
            def llm_progress(position: int, total: int) -> None:
                overall = ((file_index - 1) + 0.95 + 0.04 * position / max(1, total)) * 100 / total_files
                LOG.info("[PROGRESS] %.2f%% | capítulo %d/%d | %s | IA contextual bloco %d/%d",
                         overall, file_index, total_files, path.name, position, total)

            llm_review = review_scenes(
                self.llm, self.cache, dialogues, book_blocks,
                self.book_characters | set(self.characters),
                float(self.config["speaker_confidence_threshold"]), llm_progress,
                float(self.config.get("llm", {}).get("automatic_confidence", 0.98)),
                bool(self.config.get("llm", {}).get("critic_enabled", True)),
                float(self.config.get("llm", {}).get("consensus_confidence", 0.90)),
            )
            if llm_review["errors"]:
                warnings.append(f"IA contextual falhou em {len(llm_review['errors'])} cena(s); falas foram preservadas")
            LOG.info("[LLM] %d atribuída(s), %d sugerida(s), %d sem solução em %.1fs",
                     llm_review["assigned"], llm_review["suggested_for_review"],
                     llm_review["unresolved"], llm_review["elapsed_seconds"])
            refine_speaker_sequence(dialogues, self.speaker_aliases)
        mark_stage("speaker_attribution")
        for dialogue in dialogues:
            self._eligibility(dialogue, bool(book_blocks))
        self._prevent_overlaps(dialogues)
        result: dict[str, Any] = {"input": str(path), "duration": info.duration, "sample_rate": info.sample_rate,
            "channels": info.channels, "codec": info.codec, "segments_analyzed": len(transcript.get("segments", [])),
            "dialogues": dialogues, "errors": [], "warnings": warnings, "final_duration": info.duration,
            "llm_review": llm_review, "stage_timings": stage_timings}
        if textual_analysis is not None:
            result["book_speaker_analysis"] = textual_analysis
        if book_blocks:
            inventory = getattr(self, "book_inventory", None)
            if inventory is None:
                inventory = dialogue_inventory(book_blocks)
            result["book_dialogue_coverage"] = audio_coverage(inventory, alignments, dialogues)
            coverage = result["book_dialogue_coverage"]
            LOG.info("[BOOK] %d/%d candidatos textuais localizados; %d não detectados no intervalo alinhado",
                     coverage["candidates_located"], coverage["candidates_in_scope"],
                     coverage["candidates_not_detected"])
        confident_ids = [int(item["book_paragraph_id"]) for item in alignments if item.get("alignment_confidence", 0) >= 0.5]
        result["_book_cursor"] = max(confident_ids, default=book_cursor) + (1 if confident_ids else 0)
        mark_stage("planning_and_coverage")
        if command == "analyze" or dry_run:
            for dialogue in dialogues:
                dialogue["action"] = "would_convert" if dialogue["eligible"] else "skipped"
            return result
        replacements: list[tuple[float, float, Path]] = []
        eligible_total = sum(bool(dialogue["eligible"]) for dialogue in dialogues)
        converted_progress = 0
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
            finally:
                converted_progress += 1
                phase = 0.75 + 0.20 * converted_progress / max(1, eligible_total)
                overall = ((file_index - 1) + phase) * 100 / total_files
                LOG.info("[PROGRESS] %.2f%% | capítulo %d/%d | %s | convertendo falas %d/%d", overall,
                         file_index, total_files, path.name, converted_progress, eligible_total)
        mark_stage("conversion_with_cuts_and_conforming")
        extension = "." + str(self.config.get("output", {}).get("format", "mp3")).lstrip(".")
        target = self.output / f"{path.stem} Enhanced{extension}"
        overall = ((file_index - 1) + 0.95) * 100 / total_files
        LOG.info("[PROGRESS] %.2f%% | capítulo %d/%d | %s | reconstruindo capítulo", overall,
                 file_index, total_files, path.name)
        reconstruct(path, replacements, target, str(self.config.get("output", {}).get("bitrate", "320k")))
        result["output"] = str(target)
        result["final_duration"] = probe(target).duration
        mark_stage("reconstruction_and_export")
        return result

    def _eligibility(self, dialogue: dict[str, Any], has_book: bool) -> None:
        reasons: list[str] = []
        speaker = dialogue.get("speaker")
        character = self.characters.get(speaker) if speaker else None
        dialogue["character_configured"] = character is not None
        if not speaker: reasons.append("speaker unidentified")
        elif not character: reasons.append("character not configured")
        # Figurante de uma cena so fica com a voz do narrador por decisao de
        # produto, nao por falha de identificacao. Configurar o papel na mao
        # continua valendo: a checagem acima ja deixou passar quem tem ficha.
        if dialogue.get("speaker_role") == "figurante" and not character:
            reasons.append("figurante de uma cena so")
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
        reference = Path(character["_resolved_voice_reference"])
        reference_fingerprint = self.voice_fingerprints.get(dialogue["speaker"]) or self.cache.file_fingerprint(reference)
        key = self.cache.digest(self.cache.file_fingerprint(source), dialogue, character,
                                reference_fingerprint, self.converter.name)
        final = self.cache.path("converted_audio", key, ".wav")
        if final.is_file():
            self.cache.hits += 1
            return final
        self.cache.misses += 1
        original = self.cache.path("converted_audio", key + "-original", ".wav")
        raw = self.cache.path("converted_audio", key + "-raw", ".wav")
        extract_segment(source, original, start, end)
        self.converter.convert(original, reference, raw, character)
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

    def _voice_fingerprints(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for name, item in self.characters.items():
            reference = item.get("_resolved_voice_reference")
            if reference and Path(reference).is_file():
                result[name] = self.cache.file_fingerprint(Path(reference))
        return result

    @staticmethod
    def _load_checkpoint(path: Path, command: str, dry_run: bool) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if int(data.get("next_index", -1)) != len(data.get("results", [])):
                return {}
            if command == "process" and not dry_run:
                outputs = [item.get("output") for item in data.get("results", [])]
                if any(not output or not Path(output).is_file() for output in outputs):
                    return {}
            LOG.info("Retomando checkpoint com %d capítulo(s) concluído(s)", data.get("next_index", 0))
            return data
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _save_checkpoint(path: Path, next_index: int, book_cursor: int, results: list[dict[str, Any]]) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"next_index": next_index, "book_cursor": book_cursor, "results": results},
                                        ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        LOG.info("Checkpoint salvo após o capítulo %d", next_index)


def _clock(seconds: float) -> str:
    seconds = max(0, round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
