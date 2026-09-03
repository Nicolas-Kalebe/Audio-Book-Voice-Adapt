from __future__ import annotations

from pathlib import Path
from typing import Any
import os

from .hardware import detect_hardware


def transcribe(path: Path, config: dict[str, Any], language: str = "auto") -> dict[str, Any]:
    # On Windows, expose CUDA/cuDNN DLLs bundled in the PyTorch wheel to CTranslate2.
    if os.name == "nt":
        try:
            import torch
            torch_lib = Path(torch.__file__).parent / "lib"
            site_packages = Path(torch.__file__).parent.parent
            candidates = [torch_lib, site_packages / "nvidia" / "cublas" / "bin",
                          site_packages / "nvidia" / "cudnn" / "bin",
                          site_packages / "nvidia" / "cuda_nvrtc" / "bin"]
            dll_dirs = [str(item) for item in candidates if item.is_dir()]
            for item in dll_dirs:
                os.add_dll_directory(item)
            if dll_dirs:
                os.environ["PATH"] = os.pathsep.join(dll_dirs + [os.environ.get("PATH", "")])
        except (ImportError, OSError):
            pass
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper não está instalado. Execute setup.bat.") from exc
    hardware = detect_hardware()
    requested = config.get("device", "auto")
    device = "cuda" if requested == "cuda" or (requested == "auto" and hardware["cuda_available"]) else "cpu"
    trans_cfg = config.get("transcription", {})
    compute = trans_cfg.get("compute_type", "float16") if device == "cuda" else "int8"
    model = WhisperModel(trans_cfg.get("model", "large-v3"), device=device, compute_type=compute)
    segments, info = model.transcribe(str(path), language=None if language == "auto" else language,
                                      beam_size=int(trans_cfg.get("beam_size", 5)),
                                      vad_filter=bool(trans_cfg.get("vad_filter", True)), word_timestamps=True)
    output = []
    for index, segment in enumerate(segments):
        words = [{"word": word.word.strip(), "start": word.start, "end": word.end, "probability": word.probability}
                 for word in (segment.words or []) if word.start is not None and word.end is not None]
        output.append({"id": index, "start": segment.start, "end": segment.end, "text": segment.text.strip(), "words": words})
    return {"language": info.language, "language_probability": info.language_probability, "device": device,
            "model": trans_cfg.get("model", "large-v3"), "segments": output}
