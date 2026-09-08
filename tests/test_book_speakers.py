import copy

import pytest

from audiobook_voice_enhancer.book_speakers import build_book, review_book, project_to_audio, windows
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.character_discovery import discover_characters
from audiobook_voice_enhancer.llm import LLMProvider, SYSTEM


class TextProvider(LLMProvider):
    model = "fixture"

    def __init__(self, response):
        self.response = response
        self.payloads = []

    def infer(self, payload):
        self.payloads.append(copy.deepcopy(payload))
        return self.response(payload)


def citation(paragraph, quote):
    # Deliberately wrong offsets exercise exact, unique quote recovery.
    return {"paragraph": paragraph, "start": -1, "end": -1, "quote": quote}


def test_text_turns_exist_without_any_transcription_and_include_all_fragments():
    blocks = ["— Abra — disse Iara. — Agora!", "— Como?", "— Volte — disse Nilo."]
    model = build_book(blocks)
    assert len(model["turns"]) == 3
    first = model["turns"][0]
    assert [part["text"] for part in first["fragments"]] == ["Abra", "Agora!"]
    assert first["status"] == "explicit"
    assert model["entities"][first["speaker_entity_id"]]["name"] == "Iara"
    assert model["turns"][1]["status"] == "unresolved"
    assert not any("start" in turn for turn in model["turns"])


def test_distinct_people_sharing_first_name_keep_distinct_ids():
    model = build_book(["— Venha — disse Nilo Braga.", "— Espere — disse Nilo Costa."])
    assert len(model["entities"]) == 2
    assert len({turn["speaker_entity_id"] for turn in model["turns"]}) == 2
    assert build_book(model["blocks"])["entities"] == model["entities"]


def test_configured_alias_is_explicit_identity_link():
    model = build_book(["— Venha — disse Nilo.", "— Espere — disse Nilo Braga."], {"nilo": "Nilo Braga"})
    assert len(model["entities"]) == 1
    assert len({turn["speaker_entity_id"] for turn in model["turns"]}) == 1


def test_quoted_speech_has_explicit_anchor_but_action_alone_does_not():
    model = build_book(['Iara disse: “Abra a porta.”', "— Por quê? — Nilo olhou para ela."])
    assert model["turns"][0]["status"] == "explicit"
    assert model["turns"][1]["speaker_entity_id"] is None


def test_explicit_self_introduction_discovers_name_without_audio_or_configuration():
    model = build_book(["— Eu, Iara, conheço a cidade."])
    turn = model["turns"][0]
    assert turn["status"] == "explicit"
    assert model["entities"][turn["speaker_entity_id"]]["name"] == "Iara"


def test_audio_without_book_match_does_not_keep_old_speaker_guess():
    audio = [{"id": "missing", "source": "transcript", "speaker": "Old guess", "speaker_confidence": .99,
              "start": 2, "end": 3}]
    project_to_audio(build_book(["— Olá!"]), audio)
    assert audio[0]["speaker"] is None
    assert (audio[0]["start"], audio[0]["end"]) == (2, 3)


def test_model_sees_unaligned_turn_and_projection_preserves_timings_and_manual_choice(tmp_path):
    blocks = ["— Abra — disse Iara. — Agora!", "— Como?"]
    model = build_book(blocks)
    def response(payload):
        identity = payload["entities"][0]["id"]
        return {"entities": [], "assignments": [
            {"id": turn["id"], "speaker": identity, "kind": "speech", "confidence": .95,
             "reason": "contexto", "evidence": [citation(0, "disse Iara")]} for turn in payload["turns"]]}
    provider = TextProvider(response)
    reviewed = review_book(model, provider, Cache(tmp_path), (0, 1))
    assert provider.system_prompt == SYSTEM  # Adaptation never mutates shared provider.
    assert len(provider.payloads[0]["turns"]) == 2
    assert len(provider.payloads[0]["turns"][0]["fragments"]) == 2
    assert reviewed["turns"][1]["status"] == "contextual"
    assert model["turns"][1]["status"] == "unresolved"
    audio = [{"id": "0-0", "source": "book", "start": 1.2, "end": 1.7, "speaker": "old"},
             {"id": "0-1", "source": "book", "start": 2.2, "end": 2.7, "speaker": "Manual", "manually_confirmed": True}]
    project_to_audio(reviewed, audio)
    assert len(audio) == 2  # Missing textual turn never gets invented audio.
    assert audio[0]["speaker"] == "Iara"
    assert (audio[0]["start"], audio[0]["end"]) == (1.2, 1.7)
    assert audio[1]["speaker"] == "Manual"


