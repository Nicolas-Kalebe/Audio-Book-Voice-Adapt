import copy
import json

import pytest

from audiobook_voice_enhancer.book_speakers import build_book, review_book
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.llm import LLMProvider, OllamaProvider, cached_infer


class Provider(LLMProvider):
    model = "fixture"

    def __init__(self, callback):
        self.callback = callback

    def infer(self, payload):
        return self.callback(payload)


def test_compact_context_can_attribute_without_generated_evidence(tmp_path):
    model = build_book(["— Abra — disse Iara.", "Ela insistiu.", "— Agora!"])
    untouched = copy.deepcopy(model)

    def answer(payload):
        assert [p["text"] for p in payload["scene_text"]] == model["blocks"]
        assert all("char_start" not in f for t in payload["turns"] for f in t["fragments"])
        return {"entities": [], "assignments": [
            {"id": t["id"], "speaker": "E0", "kind": "speech", "confidence": .95}
            for t in payload["turns"]]}

    reviewed = review_book(model, Provider(answer), Cache(tmp_path), protocol="compact")
    assert model == untouched
    assert reviewed["turns"][1]["status"] == "contextual"
    assert reviewed["turns"][1]["evidence"] == []
    assert reviewed["review"]["unresolved"] == 0
    assert reviewed["review"]["raw_speaker_proposals"] == 2


@pytest.mark.parametrize("problem", ["missing", "duplicate", "invented", "low", "unknown"])
def test_compact_rejections_keep_raw_proposals_without_overwriting_anchor(tmp_path, problem):
    model = build_book(["— Abra — disse Iara.", "— Agora!"])

    def answer(payload):
        row = {"id": "T1", "speaker": "E0", "kind": "speech", "confidence": .95}
        if problem == "invented":
            row["speaker"] = "E999"
        if problem == "low":
            row["confidence"] = .4
        if problem == "unknown":
            row.update(kind="unknown", speaker=None)
        return {"entities": [], "assignments": [] if problem == "missing" else
                [row, row] if problem == "duplicate" else [row]}

    reviewed = review_book(model, Provider(answer), Cache(tmp_path), protocol="compact")
    assert reviewed["turns"][0]["status"] == "explicit"
    assert reviewed["turns"][1]["speaker_entity_id"] is None
    assert "raw_decisions" in reviewed["turns"][1]
    assert reviewed["review"]["unresolved"] == 1


def test_compact_new_entity_uses_literal_mention_without_offsets(tmp_path):
    model = build_book(["Um viajante entrou.", "— Olá!"])
    answer = {"entities": [{"id": "N0", "kind": "anonymous", "mention": "viajante", "paragraph": 0}],
              "assignments": [{"id": "T0", "speaker": "N0", "kind": "speech", "confidence": .96}]}
    result = review_book(model, Provider(lambda _: answer), Cache(tmp_path), protocol="compact")
    identity = result["turns"][0]["speaker_entity_id"]
    assert result["entities"][identity]["name"] == "viajante"
    answer["entities"][0]["mention"] = "feiticeiro"
    result = review_book(model, Provider(lambda _: answer), Cache(tmp_path / "other"), protocol="compact")
    assert result["turns"][0]["speaker_entity_id"] is None


def test_truncated_ollama_output_records_finish_reason_and_raw_response(tmp_path, monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": '{"assignments":['}, "done_reason": "length", "eval_count": 4096}

    monkeypatch.setattr("audiobook_voice_enhancer.llm.requests.post", lambda *a, **k: Response())
    cache = Cache(tmp_path)
    with pytest.raises(ValueError, match="done_reason=length"):
        cached_infer(OllamaProvider("http://localhost:11434", "fixture"), cache, {})
    diagnostics = json.loads(next((tmp_path / "llm_diagnostics").glob("*.json")).read_text())
    assert diagnostics["raw_content"] == '{"assignments":['
    assert diagnostics["eval_count"] == 4096
    assert not list((tmp_path / "llm").glob("*.json"))
