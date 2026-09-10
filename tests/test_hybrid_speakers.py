from audiobook_voice_enhancer.book_speakers import build_book, review_book
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.llm import LLMProvider
from audiobook_voice_enhancer.cache import FrozenCache, ReplayMiss
import pytest


class Provider(LLMProvider):
    model = "hybrid-fixture"

    def __init__(self, repair_confidence=.97):
        self.calls = []
        self.repair_schemas = []
        self.repair_confidence = repair_confidence

    def infer(self, payload):
        self.calls.append(payload)
        if payload.get("task") == "repair_unresolved_continuation":
            self.repair_schemas.append(self.response_schema)
            return {"entities": [], "assignments": [
                {"id": turn["id"], "speaker": "R0", "kind": "speech",
                 "confidence": self.repair_confidence}
                for turn in payload["turns"]
            ]}
        ids = {entity["name"]: entity["id"] for entity in payload["entities"]}
        if payload["turns"][0]["fragments"][0]["paragraph"] < 2:
            speakers = [ids["Iara"], ids["Nilo"]]
        else:
            speakers = [None] * len(payload["turns"])
        return {"entities": [], "assignments": [
            {"id": turn["id"], "speaker": speaker,
             "kind": "speech" if speaker else "unknown", "confidence": .98}
            for turn, speaker in zip(payload["turns"], speakers)
        ]}


def model_with_split_scene():
    return build_book([
        "— Primeiro — disse Iara.",
        "— Segundo — disse Nilo.",
        "— Terceiro.",
        "— Quarto.",
    ])


def test_frozen_base_only_calls_provider_for_repair(tmp_path):
    source = Cache(tmp_path / "original")
    review_book(model_with_split_scene(), Provider(), source,
                protocol="hybrid", max_turns=2)
    frozen = FrozenCache(source.root)
    provider = Provider()
    result = review_book(model_with_split_scene(), provider, Cache(tmp_path / "candidate"),
                         protocol="hybrid", max_turns=2, base_cache=frozen)
    assert frozen.hits == 2
    assert frozen.misses == 0
    assert len(provider.calls) == 1
    assert provider.calls[0]["task"] == "repair_unresolved_continuation"
    assert result["hybrid_router"]["accepted_repairs"] == 2


def test_frozen_miss_aborts_engine_instead_of_partial_result(tmp_path):
    source = Cache(tmp_path / "empty")
    provider = Provider()
    with pytest.raises(ReplayMiss):
        review_book(model_with_split_scene(), provider, Cache(tmp_path / "candidate"),
                    protocol="hybrid", max_turns=2, base_cache=FrozenCache(source.root))
    assert provider.calls == []


def test_hybrid_repairs_only_unresolved_continuation_window(tmp_path):
    provider = Provider()
    result = review_book(model_with_split_scene(), provider, Cache(tmp_path),
                         protocol="hybrid", max_turns=2)

    repair = [call for call in provider.calls
              if call.get("task") == "repair_unresolved_continuation"]
    assert len(provider.calls) == 3
    assert len(repair) == 1
    assert {row["name"] for row in repair[0]["established_speakers"]} == {"Iara", "Nilo"}
    assert len(repair[0]["literal_anchors"]) == 2
    schema = provider.repair_schemas[0]
    assert "entities" not in schema["properties"]
    assert schema["properties"]["assignments"]["maxItems"] == 2
    assert set(schema["properties"]["assignments"]["items"]["properties"]["speaker"]["enum"]) == {
        "R0", "R1", None}
    assert result["turns"][2]["status"] == "contextual"
    assert result["turns"][2]["review_issue"] == "repaired_by_hybrid_continuity"
    assert result["hybrid_router"]["accepted_repairs"] == 2
    assert result["review"]["total_llm_calls"] == 3
    assert result["hybrid_router"]["repair_token_budgets"] == [256]


def test_hybrid_rejects_repair_below_stricter_floor(tmp_path):
    provider = Provider(repair_confidence=.94)
    result = review_book(model_with_split_scene(), provider, Cache(tmp_path),
                         protocol="hybrid", max_turns=2, threshold=.90)

    assert result["turns"][2]["speaker_entity_id"] is None
    assert result["hybrid_router"]["accepted_repairs"] == 0
    assert result["hybrid_router"]["rejected_repairs"] == 2


def test_compact_baseline_does_not_invoke_hybrid_router(tmp_path):
    provider = Provider()
    result = review_book(model_with_split_scene(), provider, Cache(tmp_path),
                         protocol="compact", max_turns=2)

    assert len(provider.calls) == 2
    assert "hybrid_router" not in result


def test_hybrid_never_overwrites_literal_anchor_on_model_disagreement(tmp_path):
    model = build_book(["— Primeiro — disse Iara."])

    class Disagreeing(LLMProvider):
        model = "fixture"

        def infer(self, payload):
            return {"entities": [], "assignments": [
                {"id": payload["turns"][0]["id"], "speaker": None,
                 "kind": "unknown", "confidence": .99}
            ]}

    result = review_book(model, Disagreeing(), Cache(tmp_path), protocol="hybrid")
    turn = result["turns"][0]
    assert turn["status"] == "explicit"
    assert turn["speaker_entity_id"] is not None


def test_hybrid_ignores_proposed_entities_but_never_accepts_their_ids(tmp_path):
    provider = Provider()

    original_infer = provider.infer

    def infer(payload):
        if payload.get("task") != "repair_unresolved_continuation":
            return original_infer(payload)
        provider.calls.append(payload)
        return {"entities": [{"id": "N0", "mention": "Intruso"}], "assignments": [
            {"id": payload["turns"][0]["id"], "speaker": "R0",
             "kind": "speech", "confidence": .97},
            {"id": payload["turns"][1]["id"], "speaker": "N0",
             "kind": "speech", "confidence": .99},
        ]}

    provider.infer = infer
    result = review_book(model_with_split_scene(), provider, Cache(tmp_path),
                         protocol="hybrid", max_turns=2)

    assert result["turns"][2]["speaker_entity_id"] is not None
    assert result["turns"][3]["speaker_entity_id"] is None
    assert result["hybrid_router"]["ignored_entity_proposals"] == 1
    assert result["hybrid_router"]["accepted_repairs"] == 1
    assert result["hybrid_router"]["rejected_repairs"] == 1
    assert all(entity["name"] != "Intruso" for entity in result["entities"].values())