@pytest.mark.parametrize("evidence", [[citation(0, "invented")], [citation(50, "disse Iara")],
                                     [citation(0, "Abra")], []])
def test_unverifiable_or_spoken_evidence_cannot_attribute_target(tmp_path, evidence):
    model = build_book(["— Abra — disse Iara.", "— Como?"])
    def response(payload):
        return {"entities": [], "assignments": [{"id": "book-1", "speaker": payload["entities"][0]["id"],
                   "kind": "speech", "confidence": 1, "evidence": evidence}]}
    result = review_book(model, TextProvider(response), Cache(tmp_path))
    assert result["turns"][1]["speaker_entity_id"] is None


def test_explicit_attribution_disagreement_is_reported_as_conflict(tmp_path):
    model = build_book(["— Abra — disse Iara.", "— Espere — disse Nilo."])
    def response(payload):
        nilo = next(e["id"] for e in payload["entities"] if e["name"] == "Nilo")
        return {"entities": [], "assignments": [{"id": "book-0", "speaker": nilo,
                   "kind": "speech", "confidence": .99, "evidence": [citation(1, "disse Nilo")]}]}
    result = review_book(model, TextProvider(response), Cache(tmp_path))
    assert result["turns"][0]["status"] == "conflict"
    assert result["turns"][0]["speaker_entity_id"] is None


def test_invalid_confidence_does_not_override_explicit_anchor(tmp_path):
    model = build_book(["— Abra — disse Iara.", "— Espere — disse Nilo."])
    def response(payload):
        nilo = next(e["id"] for e in payload["entities"] if e["name"] == "Nilo")
        return {"entities": [], "assignments": [{"id": "book-0", "speaker": nilo,
                   "kind": "speech", "confidence": float("nan"), "evidence": [citation(1, "disse Nilo")]}]}
    result = review_book(model, TextProvider(response), Cache(tmp_path))
    assert result["turns"][0]["status"] == "explicit"
    assert result["turns"][0]["speaker_entity_id"] == model["turns"][0]["speaker_entity_id"]


def test_anonymous_people_are_scene_local_and_selectable(tmp_path):
    model = build_book(["Um padeiro ruivo chegou.", "— Olá!", "***", "Um padeiro ruivo chegou.", "— Oi!"])
    def response(payload):
        p = next(row["paragraph"] for row in payload["scene_text"] if "padeiro" in row["text"])
        return {"entities": [{"id": "local", "kind": "anonymous", "mention": citation(p, "padeiro ruivo")}],
                "assignments": [{"id": turn["id"], "speaker": "local", "kind": "speech", "confidence": .95,
                                 "evidence": [citation(p, "Um padeiro ruivo chegou.")]} for turn in payload["turns"]]}
    result = review_book(model, TextProvider(response), Cache(tmp_path))
    assert len(result["entities"]) == 2
    assert len({turn["speaker_entity_id"] for turn in result["turns"]}) == 2
    audio = [{"id": "1-0", "source": "book"}, {"id": "4-0", "source": "book"}]
    project_to_audio(result, audio)
    names = discover_characters({"files": [{"dialogues": audio}]})
    assert set(names) == {item["speaker"] for item in audio}


def test_duplicate_ids_do_not_replace_a_turn(tmp_path):
    model = build_book(["— Abra — disse Iara.", "— Como?"])
    def response(payload):
        decision = {"id": "book-1", "speaker": payload["entities"][0]["id"], "kind": "speech",
                    "confidence": 1, "evidence": [citation(0, "disse Iara")]}
        return {"entities": [], "assignments": [decision, decision]}
    result = review_book(model, TextProvider(response), Cache(tmp_path))
    assert result["turns"][1]["speaker_entity_id"] is None
    assert result["turns"][1]["review_issue"] == "missing_or_duplicate_assignment"


def test_context_windows_do_not_cross_scene_or_drop_targets():
    model = build_book(["— Um?", "— Dois?", "***", "— Três?"])
    batches = list(windows(model, None, max_turns=1))
    assert len(batches) == 3
    assert batches[0]["last"] <= 1
    assert batches[-1]["first"] >= 2
    oversized = list(windows(model, None, max_chars=1))
    assert sum(len(batch["turns"]) for batch in oversized) == 3
    assert all(batch["error"] == "context_limit" for batch in oversized)


