import copy

import pytest

from audiobook_voice_enhancer.book_speakers import build_book, review_book, scoped_report
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.llm import LLMProvider
from audiobook_voice_enhancer.scene_context import SceneContext, context_chunks


def person(name, *mentions, kind="named", role="participant"):
    return {"name": name, "kind": kind, "role": role,
            "mentions": [{"paragraph": p, "text": text} for p, text in mentions]}


class Provider(LLMProvider):
    model = "scene-fixture"

    def __init__(self, callback):
        self.callback = callback
        self.calls = []

    def infer(self, payload):
        self.calls.append(copy.deepcopy(payload))
        return self.callback(payload)


def test_cast_distinguishes_mentions_and_preserves_scene_context_and_stable_ids(tmp_path):
    blocks = ["Iara conversava com Nilo sobre Otávio.", "— Olá — disse Iara.", "— Tudo bem?",
              "***", "— Quem? — disse Otávio."]
    model = build_book(blocks)
    original = copy.deepcopy(model)

    def respond(payload):
        if payload.get("task") == "scene_cast":
            return {"entities": [person("Iara", (0, "Iara")), person("Nilo", (0, "Nilo")),
                                 person("Otávio", (0, "Otávio"), role="mentioned")]}
        assert payload["complete_scene"]
        assert [p["text"] for p in payload["scene_text"]] == blocks[:3]
        assert {e["name"] for e in payload["entities"]} == {"Iara", "Nilo"}
        assert payload["mentioned_people"] == ["Otávio"]
        nilo = next(e["id"] for e in payload["entities"] if e["name"] == "Nilo")
        return {"entities": [], "assignments": [
            {"id": t["id"], "speaker": t["anchor"] or nilo, "kind": "speech", "confidence": .96}
            for t in payload["turns"]]}

    provider = Provider(respond)
    result = review_book(model, provider, Cache(tmp_path), (1, 2), protocol="scene", max_turns=1)
    assert model == original
    assert result["review"]["cast_calls"] == 1
    assert result["review"]["total_llm_calls"] == 3
    assert result["review"]["errors"] == []
    assert result["entities"][result["turns"][1]["speaker_entity_id"]]["name"] == "Nilo"
    targets = [p["turns"][0]["id"] for p in provider.calls if p.get("task") != "scene_cast"]
    assert len(set(targets)) == 2
    assert scoped_report(result, (1, 2))["scene_context"]["scenes"]


def test_cast_description_resolves_literal_subject_but_does_not_change_other_scene(tmp_path):
    blocks = ["Lia falou com uma capitã de casaco azul.", "— Vamos — disse Lia.",
              "— Agora — disse a capitã.", "***", "— Amanhã — disse a capitã."]
    model = build_book(blocks)
    provider = Provider(lambda _: {"entities": [person("Lia", (0, "Lia")),
        person("capitã de casaco azul", (0, "capitã de casaco azul"), (2, "capitã"), kind="anonymous")]})
    context = SceneContext(model, provider, Cache(tmp_path))
    context.prepare(model["turns"][0]["scene_id"])
    turn = model["turns"][1]
    assert turn["status"] == "explicit"
    assert turn["anchor_origin"] == "scene_alias_speech_tag"
    assert model["entities"][turn["speaker_entity_id"]]["name"] == "capitã de casaco azul"
    assert model["turns"][2]["speaker_entity_id"] is None


def test_same_description_different_mentions_are_not_merged(tmp_path):
    model = build_book(["Um guarda chegou.", "Outro guarda chegou.", "— Olá — disse o guarda."])
    provider = Provider(lambda _: {"entities": [person("guarda", (0, "guarda"), kind="anonymous"),
                                               person("guarda", (1, "guarda"), kind="anonymous")]})
    context = SceneContext(model, provider, Cache(tmp_path))
    context.prepare(model["turns"][0]["scene_id"])
    assert len(context.entities(model["turns"][0]["scene_id"])) == 2
    assert model["turns"][0]["speaker_entity_id"] is None


def test_literal_short_full_name_link_is_local(tmp_path):
    model = build_book(["Iara Silva chegou.", "— Olá — disse Iara.", "***", "— Quem? — disse Iara."])
    provider = Provider(lambda _: {"entities": [person("Iara Silva", (0, "Iara Silva"), (1, "Iara"))]})
    context = SceneContext(model, provider, Cache(tmp_path))
    context.prepare(model["turns"][0]["scene_id"])
    assert model["entities"][model["turns"][0]["speaker_entity_id"]]["name"] == "Iara Silva"
    assert model["entities"][model["turns"][1]["speaker_entity_id"]]["name"] == "Iara"
    assert model["aliases"] == {}


