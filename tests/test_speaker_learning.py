import json

from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.llm import LLMProvider, review_scenes
from audiobook_voice_enhancer.speaker_overrides import apply_overrides, confirm


class FakeProvider(LLMProvider):
    model = "fake"

    def infer(self, payload):
        return {"assignments": [
            {"id": item["id"], "speaker": "Geralt", "confidence": .99, "reason": "ação anterior"}
            for item in payload["target_dialogues"]
        ]}


def test_contextual_ai_assigns_scene_in_one_batch(tmp_path):
    dialogues = [
        {"id": "1", "speaker": None, "speaker_confidence": 0, "scene_id": 3,
         "book_paragraph_id": 1, "text": "Ela é nosso destino."},
        {"id": "2", "speaker": "Ciri", "speaker_confidence": .98, "scene_id": 4,
         "book_paragraph_id": 2, "text": "Estou com medo."},
    ]
    stats = review_scenes(FakeProvider(), Cache(tmp_path), dialogues,
                          ["As mãos de Geralt apertaram seus ombros.", "— Ela é nosso destino."],
                          {"Geralt", "Ciri"}, .85)
    assert dialogues[0]["speaker"] == "Geralt"
    assert dialogues[0]["llm_suggestion"] == "Geralt"
    assert stats["scenes_reviewed"] == 1
    assert stats["assigned"] == 1


def test_contextual_ai_rejects_invented_speaker(tmp_path):
    class Inventor(FakeProvider):
        def infer(self, payload):
            return {"assignments": [{"id": "1", "speaker": "Inventado", "confidence": .99, "reason": ""}]}

    dialogues = [{"id": "1", "speaker": None, "speaker_confidence": 0, "scene_id": 1,
                  "book_paragraph_id": 0, "text": "Olá"}]
    stats = review_scenes(Inventor(), Cache(tmp_path), dialogues, ["— Olá"], {"Geralt"}, .85)
    assert dialogues[0]["speaker"] is None
    assert stats["unresolved"] == 1


def test_contextual_ai_rejects_addressee_as_speaker(tmp_path):
    dialogues = [{"id": "1", "speaker": None, "speaker_confidence": 0, "scene_id": 1,
                  "book_paragraph_id": 0, "text": "Salve, Geralt!"}]
    stats = review_scenes(FakeProvider(), Cache(tmp_path), dialogues, ["— Salve, Geralt!"], {"Geralt"}, .85)
    assert dialogues[0]["speaker"] is None
    assert dialogues[0]["llm_rejected_reason"]
    assert stats["unresolved"] == 1


def test_contextual_ai_abstains_when_critic_disagrees(tmp_path):
    class DisagreeingProvider(LLMProvider):
        model = "disagree"

        def infer(self, payload):
            speaker = "Ciri" if payload.get("review_pass") == "blind_second_reading" else "Geralt"
            return {"assignments": [{"id": item["id"], "speaker": speaker,
                                      "confidence": .99, "reason": "teste"}
                                     for item in payload["target_dialogues"]]}

    dialogues = [{"id": "1", "speaker": None, "speaker_confidence": 0, "scene_id": 1,
                  "book_paragraph_id": 0, "text": "Olá"}]
    stats = review_scenes(DisagreeingProvider(), Cache(tmp_path), dialogues, ["— Olá"],
                          {"Geralt", "Ciri"}, .85)
    assert dialogues[0]["speaker"] is None
    assert dialogues[0]["llm_suggestion"] == "Geralt"
    assert dialogues[0]["llm_alternative"] == "Ciri"
    assert stats["critic_disagreements"] == 1


def test_consensus_threshold_is_not_lowered_in_multi_speaker_batch(tmp_path):
    class ModestProvider(LLMProvider):
        model = "modest"

        def infer(self, payload):
            return {"assignments": [{"id": item["id"], "speaker": "Geralt",
                                      "confidence": .91, "reason": "contexto"}
                                     for item in payload["target_dialogues"]]}

    dialogues = [
        {"id": "target", "speaker": None, "speaker_confidence": 0, "scene_id": 1,
         "book_paragraph_id": 1, "text": "Olá"},
        *({"id": name, "speaker": name, "speaker_confidence": .98, "scene_id": 1,
           "book_paragraph_id": index, "text": "fala"}
          for index, name in enumerate(("Geralt", "Ciri", "Yennefer"), 2)),
    ]
    stats = review_scenes(ModestProvider(), Cache(tmp_path), dialogues,
                          ["x", "— Olá", "x", "x", "x"], {"Geralt", "Ciri", "Yennefer"}, .85)
    assert dialogues[0]["speaker"] is None
    assert stats["suggested_for_review"] == 1


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


def test_confirmation_applies_to_every_fragment_of_the_same_turn(tmp_path):
    report_path = tmp_path / "analysis.json"
    overrides = tmp_path / "speaker_overrides.json"
    report_data = {"files": [{"input": str(tmp_path / "Parte 01.mp3"), "dialogues": [
        {"id": "1-0", "turn_id": "book-1", "fragment_index": 0, "dialogue_style": "dash",
         "speaker": None, "scene_id": 1},
        {"id": "1-1", "turn_id": "book-1", "fragment_index": 1, "dialogue_style": "dash",
         "speaker": None, "scene_id": 1},
    ]}]}
    report_path.write_text(json.dumps(report_data), encoding="utf-8")
    assert confirm(report_path, overrides, "Parte 01.mp3", "1-1", "Yennefer", False) == 2
    saved = json.loads(report_path.read_text(encoding="utf-8"))["files"][0]["dialogues"]
    assert [item["speaker"] for item in saved] == ["Yennefer", "Yennefer"]
    assert all(item["manually_confirmed"] for item in saved)