def test_provider_failure_keeps_explicit_text_anchors(tmp_path):
    model = build_book(["— Abra — disse Iara.", "— Como?"])
    def fail(payload):
        raise TimeoutError("test timeout")
    result = review_book(model, TextProvider(fail), Cache(tmp_path))
    assert result["turns"][0]["status"] == "explicit"
    assert result["turns"][1]["speaker_entity_id"] is None
    assert len(result["review"]["errors"]) == 1


@pytest.mark.parametrize("protocol", ["evidence", "compact", "scene", "lightweight"])
def test_pipeline_routes_text_first_review_and_keeps_unaligned_turn_in_report(tmp_path, monkeypatch, protocol):
    from types import SimpleNamespace
    from audiobook_voice_enhancer.pipeline import Pipeline

    blocks = ["— Abra — disse Iara.", "— Como?", "— Feche — disse Nilo."]
    audio = tmp_path / "chapter.mp3"
    audio.write_bytes(b"fixture, probe and ASR are mocked")
    segments = [{"id": i, "start": i, "end": i + .8, "text": word,
                 "words": [{"word": word, "start": i, "end": i + .8}]} for i, word in ((0, "Abra"), (2, "Feche"))]
    alignments = [{"segment_id": i, "book_paragraph_id": i, "book_text": blocks[i],
                   "audio_start": i, "audio_end": i + .8, "alignment_confidence": .99} for i in (0, 2)]
    def response(payload):
        if payload.get("task") == "scene_cast":
            return {"entities": []}
        iara = next(e["id"] for e in payload["entities"] if e["name"] == "Iara")
        if protocol == "scene":
            return {"entities": [], "assignments": [{"id": turn["id"], "speaker": turn["anchor"] or iara,
                       "kind": "speech", "confidence": .95} for turn in payload["turns"]]}
        return {"entities": [], "assignments": [{"id": "T1" if protocol in {"compact", "lightweight"} else "book-1", "speaker": iara, "kind": "speech",
                   "confidence": .95, "evidence": [citation(0, "disse Iara")]}]}
    pipeline = Pipeline.__new__(Pipeline)
    pipeline.root = tmp_path
    pipeline.cache = Cache(tmp_path / "cache")
    pipeline.speaker_aliases = {}
    pipeline.characters = {"Iara": {"mode": "original"}, "Nilo": {"mode": "original"}}
    pipeline.config = {"book_first": {"enabled": True, "protocol": protocol}, "speaker_confidence_threshold": .85,
                       "alignment_confidence_threshold": .8, "minimum_segment_duration": 0}
    pipeline.llm = TextProvider(response)
    monkeypatch.setattr("audiobook_voice_enhancer.pipeline.probe", lambda _: SimpleNamespace(
        duration=3, channels=1, codec="mp3", sample_rate=24000))
    monkeypatch.setattr("audiobook_voice_enhancer.pipeline.transcribe", lambda *a, **k: {"segments": segments})
    monkeypatch.setattr("audiobook_voice_enhancer.pipeline.align_blocks", lambda *a, **k: alignments)
    def forbidden(*args, **kwargs):
        raise AssertionError("Legacy speaker review must not run in text-first mode")
    monkeypatch.setattr("audiobook_voice_enhancer.pipeline.review_scenes", forbidden)
    result = pipeline._one(audio, command="analyze", language="pt", book_blocks=blocks,
                           book_fingerprint={"fixture": True}, book_cursor=0, dry_run=False,
                           file_index=1, total_files=1)
    assert len(result["dialogues"]) == 2
    assert len(result["book_speaker_analysis"]["turns"]) == 3
    assert result["book_speaker_analysis"]["turns"][1]["status"] == "contextual"
    assert [d["speaker"] for d in result["dialogues"]] == ["Iara", "Nilo"]
    assert all(d["action"] == "skipped" for d in result["dialogues"])
    assert "speaker_attribution" in result["stage_timings"]
    assert result["stage_timings"]["probe_and_transcription"]["cache_misses"] == 1


@pytest.mark.parametrize("options", [{"max_turns_per_window": 0}, {"max_context_characters": -1},
                                     {"automatic_confidence": float("nan")}])
def test_invalid_book_settings_fail_before_transcription(tmp_path, options):
    import yaml
    from audiobook_voice_enhancer.config import ConfigurationError, load_config
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"speaker_confidence_threshold": .85, "alignment_confidence_threshold": .8,
                                   "voice_conversion": {}, "book_first": {"enabled": True, **options}}), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Análise textual"):
        load_config(path)
