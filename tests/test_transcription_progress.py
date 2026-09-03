import sys
from types import SimpleNamespace

from audiobook_voice_enhancer import transcription


def test_transcription_reports_periodic_progress(monkeypatch, tmp_path):
    class Model:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, *args, **kwargs):
            segments = [
                SimpleNamespace(start=0.0, end=5.0, text=" início", words=[]),
                SimpleNamespace(start=50.0, end=55.0, text=" meio", words=[]),
            ]
            return iter(segments), SimpleNamespace(duration=100.0, language="pt", language_probability=0.99)

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
    monkeypatch.setattr(transcription, "detect_hardware", lambda: {"cuda_available": False})
    values = []
    result = transcription.transcribe(tmp_path / "chapter.mp3", {
        "device": "cpu", "transcription": {"model": "tiny", "compute_type": "int8"}
    }, "pt", lambda percent, processed, duration: values.append((percent, processed, duration)))
    assert result["segments"][1]["text"] == "meio"
    assert values[0] == (5.0, 5.0, 100.0)
    assert values[-1] == (100.0, 100.0, 100.0)
