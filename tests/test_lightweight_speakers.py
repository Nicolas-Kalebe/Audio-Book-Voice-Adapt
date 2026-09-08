import copy

import pytest

from audiobook_voice_enhancer.book_speakers import build_book, review_book
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.llm import LLMProvider


class Provider(LLMProvider):
    model = "lightweight-fixture"

    def __init__(self, respond):
        self.respond = respond
        self.calls = []

    def infer(self, payload):
        self.calls.append(copy.deepcopy(payload))
        return self.respond(payload, self.response_schema)


def test_candidates_survive_without_generated_cast_and_only_one_call_per_window(tmp_path):
    model = build_book(["Iara olhou para Nilo.", "— Você vem, Nilo?", "— Sim.",
                        "***", "— Amanhã — disse Nilo.", "— Certo — disse Iara."])
    untouched = copy.deepcopy(model)

    def answer(payload, schema):
        assert "task" not in payload  # no cast or secondary pass
        ids = {e["name"]: e["id"] for e in payload["entities"]}
        assert set(ids) == {"Iara", "Nilo"}
        assert all(e["narration_mentions"] == [0] for e in payload["entities"])
        row = payload["turns"][0]
        assert set(schema["properties"]["assignments"]["items"]["properties"]["speaker"]["enum"]) == {*ids.values(), "N0", None}
        assert schema["properties"]["assignments"]["maxItems"] == 1
        name = "Iara" if row["fragments"][0]["paragraph"] == 1 else "Nilo"
        return {"entities": [], "assignments": [{"id": row["id"], "speaker": ids[name], "kind": "speech", "confidence": .96}]}

    provider = Provider(answer)
    result = review_book(model, provider, Cache(tmp_path), (1, 2), protocol="lightweight", max_turns=1)
    assert model == untouched
    assert len(provider.calls) == result["review"]["batches_reviewed"] == 2
    assert result["review"]["errors"] == []
    assert [result["entities"][t["speaker_entity_id"]]["name"] for t in result["turns"][:2]] == ["Iara", "Nilo"]


def test_modified_subject_is_retained_despite_llm_disagreement(tmp_path):
    model = build_book(["— Eu vou — respondeu por ele Iara.", "***", "— Certo — disse Iara.", "— Sim — disse Nilo."])

    def answer(payload, schema):
        row = payload["turns"][0]
        assert row["anchor"] is not None
        assert row["anchor_evidence"][0]["quote"].strip(" –—") == "respondeu por ele Iara"
        assert row["local_narration"]
        return {"entities": [], "assignments": [{"id": row["id"], "speaker": None, "kind": "thought", "confidence": .96}]}

    result = review_book(model, Provider(answer), Cache(tmp_path), (0, 0), protocol="lightweight")
    assert result["turns"][0]["status"] == "explicit"
    assert result["turns"][0]["review_issue"] == "llm_disagrees_with_literal_subject"
    assert result["entities"][result["turns"][0]["speaker_entity_id"]]["name"] == "Iara"


def test_action_proximity_does_not_become_automatic_subject(tmp_path):
    model = build_book(["— Venha. — Nilo observou Iara.", "***", "— Sim — disse Iara."])
    result = review_book(model, None, Cache(tmp_path), (0, 0), protocol="lightweight")
    assert result["turns"][0]["speaker_entity_id"] is None


@pytest.mark.parametrize("mention,kind,accepted", [("Iara", "named", True), ("guarda", "anonymous", False), ("feiticeira", "anonymous", False)])
def test_repeated_named_mention_can_be_registered_but_ambiguous_anonymous_cannot(tmp_path, mention, kind, accepted):
    model = build_book(["Iara olhou para Iara no espelho. Um guarda olhou para outro guarda.", "— Olá."])
    def answer(payload, schema):
        return {"entities": [{"id": "N0", "mention": mention, "paragraph": 0, "kind": kind}],
                "assignments": [{"id": payload["turns"][0]["id"], "speaker": "N0", "kind": "speech", "confidence": .96}]}
    result = review_book(model, Provider(answer), Cache(tmp_path), protocol="lightweight")
    assert bool(result["turns"][0]["speaker_entity_id"]) == accepted
    assert bool(result["review"]["entity_rejections"]) != accepted
    assert result["review"]["errors"] == []
