from audiobook_voice_enhancer.book_speakers import build_book, review_book
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.compact_speakers import SCHEMA
from audiobook_voice_enhancer.llm import LLMProvider


class Provider(LLMProvider):
    model = "memory-fixture"

    def __init__(self):
        self.calls = []

    def infer(self, payload):
        self.calls.append(payload)
        assert self.response_schema == SCHEMA
        coen = next(entity["id"] for entity in payload["entities"] if entity["name"] == "Coen")
        return {"entities": [], "assignments": [
            {"id": turn["id"], "speaker": coen, "kind": "speech", "confidence": .96}
            for turn in payload["turns"]]}


def test_memory_keeps_stable_speaker_and_turn_ids_without_expanding_scene(tmp_path):
    blocks = ["— Agora — disse Coen.", "— Um.", "— Dois.", "— Três.", "— Quatro.", "— Cinco."]
    model = build_book(blocks)
    provider = Provider()
    result = review_book(model, provider, Cache(tmp_path), protocol="compact", max_turns=2)

    assert len(provider.calls) == 3
    coen_ids = [{entity["name"]: entity["id"] for entity in call["entities"]}["Coen"]
                for call in provider.calls]
    assert len(set(coen_ids)) == 1
    assert provider.calls[1]["recent_hypotheses"]
    assert provider.calls[1]["literal_anchors_before_window"][0]["speaker"] == coen_ids[0]
    assert provider.calls[-1]["scene_text"][0]["paragraph"] > 0
    turn_ids = [turn["id"] for call in provider.calls for turn in call["turns"]]
    assert turn_ids == [f"T{i}" for i in range(len(turn_ids))]
    assert result["compact_memory"]["max_catalog_entities"] == 1


def test_timeout_still_carries_literal_anchor_but_not_failed_hypothesis(tmp_path):
    model = build_book(["— Agora — disse Coen.", "— Um.", "— Dois."])

    class FailingOnce(Provider):
        def infer(self, payload):
            self.calls.append(payload)
            if len(self.calls) == 1:
                raise TimeoutError("fixture timeout")
            coen = next(entity["id"] for entity in payload["entities"] if entity["name"] == "Coen")
            assert payload["literal_anchors_before_window"][0]["speaker"] == coen
            assert payload["recent_hypotheses"] == []
            return {"entities": [], "assignments": [
                {"id": turn["id"], "speaker": coen, "kind": "speech", "confidence": .96}
                for turn in payload["turns"]]}

    provider = FailingOnce()
    result = review_book(model, provider, Cache(tmp_path), protocol="compact", max_turns=2)
    assert len(provider.calls) == 2
    assert result["review"]["errors"][0]["error"] == "fixture timeout"
    assert result["compact_memory"]["literal_records"] == 1
    assert result["compact_memory"]["hypothesis_records"] == 1
