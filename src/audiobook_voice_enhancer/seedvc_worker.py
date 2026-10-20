"""Private JSON-lines worker. Runs in Seed-VC's Python, not the app environment.

Reuse the official inference function and memoize only its model loader. Do not
alter sampling, reference processing or audio quality. An incompatible checkout
fails explicitly; the configurable CLI mode remains available for comparison.
"""
from __future__ import annotations

import contextlib
import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from types import SimpleNamespace

PREFIX = "__ABVA_WORKER__"


def install_model_cache(module):
    loader = module.load_models
    loaded = {}

    def reuse(args):
        key = (args.checkpoint, args.config, args.fp16, args.f0_condition)
        if key not in loaded:
            if loaded:
                raise RuntimeError("Model settings changed; restart the Seed-VC worker")
            loaded[key] = loader(args)
        return loaded[key]

    module.load_models = reuse


def serve(root: Path):
    sys.path.insert(0, str(root.resolve()))
    module = None
    for line in sys.stdin:
        started = time.monotonic()
        try:
            request = json.loads(line)
            # Reserve stdout for IPC; libraries may print extensively during load.
            with contextlib.redirect_stdout(sys.stderr):
                if module is None:
                    module = importlib.import_module("inference")
                    install_model_cache(module)
                output = Path(request["output"])
                output.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix=".seedvc-", dir=output.parent) as staging:
                    args = SimpleNamespace(source=request["source"], target=request["reference"],
                        output=staging, diffusion_steps=int(request.get("diffusion_steps", 25)), length_adjust=1.0,
                        inference_cfg_rate=float(request.get("inference_cfg_rate", 0.7)),
                        f0_condition=bool(request.get("f0_condition", False)),
                        auto_f0_adjust=bool(request.get("auto_f0_adjust", False)),
                        semi_tone_shift=request["pitch_shift"], checkpoint=None, config=None, fp16=True)
                    module.main(args)
                    candidates = list(Path(staging).glob("*.wav"))
                    if len(candidates) != 1 or candidates[0].stat().st_size <= 44:
                        raise RuntimeError("Seed-VC must produce exactly one nonempty WAV")
                    shutil.copy2(candidates[0], output)
            response = {"ok": True, "seconds": time.monotonic() - started}
        except Exception as exc:
            response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        print(PREFIX + json.dumps(response, ensure_ascii=True), flush=True)
        if not response["ok"]:
            break  # Never reuse partially failed model/GPU state.


if __name__ == "__main__":
    serve(Path(sys.argv[1]))
