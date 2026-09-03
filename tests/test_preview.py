import json

from audiobook_voice_enhancer import preview
from audiobook_voice_enhancer.models import AudioInfo


def test_preview_generates_matching_original_and_converted(monkeypatch, tmp_path):
    source = tmp_path / "chapter.mp3"
    source.write_bytes(b"audio")
    reference = tmp_path / "voice.wav"
    reference.write_bytes(b"voice")
    config = tmp_path / "config.yaml"
    config.write_text("speaker_confidence_threshold: 0.85\nalignment_confidence_threshold: 0.8\nvoice_conversion:\n  backend: auto\n", encoding="utf-8")
    characters = tmp_path / "characters.json"
    characters.write_text(json.dumps({"Geralt": {"mode": "original", "voice_reference": "voice.wav"}}), encoding="utf-8")

    class Converter:
        def convert(self, original, selected_reference, raw, character):
            assert selected_reference == reference
            raw.write_bytes(b"converted raw")

    monkeypatch.setattr(preview, "probe", lambda path: AudioInfo(path, 120, 44100, 2, "mp3", "mp3", {}))
    monkeypatch.setattr(preview, "extract_segment", lambda source, target, start, end: target.write_bytes(b"original"))
    monkeypatch.setattr(preview, "select_converter", lambda config, root: Converter())
    monkeypatch.setattr(preview, "conform_segment", lambda raw, original, target, duration, fade: target.write_bytes(b"converted"))
    result = preview.generate_preview(tmp_path, source, "Geralt", config, characters, tmp_path / "previews", 10, 20)
    assert result["original"].read_bytes() == b"original"
    assert result["converted"].read_bytes() == b"converted"
