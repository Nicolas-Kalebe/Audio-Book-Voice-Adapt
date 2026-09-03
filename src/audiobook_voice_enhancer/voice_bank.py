from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .audio import probe, require_ffmpeg


VOICE_BANK_VERSION = "resemblyzer-v4-reviewed-clips"


class VoiceBankError(RuntimeError):
    pass


def _run(command: list[str], label: str) -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             creationflags=flags)
    if process.returncode:
        raise VoiceBankError(f"{label} falhou: {(process.stderr or process.stdout).strip()[-2000:]}")
    if process.stdout.strip():
        print(process.stdout.strip(), flush=True)


def _session_key(source: Path, start: float, duration: float, speakers: int, cleanup: bool) -> str:
    stat = source.stat()
    value = f"{VOICE_BANK_VERSION}|{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{start}|{duration}|{speakers}|{cleanup}"
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def _speech_chunks(audio: np.ndarray, sample_rate: int) -> list[dict[str, Any]]:
    try:
        from faster_whisper.vad import VadOptions, get_speech_timestamps
    except ImportError as exc:
        raise VoiceBankError("faster-whisper não está instalado; execute setup.bat") from exc
    timestamps = get_speech_timestamps(audio, VadOptions(threshold=0.55, min_speech_duration_ms=950,
                                       max_speech_duration_s=4, min_silence_duration_ms=180,
                                       speech_pad_ms=50), sampling_rate=sample_rate)
    chunks: list[dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps):
        start_sample, end_sample = int(timestamp["start"]), int(timestamp["end"])
        duration = (end_sample - start_sample) / sample_rate
        if duration < 0.9:
            continue
        sample = audio[start_sample:end_sample]
        rms = float(np.sqrt(np.mean(np.square(sample), dtype=np.float64))) if sample.size else 0.0
        clipping = float(np.mean(np.abs(sample) >= 0.985)) if sample.size else 1.0
        # Longer, audible and non-clipped excerpts are better references.
        duration_score = min(1.0, duration / 2.5)
        volume_score = min(1.0, rms / 0.045)
        quality = duration_score * 0.55 + volume_score * 0.35 + max(0.0, 1 - clipping * 50) * 0.10
        chunks.append({"id": index, "start": round(start_sample / sample_rate, 4),
                       "end": round(end_sample / sample_rate, 4), "duration": round(duration, 4),
                       "rms": round(rms, 6), "clipping": round(clipping, 6),
                       "quality": round(quality, 4)})
    return chunks


