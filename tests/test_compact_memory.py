from audiobook_voice_enhancer.book_speakers import build_book, review_book
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.compact_memory import SceneLocalMemory
from audiobook_voice_enhancer.compact_speakers import SCHEMA
from audiobook_voice_enhancer.llm import LLMProvider


class Provider(LLMProvider):
    model = "memory-fixture"

    def __init__(self):
        self.calls = []

    def infer(self, payload):
        self.calls.append(payload)
        assert self.response_schema == SCHEMA
        speaker = payload["entities"][0]["id"]
        return {"entities": [], "assignments": [
            {"id": turn["id"], "speaker": speaker, "kind": "speech", "confidence": .96}
            for turn in payload["turns"]]}


def test_ids_are_stable_inside_scene_and_restart_at_zero_in_next_scene(tmp_path):
    blocks = ["— Olá — disse Luma.", "***", "— Agora — disse Coen.",
              "— Um.", "— Dois.", "— Três.", "— Quatro."]
    model = build_book(blocks)
    provider = Provider()
    result = review_book(model, provider, Cache(tmp_path), protocol="compact", max_turns=2)

    luma_call = next(call for call in provider.calls
                     if any(entity["name"] == "Luma" for entity in call["entities"]))
    coen_calls = [call for call in provider.calls
                  if any(entity["name"] == "Coen" for entity in call["entities"])]
    assert luma_call["entities"][0]["id"] == "E0"
    assert len(coen_calls) == 3
    assert all(call["entities"][0]["id"] == "E0" for call in coen_calls)
    assert [turn["id"] for call in coen_calls for turn in call["turns"]] == [
        "T0", "T1", "T2", "T3", "T4"]
    assert coen_calls[1]["literal_anchors_before_window"][0]["speaker"] == "E0"
    assert coen_calls[1]["recent_hypotheses"]
    assert coen_calls[-1]["scene_text"][0]["paragraph"] > 2
    assert result["compact_memory"]["max_catalog_entities"] == 1


def test_only_recent_hypotheses_remain_in_catalog():
    entities = {f"person-{i}": {"id": f"person-{i}", "name": f"Pessoa {i}",
        "kind": "named", "scene_id": 0, "aliases": [f"Pessoa {i}"]} for i in range(3)}
    memory = SceneLocalMemory({"entities": entities, "turns": []}, recent_limit=2)
    memory.records[0] = [{"identity": f"person-{i}", "source": "model_hypothesis"}
                         for i in range(3)]
    selected = memory.entities({"scene_id": 0, "turns": []}, "")
    assert [entity["id"] for entity in selected] == ["person-1", "person-2"]
    assert [memory.entity_id(0, entity["id"]) for entity in selected] == ["E0", "E1"]


def test_timeout_carries_literal_anchor_but_not_failed_hypothesis(tmp_path):
    model = build_book(["— Agora — disse Coen.", "— Um.", "— Dois."])

    class FailingOnce(Provider):
        def infer(self, payload):
            self.calls.append(payload)
            if len(self.calls) == 1:
                raise TimeoutError("fixture timeout")
            assert payload["entities"][0]["id"] == "E0"
            assert payload["literal_anchors_before_window"][0]["speaker"] == "E0"
            assert payload["recent_hypotheses"] == []
            return {"entities": [], "assignments": [
                {"id": turn["id"], "speaker": "E0", "kind": "speech", "confidence": .96}
                for turn in payload["turns"]]}

    provider = FailingOnce()
    result = review_book(model, provider, Cache(tmp_path), protocol="compact", max_turns=2)
    assert len(provider.calls) == 2
    assert result["review"]["errors"][0]["error"] == "fixture timeout"
    assert result["compact_memory"]["literal_records"] == 1
    assert result["compact_memory"]["hypothesis_records"] == 1
