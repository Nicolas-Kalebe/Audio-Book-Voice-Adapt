import json

from audiobook_voice_enhancer.character_discovery import discover_characters, merge_detected_characters


def report(*dialogues):
    return {"files": [{"dialogues": list(dialogues)}]}


def test_discovery_keeps_named_speakers_and_marks_low_confidence():
    found = discover_characters(report(
        {"speaker": "Vesemir", "speaker_confidence": 0.98},
        {"speaker": "Ciri", "speaker_confidence": 0.72},
        {"speaker": "ele", "speaker_confidence": 0.98},
        {"speaker": None, "speaker_confidence": 0},
    ))
    assert set(found) == {"Ciri", "Vesemir"}
    assert found["Vesemir"]["review_required"] is False
    assert found["Ciri"]["review_required"] is True


def test_merge_adds_safe_default_and_preserves_existing_settings(tmp_path):
    path = tmp_path / "characters.json"
    path.write_text(json.dumps({"__narrator__": {"mode": "original"}, "Geralt": {"mode": "convert", "voice_reference": "geralt.wav"}}), encoding="utf-8")
    result = merge_detected_characters(path, report(
        {"speaker": "Geralt", "speaker_confidence": 0.98},
        {"speaker": "Vesemir", "speaker_confidence": 0.98},
    ))
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert result["added"] == ["Vesemir"]
    assert saved["Vesemir"]["mode"] == "original"
    assert saved["Geralt"]["mode"] == "convert"
    assert saved["Geralt"]["voice_reference"] == "geralt.wav"


def test_merge_matches_existing_names_without_changing_case(tmp_path):
    path = tmp_path / "characters.json"
    path.write_text(json.dumps({"GERALT": {"mode": "original"}}), encoding="utf-8")
    result = merge_detected_characters(path, report({"speaker": "Geralt", "speaker_confidence": 0.98}))
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert result["added"] == []
    assert set(saved) == {"GERALT"}
