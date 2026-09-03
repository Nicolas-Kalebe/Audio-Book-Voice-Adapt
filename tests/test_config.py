import json
from pathlib import Path

import pytest

from audiobook_voice_enhancer.config import ConfigurationError, load_characters, load_config


def test_load_default_config():
    config = load_config(Path("config/config.yaml"))
    assert config["voice_conversion"]["backend"] == "auto"
    assert 0 <= config["speaker_confidence_threshold"] <= 1


def test_character_reference_required_in_convert_mode(tmp_path):
    path = tmp_path / "characters.json"
    path.write_text(json.dumps({"Ana": {"mode": "convert"}}), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="voice_reference"):
        load_characters(path, project_root=tmp_path)


def test_character_alias_cannot_belong_to_two_characters(tmp_path):
    path = tmp_path / "characters.json"
    path.write_text('{"Geralt":{"mode":"original","aliases":["bruxo"]},"Vesemir":{"mode":"original","aliases":["Bruxo"]}}', encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Alias"):
        load_characters(path, project_root=tmp_path)


def test_shared_reference_can_be_rejected(tmp_path):
    path = tmp_path / "characters.json"
    path.write_text(json.dumps({"Ana": {"mode": "convert", "voice_reference": "same.wav"},
                                "Bia": {"mode": "convert", "voice_reference": "same.wav"}}), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="compartilhada"):
        load_characters(path, project_root=tmp_path, allow_shared=False)


def test_convert_reference_must_exist_for_processing(tmp_path):
    path = tmp_path / "characters.json"
    path.write_text(json.dumps({"Vesemir": {"mode": "convert", "voice_reference": "missing.wav"}}), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="was not found"):
        load_characters(path, project_root=tmp_path, require_references=True)
