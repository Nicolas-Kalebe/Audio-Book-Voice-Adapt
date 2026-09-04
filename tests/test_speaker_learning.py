import json

import numpy as np

from audiobook_voice_enhancer.acoustic_attribution import assign_suggestions
from audiobook_voice_enhancer.speaker_overrides import apply_overrides, confirm


def test_acoustic_suggestion_requires_similarity_and_margin():
    dialogues = [
        {"id": "a1", "speaker": "Ciri", "speaker_confidence": .98, "scene_id": 1},
        {"id": "a2", "speaker": "Ciri", "speaker_confidence": .98, "scene_id": 1},
        {"id": "b1", "speaker": "Geralt", "speaker_confidence": .98, "scene_id": 1},
        {"id": "b2", "speaker": "Geralt", "speaker_confidence": .98, "scene_id": 1},
        {"id": "u1", "speaker": None, "speaker_confidence": 0, "scene_id": 1},
    ]
    vectors = {"a1": np.array([1., 0.]), "a2": np.array([.98, .02]),
               "b1": np.array([0., 1.]), "b2": np.array([.02, .98]),
               "u1": np.array([.99, .01])}
    count = assign_suggestions(dialogues, vectors,
                               {"minimum_acoustic_similarity": .78, "minimum_acoustic_margin": .035},
                               {"Ciri", "Geralt"})
    assert count == 1
    assert dialogues[-1]["acoustic_suggestion"] == "Ciri"


def test_acoustic_suggestion_never_imports_character_from_another_scene():
    dialogues = [
        {"id": "c", "speaker": "Ciri", "speaker_confidence": .98, "scene_id": 1},
        {"id": "g", "speaker": "Geralt", "speaker_confidence": .98, "scene_id": 1},
        {"id": "y1", "speaker": "Yennefer", "speaker_confidence": .98, "scene_id": 2},
        {"id": "y2", "speaker": "Yennefer", "speaker_confidence": .98, "scene_id": 2},
        {"id": "u", "speaker": None, "speaker_confidence": 0, "scene_id": 1},
    ]
    vectors = {"c": np.array([1., 0.]), "g": np.array([0., 1.]),
               "y1": np.array([.7, .7]), "y2": np.array([.7, .7]), "u": np.array([.7, .7])}
    assign_suggestions(dialogues, vectors, {"acoustic_anchor_confidence": .9},
                       {"Ciri", "Geralt", "Yennefer"})
    assert dialogues[-1].get("acoustic_suggestion") != "Yennefer"


def test_confirmation_propagates_same_role_in_scene(tmp_path):
    report_path = tmp_path / "analysis.json"
    overrides = tmp_path / "speaker_overrides.json"
    report = {"files": [{"input": str(tmp_path / "Parte 01.mp3"), "dialogues": [
        {"id": "1", "speaker": None, "scene_id": 3, "attribution_role": "guerreira"},
        {"id": "2", "speaker": None, "scene_id": 3, "attribution_role": "guerreira"},
        {"id": "3", "speaker": None, "scene_id": 4, "attribution_role": "guerreira"},
    ]}]}
    report_path.write_text(json.dumps(report), encoding="utf-8")
    assert confirm(report_path, overrides, "Parte 01.mp3", "1", "Rayla", True) == 2
    dialogues = json.loads(report_path.read_text(encoding="utf-8"))["files"][0]["dialogues"]
    assert [item.get("speaker") for item in dialogues] == ["Rayla", "Rayla", None]
    fresh = [{"id": "2", "speaker": None, "scene_id": 3, "attribution_role": "guerreira"}]
    assert apply_overrides(tmp_path / "Parte 01.mp3", fresh, overrides) == 1
    assert fresh[0]["speaker"] == "Rayla"
