from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


class VoiceConversionError(RuntimeError):
    pass


class VoiceConverter:
    name = "base"

    def available(self) -> bool:
        raise NotImplementedError

    def convert(self, source: Path, reference: Path, output: Path, character: dict[str, Any]) -> None:
        raise NotImplementedError


class SeedVCConverter(VoiceConverter):
    name = "seedvc"

    def __init__(self, root: Path):
        self.root = root.resolve()

    def available(self) -> bool:
        return (self.root / "inference.py").is_file()

    def convert(self, source: Path, reference: Path, output: Path, character: dict[str, Any]) -> None:
        if not self.available():
            raise VoiceConversionError(f"Seed-VC não instalado em {self.root}; execute setup_seedvc.bat")
        staging = output.parent / f".{output.stem}-seedvc"
        staging.mkdir(parents=True, exist_ok=True)
        private_python = self.root / ".venv" / "Scripts" / "python.exe"
        python = str(private_python) if private_python.is_file() else sys.executable
        command = [python, str(self.root / "inference.py"), "--source", str(source.resolve()), "--target",
                   str(reference.resolve()), "--output", str(staging.resolve()), "--diffusion-steps", "25",
                   "--length-adjust", "1.0", "--inference-cfg-rate", "0.7", "--f0-condition", "False",
                   "--auto-f0-adjust", "False", "--semi-tone-shift", str(character.get("pitch_shift", 0)), "--fp16", "True"]
        proc = subprocess.run(command, cwd=self.root, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if proc.returncode:
            raise VoiceConversionError(f"Seed-VC falhou: {proc.stderr[-2000:] or proc.stdout[-2000:]}")
        candidates = sorted(staging.rglob("*.wav"), key=lambda item: item.stat().st_mtime, reverse=True)
        if not candidates:
            raise VoiceConversionError("Seed-VC terminou sem produzir WAV")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidates[0], output)


class OpenVoiceConverter(VoiceConverter):
    name = "openvoice"
    def __init__(self, root: Path): self.root = root.resolve()
    def available(self) -> bool: return (self.root / "openvoice").is_dir()
    def convert(self, source: Path, reference: Path, output: Path, character: dict[str, Any]) -> None:
        raise VoiceConversionError("OpenVoice exige checkpoints e um extrator de embedding específicos; use Seed-VC ou configure uma integração externa.")


class RVCConverter(VoiceConverter):
    name = "rvc"
    def __init__(self, root: Path): self.root = root.resolve()
    def available(self) -> bool: return (self.root / "infer" / "cli.py").is_file()
    def convert(self, source: Path, reference: Path, output: Path, character: dict[str, Any]) -> None:
        model = character.get("voice_model")
        if not model or not Path(str(model)).is_file():
            raise VoiceConversionError("RVC requer voice_model apontando para um modelo .pth treinado; a referência curta não é suficiente.")
        command = [sys.executable, str(self.root / "infer" / "cli.py"), "--model", str(Path(model).resolve()),
                   "--input", str(source.resolve()), "--output", str(output.resolve()), "--format", "wav",
                   "--pitch", str(character.get("pitch_shift", 0)), "--f0-method", "rmvpe", "--index-rate", "0"]
        proc = subprocess.run(command, cwd=self.root, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if proc.returncode or not output.is_file():
            raise VoiceConversionError(f"RVC falhou: {proc.stderr[-2000:] or proc.stdout[-2000:]}")


def select_converter(config: dict[str, Any], root: Path) -> VoiceConverter:
    vc = config.get("voice_conversion", {})
    choices: dict[str, VoiceConverter] = {
        "seedvc": SeedVCConverter(root / vc.get("seedvc_path", "models/seed-vc")),
        "openvoice": OpenVoiceConverter(root / vc.get("openvoice_path", "models/OpenVoice")),
        "rvc": RVCConverter(root / vc.get("rvc_path", "models/Retrieval-based-Voice-Conversion-WebUI")),
    }
    requested = str(vc.get("backend", "auto")).lower()
    if requested != "auto":
        if requested not in choices:
            raise VoiceConversionError(f"Backend desconhecido: {requested}")
        return choices[requested]
    # Seed-VC is the only zero-shot speech-to-speech backend in the supported set.
    for name in ("seedvc", "openvoice", "rvc"):
        if choices[name].available():
            return choices[name]
    return choices["seedvc"]