def _montage(source_wav: Path, segments: list[dict[str, Any]], target: Path,
             target_seconds: float) -> float:
    audio, sample_rate = sf.read(source_wav, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    pieces: list[np.ndarray] = []
    accumulated = 0.0
    silence = np.zeros(round(sample_rate * 0.12), dtype=np.float32)
    for segment in segments:
        if accumulated >= target_seconds:
            break
        start = max(0, round(float(segment["start"]) * sample_rate))
        end = min(len(audio), round(float(segment["end"]) * sample_rate))
        piece = np.asarray(audio[start:end], dtype=np.float32).copy()
        remaining = target_seconds - accumulated
        if len(piece) / sample_rate > remaining:
            piece = piece[:round(remaining * sample_rate)]
        fade = min(round(sample_rate * 0.02), len(piece) // 3)
        if fade:
            piece[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
            piece[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
        if pieces:
            pieces.append(silence)
        pieces.append(piece)
        accumulated += len(piece) / sample_rate
    if not pieces or accumulated < 1:
        raise VoiceBankError("A voz selecionada não possui áudio útil suficiente")
    combined = np.concatenate(pieces)
    peak = float(np.max(np.abs(combined)))
    if peak > 0.98:
        combined *= 0.98 / peak
    target.parent.mkdir(parents=True, exist_ok=True)
    sf.write(target, combined, sample_rate, subtype="PCM_16")
    return round(accumulated, 3)


def analyze_voice_source(root: Path, source: Path, cache_root: Path, *, start: float = 0,
                         duration: float = 600, speakers: int = 0, cleanup: bool = True) -> Path:
    root, source, cache_root = root.resolve(), source.resolve(), cache_root.resolve()
    if not source.is_file():
        raise VoiceBankError(f"Áudio não encontrado: {source}")
    if not 0 <= speakers <= 12:
        raise VoiceBankError("O número de vozes deve ficar entre automático e 12")
    info = probe(source)
    start = min(max(0.0, start), max(0.0, info.duration - 0.1))
    duration = min(max(10.0, duration), 3600.0, max(0.1, info.duration - start))
    session = cache_root / _session_key(source, start, duration, speakers, cleanup)
    manifest_path = session / "manifest.json"
    if manifest_path.is_file():
        print(f"[VOICE_BANK] análise restaurada do cache: {manifest_path}", flush=True)
        return manifest_path
    session.mkdir(parents=True, exist_ok=True)
    normalized = session / "source-16k.wav"
    require_ffmpeg()
    print("[VOICE_BANK] preparando áudio...", flush=True)
    command = ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.4f}", "-t", f"{duration:.4f}",
               "-i", str(source), "-vn", "-ac", "1", "-ar", "16000"]
    if cleanup:
        # Conservative speech-band cleanup: attenuates rumble/hiss and tracks
        # steady background noise without aggressively changing vocal timbre.
        command.extend(["-af", "highpass=f=70,lowpass=f=7600,afftdn=nr=8:nf=-45:tn=1"])
    command.extend(["-c:a", "pcm_s16le", str(normalized)])
    _run(command, "Preparação do áudio")
    audio, sample_rate = sf.read(normalized, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    print("[VOICE_BANK] detectando trechos com fala...", flush=True)
    chunks = _speech_chunks(audio, sample_rate)
    if not chunks:
        raise VoiceBankError("Nenhuma fala clara foi encontrada no intervalo selecionado")
    # Bound analysis time while retaining the best material spread through the file.
    if len(chunks) > 300:
        ranked = sorted(chunks, key=lambda item: item["quality"], reverse=True)[:300]
        chunks = sorted(ranked, key=lambda item: item["start"])
    chunks_path = session / "chunks.json"
    chunks_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    seed_root = root / "models" / "seed-vc"
    seed_python = seed_root / ".venv" / "Scripts" / "python.exe"
    if not seed_python.is_file():
        raise VoiceBankError("O ambiente do Seed-VC não foi encontrado; execute setup_seedvc.bat")
    embedded_path = session / "embedded.json"
    helper = Path(__file__).with_name("speaker_embedder.py").resolve()
    print(f"[VOICE_BANK] reconhecendo e agrupando {len(chunks)} trechos...", flush=True)
    command = [str(seed_python), str(helper), str(normalized), str(chunks_path), str(embedded_path)]
    if speakers:
        command.extend(["--speakers", str(speakers)])
    _run(command, "Reconhecimento de vozes")
    embedded = json.loads(embedded_path.read_text(encoding="utf-8"))
    grouped: dict[int, list[dict[str, Any]]] = {}
    for item in embedded:
        grouped.setdefault(int(item["cluster"]), []).append(item)
    ordered = sorted(grouped.values(), key=lambda values: sum(float(item["duration"]) for item in values), reverse=True)
    voices = []
    for display_index, values in enumerate(ordered, 1):
        ranked = sorted(values, key=lambda item: (float(item["quality"]) * 0.35 +
                                                  float(item["similarity"]) * 0.30 +
                                                  float(item.get("purity", 0)) * 0.35), reverse=True)
        cohesion = sum(float(item["similarity"]) for item in values) / len(values)
        candidates = []
        for candidate_index, item in enumerate(ranked[:12], 1):
            candidate = dict(item)
            candidate["id"] = f"voice-{display_index:02d}-clip-{candidate_index:02d}"
            purity_limit = 0.68 if candidate.get("purity_verified") else 0.0
            candidate["included"] = (float(candidate["duration"]) >= 1.5 and
                                     float(candidate.get("purity", 0)) >= purity_limit and
                                     float(candidate["similarity"]) >= max(0.70, cohesion - 0.12))
            clip_preview = session / f"{candidate['id']}.wav"
            _montage(normalized, [candidate], clip_preview, float(candidate["duration"]))
            candidate["preview"] = str(clip_preview)
            candidates.append(candidate)
        if candidates and not any(item["included"] for item in candidates):
            candidates[0]["included"] = True
        preview = session / f"voice-{display_index:02d}-preview.wav"
        included = [item for item in candidates if item["included"]]
        preview_duration = _montage(normalized, included[:4], preview, 12)
        useful_duration = sum(float(item["duration"]) for item in values)
        voices.append({"id": f"voice-{display_index:02d}", "label": f"Voz {display_index}",
                       "segments": ranked, "candidates": candidates, "segment_count": len(values),
                       "useful_duration": round(useful_duration, 2), "preview_duration": preview_duration,
                       "cohesion": round(cohesion, 4), "preview": str(preview)})
    manifest = {"version": VOICE_BANK_VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
                "source": str(source), "source_start": start, "analyzed_duration": duration,
                "normalized_audio": str(normalized), "requested_speakers": speakers,
                "light_cleanup": cleanup, "voices": voices}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[VOICE_BANK] concluído: {len(voices)} vozes encontradas", flush=True)
    return manifest_path


def save_voice(root: Path, manifest_path: Path, voice_id: str, name: str,
               characters_path: Path, *, replace: bool = False) -> Path:
    root, manifest_path = root.resolve(), manifest_path.resolve()
    name = " ".join(name.split())
    if not name or name.startswith("__"):
        raise VoiceBankError("Informe um nome válido para a voz/personagem")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    voice = next((item for item in manifest.get("voices", []) if item.get("id") == voice_id), None)
    if not voice:
        raise VoiceBankError(f"Voz não encontrada no resultado: {voice_id}")
    slug = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_") or "voice"
    target = root / "voices" / f"{slug}_ref.wav"
    if target.exists() and not replace:
        raise VoiceBankError(f"A referência já existe: {target.name}. Confirme a substituição na interface.")
    candidates = voice.get("candidates", voice.get("segments", []))
    approved = [item for item in candidates if item.get("included", True)]
    if not approved:
        raise VoiceBankError("Todos os trechos dessa voz foram excluídos; inclua pelo menos um")
    temporary_audio = target.with_name(f".{target.stem}.tmp.wav")
    duration = _montage(Path(manifest["normalized_audio"]), approved, temporary_audio, 25)
    temporary_audio.replace(target)
    characters = json.loads(characters_path.read_text(encoding="utf-8")) if characters_path.is_file() else {}
    name = next((existing for existing in characters if existing.casefold() == name.casefold()), name)
    current = dict(characters.get(name, {}))
    current.update({"mode": "convert", "voice_reference": str(target.relative_to(root)).replace("\\", "/"),
                    "voice_bank": {"source": Path(manifest["source"]).name, "voice_id": voice_id,
                                   "reference_seconds": duration, "cohesion": voice["cohesion"]}})
    characters[name] = current
    characters_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = characters_path.with_suffix(characters_path.suffix + ".tmp")
    temporary.write_text(json.dumps(characters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(characters_path)
    print(f"[VOICE_BANK] {name} salvo em {target} ({duration:.1f}s)", flush=True)
    return target
