import json

import yaml

from audiobook_voice_enhancer.gui import (ROOT, atomic_json, atomic_yaml, character_speech_stats,
                                           relative_to_root, resolve_voice_reference, voice_file_options)


def test_gui_atomic_config_writers(tmp_path):
    json_path = tmp_path / "characters.json"
    yaml_path = tmp_path / "config.yaml"
    atomic_json(json_path, {"Vesemir": {"mode": "original"}})
    atomic_yaml(yaml_path, {"device": "auto", "output": {"format": "mp3"}})
    assert json.loads(json_path.read_text(encoding="utf-8"))["Vesemir"]["mode"] == "original"
    assert yaml.safe_load(yaml_path.read_text(encoding="utf-8"))["device"] == "auto"


def test_gui_relative_path_for_project_file():
    assert relative_to_root(ROOT / "voices" / "test.wav") == "voices/test.wav"


def test_gui_resolves_character_voice_from_project_root(tmp_path):
    assert resolve_voice_reference(tmp_path, {"voice_reference": "voices/test.wav"}) == \
        (tmp_path / "voices" / "test.wav").resolve()
    assert resolve_voice_reference(tmp_path, {}) is None


def test_character_speech_stats_excludes_unknown_and_calculates_weight():
    stats = character_speech_stats({"characters_detected": {"Ciri": 30, "Geralt": 20, "unknown": 50}})
    assert stats["ciri"] == (30, 0.6)
    assert stats["geralt"] == (20, 0.4)
    assert "unknown" not in stats


def test_voice_file_options_lists_supported_files_by_name(tmp_path):
    voices = tmp_path / "voices"
    voices.mkdir()
    (voices / "Yennefer.wav").write_bytes(b"wav")
    (voices / "ciri.mp3").write_bytes(b"mp3")
    (voices / "notes.txt").write_text("ignore", encoding="utf-8")
    assert voice_file_options(tmp_path) == {
        "ciri.mp3": "voices/ciri.mp3",
        "Yennefer.wav": "voices/Yennefer.wav",
    }
