from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any


def detect_hardware() -> dict[str, Any]:
    report: dict[str, Any] = {
        "cuda_available": False,
        "gpu": None,
        "vram_gb": None,
        "driver": None,
        "torch_version": None,
        "torch_cuda": None,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
    }
    if shutil.which("nvidia-smi"):
        try:
            raw = subprocess.check_output([
                "nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"
            ], text=True, timeout=10, stderr=subprocess.STDOUT).strip().splitlines()[0]
            name, memory, driver = [part.strip() for part in raw.split(",", 2)]
            report.update(gpu=name, vram_gb=round(float(memory) / 1024, 1), driver=driver)
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            pass
    try:
        import torch
        report["torch_version"] = torch.__version__
        report["torch_cuda"] = torch.version.cuda
        report["cuda_available"] = bool(torch.cuda.is_available())
        if report["cuda_available"] and not report["gpu"]:
            report["gpu"] = torch.cuda.get_device_name(0)
            report["vram_gb"] = round(torch.cuda.get_device_properties(0).total_memory / 2**30, 1)
    except ImportError:
        pass
    try:
        import ctranslate2
        report["ctranslate2_cuda_types"] = sorted(ctranslate2.get_supported_compute_types("cuda"))
    except Exception as exc:
        report["ctranslate2_cuda_types"] = []
        report["ctranslate2_error"] = str(exc)
    return report


def print_hardware_report() -> int:
    data = detect_hardware()
    print(f"CUDA: {'AVAILABLE' if data['cuda_available'] else 'UNAVAILABLE'}")
    print(f"GPU: {data['gpu'] or 'not detected'}")
    print(f"VRAM: {data['vram_gb']} GB" if data["vram_gb"] else "VRAM: unknown")
    print(f"NVIDIA driver: {data['driver'] or 'not detected'}")
    print(f"PyTorch: {data['torch_version'] or 'not installed'}")
    print(f"PyTorch CUDA: {data['torch_cuda'] or 'DISABLED'}")
    print(f"CTranslate2 CUDA types: {', '.join(data.get('ctranslate2_cuda_types', [])) or 'unavailable'}")
    print(f"FFmpeg/FFprobe: {'AVAILABLE' if data['ffmpeg'] and data['ffprobe'] else 'MISSING'}")
    print(f"Transcription backend: {'GPU' if data['cuda_available'] else 'CPU fallback'}")
    print(f"Voice Conversion backend: {'GPU' if data['cuda_available'] else 'CPU fallback / backend dependent'}")
    if not data["cuda_available"]:
        print("WARNING: PyTorch CUDA não está disponível; o processamento será muito mais lento.")
    if not data["ffmpeg"] or not data["ffprobe"]:
        print("WARNING: instale FFmpeg e adicione ffmpeg/ffprobe ao PATH.")
    return 0


if __name__ == "__main__":
    print(json.dumps(detect_hardware(), indent=2))
