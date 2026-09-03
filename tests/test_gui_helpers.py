import json

import yaml

from audiobook_voice_enhancer.gui import ROOT, atomic_json, atomic_yaml, relative_to_root, resolve_voice_reference


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
