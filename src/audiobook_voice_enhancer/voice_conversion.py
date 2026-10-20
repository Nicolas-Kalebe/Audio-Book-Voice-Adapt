from __future__ import annotations

import shutil
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
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

    def close(self) -> None:
        """Release session resources, including GPU memory."""


class SeedVCConverter(VoiceConverter):
    name = "seedvc"

    # Padrões de sempre: modelo de fala de 22 kHz, sem controle de tom.
    DEFAULTS = {"diffusion_steps": 25, "inference_cfg_rate": 0.7, "f0_condition": False, "auto_f0_adjust": False}

    def __init__(self, root: Path, *, persistent: bool = True, timeout: float = 600,
                 settings: dict[str, Any] | None = None):
        self.root = root.resolve()
        self.persistent, self.timeout = persistent, timeout
        self.settings = {**self.DEFAULTS, **{k: v for k, v in (settings or {}).items() if k in self.DEFAULTS}}
        # O nome entra na chave do cache de áudio convertido: ajuste novo não reaproveita conversão velha.
        if self.settings != self.DEFAULTS:
            self.name = "seedvc[" + ",".join(f"{k}={v}" for k, v in sorted(self.settings.items())) + "]"
        self._process = None
        self._log = None
        self.timings: list[dict] = []

    def available(self) -> bool:
        return (self.root / "inference.py").is_file()

    def convert(self, source: Path, reference: Path, output: Path, character: dict[str, Any]) -> None:
        if not self.available():
            raise VoiceConversionError(f"Seed-VC não instalado em {self.root}; execute setup_seedvc.bat")
        if self.persistent:
            self._convert_persistent(source, reference, output, character)
            return
        self._convert_cli(source, reference, output, character)

    def _start(self):
        private_python = self.root / ".venv" / "Scripts" / "python.exe"
        python = str(private_python) if private_python.is_file() else sys.executable
        self._log = tempfile.TemporaryFile(mode="w+b")
        try:
            self._process = subprocess.Popen(
                [python, "-u", str(Path(__file__).with_name("seedvc_worker.py")), str(self.root)],
                cwd=self.root, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._log,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            self._log.close()
            self._log = None
            raise
        responses = self._responses = queue.Queue()
        stream = self._process.stdout

        def read_responses():
            try:
                for line in stream:
                    if line.startswith("__ABVA_WORKER__"):
                        responses.put(json.loads(line[len("__ABVA_WORKER__"):]))
            except Exception as exc:
                responses.put({"ok": False, "error": str(exc)})
            finally:
                responses.put({"ok": False, "error": "Worker encerrou sem resposta"})

        self._reader = threading.Thread(target=read_responses, daemon=True)
        self._reader.start()

    def _convert_persistent(self, source, reference, output, character):
        started = time.monotonic()
        cold = self._process is None
        try:
            if cold:
                self._start()
            request = {"source": str(source.resolve()), "reference": str(reference.resolve()),
                       "output": str(output.resolve()), "pitch_shift": int(float(character.get("pitch_shift", 0))),
                       **self.settings}
            self._process.stdin.write(json.dumps(request, ensure_ascii=True) + "\n")
            self._process.stdin.flush()
            response = self._responses.get(timeout=self.timeout)
            if not response.get("ok") or not output.is_file() or output.stat().st_size <= 44:
                raise VoiceConversionError(response.get("error", "Worker não produziu WAV válido"))
            self.timings.append({"cold_start": cold, "elapsed_seconds": time.monotonic() - started,
                                 "worker_seconds": response.get("seconds")})
        except BaseException as exc:
            detail = ""
            if self._log:
                self._log.seek(0, 2)
                self._log.seek(max(0, self._log.tell() - 2000))
                detail = self._log.read().decode("utf-8", errors="replace")
            self.close()
            if not isinstance(exc, Exception):
                raise
            reason = f"tempo limite de {self.timeout}s excedido" if isinstance(exc, queue.Empty) else str(exc)
            raise VoiceConversionError(f"Seed-VC worker: {reason}\n{detail}") from exc

    def close(self):
        process, self._process = self._process, None
        if process:
            try:
                process.stdin.close()
            except (OSError, ValueError):
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            self._reader.join(timeout=2)
            process.stdout.close()
        if self._log:
            self._log.close()
            self._log = None

    def _convert_cli(self, source, reference, output, character):
        staging = output.parent / f".{output.stem}-seedvc"
        staging.mkdir(parents=True, exist_ok=True)
        private_python = self.root / ".venv" / "Scripts" / "python.exe"
        python = str(private_python) if private_python.is_file() else sys.executable
        command = [python, str(self.root / "inference.py"), "--source", str(source.resolve()), "--target",
                   str(reference.resolve()), "--output", str(staging.resolve()), "--diffusion-steps",
                   str(self.settings["diffusion_steps"]), "--length-adjust", "1.0", "--inference-cfg-rate",
                   str(self.settings["inference_cfg_rate"]), "--f0-condition", str(bool(self.settings["f0_condition"])),
                   "--auto-f0-adjust", str(bool(self.settings["auto_f0_adjust"])), "--semi-tone-shift", str(int(float(character.get("pitch_shift", 0)))), "--fp16", "True"]
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
        "seedvc": SeedVCConverter(root / vc.get("seedvc_path", "models/seed-vc"),
                                 persistent=bool(vc.get("persistent_worker", True)),
                                 timeout=float(vc.get("worker_timeout_seconds", 600)),
                                 settings=vc.get("seedvc", {})),
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
