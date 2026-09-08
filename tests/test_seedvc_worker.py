from types import SimpleNamespace

import pytest

from audiobook_voice_enhancer.seedvc_worker import install_model_cache
from audiobook_voice_enhancer.voice_conversion import SeedVCConverter, VoiceConversionError


def test_model_loader_is_reused_and_rejects_configuration_change():
    calls = []
    module = SimpleNamespace(load_models=lambda args: calls.append(args) or object())
    install_model_cache(module)
    args = SimpleNamespace(checkpoint=None, config=None, fp16=True, f0_condition=False)
    assert module.load_models(args) is module.load_models(args)
    assert len(calls) == 1
    args.fp16 = False
    with pytest.raises(RuntimeError, match="restart"):
        module.load_models(args)


def test_real_worker_ipc_reuses_models_and_closes(tmp_path):
    # Real subprocess/IPC; tiny fake backend avoids GPU downloads/inference.
    (tmp_path / "inference.py").write_text('''
from pathlib import Path
import wave
def load_models(args):
    with open("loads.txt", "a") as f:
        f.write("load\\n")
    return object()
def main(args):
    load_models(args)
    print("backend progress")
    with wave.open(str(Path(args.output) / "test.wav"), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(24000)
        f.writeframes(b"\\0" * 4800)
''', encoding="utf-8")
    converter = SeedVCConverter(tmp_path, timeout=15)
    try:
        converter.convert(tmp_path / "source", tmp_path / "ref", tmp_path / "one.wav", {})
        process = converter._process
        converter.convert(tmp_path / "source2", tmp_path / "ref2", tmp_path / "two.wav", {})
        assert converter._process is process
        assert (tmp_path / "loads.txt").read_text().splitlines() == ["load"]
        assert [t["cold_start"] for t in converter.timings] == [True, False]
        assert (tmp_path / "two.wav").stat().st_size > 44
    finally:
        converter.close()
    assert process.poll() is not None
    converter.close()


def test_worker_timeout_cleans_up_process(tmp_path):
    (tmp_path / "inference.py").write_text("import time\ntime.sleep(20)\n", encoding="utf-8")
    converter = SeedVCConverter(tmp_path, timeout=.1)
    with pytest.raises(VoiceConversionError, match="tempo limite"):
        converter.convert(tmp_path / "source", tmp_path / "ref", tmp_path / "out.wav", {})
    assert converter._process is None
    assert converter._log is None


def test_worker_failure_does_not_accept_old_output(tmp_path):
    (tmp_path / "inference.py").write_text('''
def load_models(args): return object()
def main(args): raise RuntimeError("backend failed")
''', encoding="utf-8")
    output = tmp_path / "out.wav"
    output.write_bytes(b"old audio" * 20)
    converter = SeedVCConverter(tmp_path, timeout=15)
    with pytest.raises(VoiceConversionError, match="backend failed"):
        converter.convert(tmp_path / "source", tmp_path / "ref", output, {})
    assert converter._process is None


@pytest.mark.parametrize("error", [RuntimeError("failed"), KeyboardInterrupt()])
def test_pipeline_closes_converter_on_failure_or_interrupt(error):
    from audiobook_voice_enhancer.pipeline import Pipeline
    pipeline = Pipeline.__new__(Pipeline)
    closed = []
    pipeline.converter = SimpleNamespace(close=lambda: closed.append(True))

    def fail(*args, **kwargs):
        raise error

    pipeline._run = fail
    with pytest.raises(type(error)):
        pipeline.run(None, command="process", language="pt", book_text=None, dry_run=False)
    assert closed == [True]