def test_shared_first_name_claim_does_not_merge_two_named_people(tmp_path):
    model = build_book(["Iara Silva e Iara Costa chegaram.", "— Olá — disse Iara."])
    provider = Provider(lambda _: {"entities": [person("Iara Silva", (0, "Iara Silva"), (1, "Iara")),
                                               person("Iara Costa", (0, "Iara Costa"), (1, "Iara"))]})
    context = SceneContext(model, provider, Cache(tmp_path))
    context.prepare(model["turns"][0]["scene_id"])
    assert {e["name"] for e in context.entities(model["turns"][0]["scene_id"])} == {"Iara", "Iara Silva", "Iara Costa"}


def test_focused_review_corrects_addressee_without_receiving_first_guess(tmp_path):
    model = build_book(["— Olá — disse Iara.", "— Oi — disse Nilo.", "— Você vem, Iara?"])

    def respond(payload):
        if payload.get("task") == "scene_cast":
            return {"entities": []}
        ids = {e["name"]: e["id"] for e in payload["entities"]}
        review = payload.get("task") == "focused_review"
        if review:
            assert len(payload["turns"]) == 1
            assert "assignments" not in payload and "first_pass_decisions" not in payload
            assert payload["turns"][0]["review_trigger"] == "possible_addressee_confusion"
        return {"entities": [], "assignments": [{"id": t["id"],
            "speaker": t["anchor"] or ids["Nilo" if review else "Iara"], "kind": "speech", "confidence": .96}
            for t in payload["turns"]]}

    result = review_book(model, Provider(respond), Cache(tmp_path), protocol="scene")
    turn = result["turns"][-1]
    assert result["entities"][turn["speaker_entity_id"]]["name"] == "Nilo"
    assert result["review"]["repair_calls"] == 1
    assert result["review"]["repair_targets"] == 1
    assert turn["first_pass_decisions"] != [turn["focused_review"]]


def test_no_repair_option_is_a_real_ablation(tmp_path):
    model = build_book(["— Olá — disse Iara.", "— Você vem, Iara?"])
    def respond(payload):
        if payload.get("task") == "scene_cast":
            return {"entities": []}
        assert payload.get("task") != "focused_review"
        return {"entities": [], "assignments": [{"id": t["id"], "speaker": "E0", "kind": "speech", "confidence": .95}
                                               for t in payload["turns"]]}
    result = review_book(model, Provider(respond), Cache(tmp_path), protocol="scene", scene_repair=False)
    assert result["review"]["repair_calls"] == 0


def test_cast_failure_and_repair_failure_keep_literal_subject(tmp_path):
    model = build_book(["— Olá — disse Iara."])
    def respond(payload):
        if payload.get("task") in {"scene_cast", "focused_review"}:
            raise TimeoutError("fixture timeout")
        return {"entities": [], "assignments": [{"id": t["id"], "speaker": None, "kind": "unknown", "confidence": .95}
                                               for t in payload["turns"]]}
    result = review_book(model, Provider(respond), Cache(tmp_path), protocol="scene")
    assert result["turns"][0]["status"] == "explicit"
    assert result["entities"][result["turns"][0]["speaker_entity_id"]]["name"] == "Iara"
    assert {e["phase"] for e in result["review"]["errors"]} == {"scene_cast", "focused_review"}


def test_context_chunks_never_drop_text_and_oversize_is_explicit():
    model = build_book(["Uma frase.", "Outra frase.", "Terceira frase."])
    scene = model["scenes"][0]
    chunks = list(context_chunks(model, scene, 23))
    assert [p for first, last in chunks for p in range(first, last + 1)] == [0, 1, 2]
    with pytest.raises(ValueError, match="exceeds"):
        list(context_chunks(model, scene, 5))


def test_long_scene_uses_bounded_context_and_history_is_explicitly_hypothetical(tmp_path):
    model = build_book(["— Olá — disse Iara.", *[f"— Mensagem número {i}." for i in range(12)]])
    context = SceneContext(model, Provider(lambda _: {"entities": []}), Cache(tmp_path), max_chars=100)
    scene_id = model["turns"][0]["scene_id"]
    context.prepare(scene_id)
    identity = model["turns"][0]["speaker_entity_id"]
    for turn in model["turns"][1:10]:
        turn.update(speaker_entity_id=identity, status="contextual")
    batch = context.expand({"scene_id": scene_id, "first": 10, "last": 10, "turns": [model["turns"][10]]})
    assert not batch["complete_scene"]
    assert batch["first"] <= 10 <= batch["last"]
    assert sum(len(b) for b in model["blocks"][batch["first"]:batch["last"] + 1]) <= 100
    extra = context.extra_payload(batch, {identity: "E0"})
    assert len(extra["history"]) == 6
    assert {entry["status"] for entry in extra["history"]} == {"hypothesis"}
