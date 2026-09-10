import json
from pathlib import Path

import pytest

from audiobook_voice_enhancer.config import BOOK_PROTOCOLS, ConfigurationError, load_characters, load_config


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


def test_hybrid_book_protocol_is_accepted(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "speaker_confidence_threshold: 0.9\n"
        "alignment_confidence_threshold: 0.8\n"
        "voice_conversion:\n  worker_timeout_seconds: 600\n"
        "book_first:\n  enabled: true\n  protocol: hybrid\n",
        encoding="utf-8",
    )
    assert load_config(path)["book_first"]["protocol"] == "hybrid"


def test_all_configured_book_protocols_are_available_to_command_line_tools():
    assert "hybrid" in BOOK_PROTOCOLS


def test_hybrid_catalog_book_protocol_is_accepted(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "speaker_confidence_threshold: 0.85\n"
        "alignment_confidence_threshold: 0.8\n"
        "voice_conversion: {}\n"
        "book_first:\n  enabled: true\n  protocol: hybrid-catalog\n",
        encoding="utf-8",
    )
    assert load_config(path)["book_first"]["protocol"] == "hybrid-catalog"
    assert "hybrid-catalog" in BOOK_PROTOCOLS


@pytest.mark.parametrize('protocol,contract,valid', [
    ('hybrid', 'speaker-only', True), ('hybrid', 'catalog-schema', True),
    ('hybrid', 'catalog-prompt', True), ('compact', 'speaker-only', False),
    ('hybrid-catalog', 'catalog-schema', False), ('hybrid', 'typo', False)])
def test_experimental_contract_config_validation(tmp_path, protocol, contract, valid):
    import yaml
    config = {'speaker_confidence_threshold': .9, 'alignment_confidence_threshold': .8,
              'voice_conversion': {}, 'book_first': {'enabled': True, 'protocol': protocol,
                                                     'attribution_contract': contract}}
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump(config), encoding='utf-8')
    if valid:
        assert load_config(path)['book_first']['attribution_contract'] == contract
    else:
        with pytest.raises(ConfigurationError):
            load_config(path)
