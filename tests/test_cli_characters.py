import json

from audiobook_voice_enhancer.cli import main


def test_character_add_set_and_list(tmp_path, capsys):
    path = tmp_path / "characters.json"
    assert main(["character", "add", "Vesemir", "--mode", "convert", "--voice", "voices/vesemir.wav", "--characters", str(path)]) == 0
    assert main(["character", "set", "Vesemir", "--mode", "original", "--characters", str(path)]) == 0
    assert main(["character", "list", "--characters", str(path)]) == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["Vesemir"]["mode"] == "original"
    assert "Vesemir" in capsys.readouterr().out
