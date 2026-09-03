from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from .models import AudioInfo

SUPPORTED = {".mp3", ".m4a", ".flac", ".wav", ".opus", ".ogg", ".aac"}


class AudioToolError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing:
        raise AudioToolError(f"Ferramentas ausentes no PATH: {', '.join(missing)}. Execute setup.bat.")


def natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.name)]


def discover_audio(source: Path, include: list[str] | None = None) -> list[Path]:
    if source.is_file() and source.suffix.lower() in SUPPORTED:
        return [source.resolve()]
    if source.is_dir():
        included = {name.casefold() for name in include} if include else None
        files = sorted((p.resolve() for p in source.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED
                        and (included is None or p.name.casefold() in included)), key=natural_key)
        if not files:
            raise AudioToolError("Nenhum arquivo de áudio selecionado foi encontrado na entrada.")
        return files
    raise AudioToolError(f"Entrada de áudio não encontrada ou não suportada: {source}")


def probe(path: Path) -> AudioInfo:
    require_ffmpeg()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format:stream", "-of", "json", str(path)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=flags)
    if proc.returncode:
        raise AudioToolError(f"ffprobe falhou para {path}: {proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    stream = next((item for item in data.get("streams", []) if item.get("codec_type") == "audio"), None)
    if not stream:
        raise AudioToolError(f"Nenhuma faixa de áudio encontrada: {path}")
    fmt = data.get("format", {})
    return AudioInfo(path, float(fmt.get("duration") or stream.get("duration") or 0), int(stream.get("sample_rate") or 0),
                     int(stream.get("channels") or 0), str(stream.get("codec_name") or "unknown"),
                     str(fmt.get("format_name") or "unknown"), dict(fmt.get("tags") or {}))


def extract_segment(source: Path, target: Path, start: float, end: float, sample_rate: int = 44100) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0, start):.6f}", "-to", f"{max(start, end):.6f}",
               "-i", str(source), "-vn", "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(target)]
    _run(command, "extração")


def conform_segment(converted: Path, original: Path, target: Path, duration: float, fade_ms: int) -> None:
    """Match duration/loudness to original and add short boundary fades."""
    target.parent.mkdir(parents=True, exist_ok=True)
    # loudnorm measured independently can over-amplify silence; RMS match is bounded to +/- 8 dB.
    import numpy as np
    import soundfile as sf
    converted_audio, sr = sf.read(converted, always_2d=True, dtype="float32")
    original_audio, original_sr = sf.read(original, always_2d=True, dtype="float32")
    if sr != original_sr:
        import subprocess
        tmp_path = converted.with_suffix('.resampled.wav')
        subprocess.run(["ffmpeg", "-y", "-i", str(converted), "-ar", str(original_sr), str(tmp_path)], capture_output=True, check=True)
        converted_audio, sr = sf.read(tmp_path, always_2d=True, dtype="float32")
        tmp_path.unlink(missing_ok=True)
    wanted = max(1, round(duration * sr))
    if len(converted_audio) != wanted:
        indices = np.linspace(0, max(0, len(converted_audio) - 1), wanted)
        converted_audio = np.vstack([np.interp(indices, np.arange(len(converted_audio)), converted_audio[:, channel])
                                     for channel in range(converted_audio.shape[1])]).T
    rms_source = float(np.sqrt(np.mean(np.square(original_audio), dtype=np.float64)))
    rms_target = float(np.sqrt(np.mean(np.square(converted_audio), dtype=np.float64)))
    if rms_target > 1e-7 and rms_source > 1e-7:
        gain = min(10 ** (8 / 20), max(10 ** (-8 / 20), rms_source / rms_target))
        converted_audio *= gain
    peak = float(np.max(np.abs(converted_audio))) if converted_audio.size else 0
    if peak > 0.98:
        converted_audio *= 0.98 / peak
    fade = min(round(fade_ms * sr / 1000), wanted // 3)
    if fade:
        converted_audio[:fade] *= np.linspace(0, 1, fade)[:, None]
        converted_audio[-fade:] *= np.linspace(1, 0, fade)[:, None]
    sf.write(target, converted_audio, sr, subtype="PCM_16")


def reconstruct(source: Path, replacements: list[tuple[float, float, Path]], target: Path, bitrate: str) -> None:
    """Mute exact original windows and mix same-length replacement files in one FFmpeg pass."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if not replacements:
        if source.suffix.casefold() == target.suffix.casefold():
            shutil.copy2(source, target)
        else:
            _run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-map", "0:a:0", "-map_metadata", "0",
                  *_encoder_args(target, bitrate), str(target)], "transcodificação")
        return
    command = ["ffmpeg", "-y", "-v", "error", "-i", str(source)]
    for _, _, replacement in replacements:
        command.extend(["-i", str(replacement)])
    mute = ",".join(f"volume=enable='between(t,{start:.6f},{end:.6f})':volume=0" for start, end, _ in replacements)
    graph = [f"[0:a]{mute}[base]"]
    mix_inputs = ["[base]"]
    for index, (start, _, _) in enumerate(replacements, 1):
        delay = max(0, round(start * 1000))
        graph.append(f"[{index}:a]adelay={delay}:all=1[r{index}]")
        mix_inputs.append(f"[r{index}]")
    graph.append("".join(mix_inputs) + f"amix=inputs={len(mix_inputs)}:duration=first:normalize=0[out]")
    command.extend(["-filter_complex", ";".join(graph), "-map", "[out]", "-map_metadata", "0", *_encoder_args(target, bitrate), str(target)])
    _run(command, "reconstrução")


def _encoder_args(target: Path, bitrate: str) -> list[str]:
    suffix = target.suffix.casefold()
    if suffix == ".mp3": return ["-c:a", "libmp3lame", "-b:a", bitrate]
    if suffix == ".m4a": return ["-c:a", "aac", "-b:a", bitrate]
    if suffix in {".opus", ".ogg"}: return ["-c:a", "libopus", "-b:a", bitrate]
    if suffix == ".flac": return ["-c:a", "flac"]
    if suffix == ".wav": return ["-c:a", "pcm_s16le"]
    raise AudioToolError(f"Formato de saída não suportado: {suffix}")


def _run(command: list[str], operation: str) -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=flags)
    if proc.returncode:
        raise AudioToolError(f"Falha na {operation}: {proc.stderr.strip()}")
