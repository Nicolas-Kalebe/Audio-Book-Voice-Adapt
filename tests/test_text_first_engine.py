import copy

import pytest

from audiobook_voice_enhancer.book_inventory import audio_coverage, dialogue_inventory
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.dialogue import _recover_short_dialogue_alignments, detect
from audiobook_voice_enhancer.llm import LLMProvider, _confidence, _decisions, cached_infer, review_scenes
from audiobook_voice_enhancer.reporting import summarize


def short_turn_fixture(audio="Portas estão abertas Sim Então todos entraram"):
    blocks = ["Portas estão abertas.", "— Sim?", "Então todos entraram."]
    words = [{"word": token, "start": float(i), "end": i + .8} for i, token in enumerate(audio.split())]
    segment = {"id": 0, "text": audio, "words": words, "start": 0, "end": words[-1]["end"]}
    alignments = [{"segment_id": 0, "book_paragraph_id": i, "book_text": blocks[i],
                   "audio_start": 0, "audio_end": segment["end"], "alignment_confidence": .99} for i in (0, 2)]
    return blocks, {"segments": [segment]}, alignments


def test_short_turn_uses_only_original_words_between_anchors():
    blocks, transcript, aligned = short_turn_fixture()
    before = copy.deepcopy((transcript, aligned))
    recovered = _recover_short_dialogue_alignments(transcript, aligned, blocks)
    assert recovered[-1]["recovery_word_range"] == [3, 4]
    found = detect(transcript, aligned, {}, blocks)
    short = next(item for item in found if item["book_paragraph_id"] == 1)
    assert (short["start"], short["end"]) == (3, 3.8)
    assert short["timing_method"] == "exact_short_turn_between_anchors"
    assert (transcript, aligned) == before


@pytest.mark.parametrize("audio", [
    "Sim Portas estão abertas Então todos entraram",  # Unique but outside the gap.
    "Então todos entraram Sim Portas estão abertas",  # Reversed chronology.
    "Portas estão abertas Sim Sim Então todos entraram",  # Ambiguous short word.
    "Portas estão abertas Então todos entraram",  # Not transcribed: don't invent timing.
    "Portas estão fechadas Sim Então todos entraram",  # Missing exact left anchor.
])
def test_short_turn_abstains_without_unique_ordered_anchors(audio):
    blocks, transcript, aligned = short_turn_fixture(audio)
    assert _recover_short_dialogue_alignments(transcript, aligned, blocks) == aligned


def test_short_turn_does_not_steal_same_word_outside_the_gap():
    blocks, transcript, aligned = short_turn_fixture("Sim Portas estão abertas Sim Então todos entraram Sim")
    found = detect(transcript, aligned, {}, blocks)
    short = next(item for item in found if item["book_paragraph_id"] == 1)
    assert (short["start"], short["end"]) == (4, 4.8)


def test_short_turn_anchors_can_cross_asr_segment_boundaries():
    blocks, transcript, aligned = short_turn_fixture()
    timed = transcript["segments"][0]["words"]
    transcript["segments"] = [
        {"id": index, "words": chunk, "start": chunk[0]["start"], "end": chunk[-1]["end"]}
        for index, chunk in enumerate((timed[:2], timed[2:5], timed[5:]))]
    aligned[1]["segment_id"] = 2
    recovered = _recover_short_dialogue_alignments(transcript, aligned, blocks)
    assert recovered[-1]["book_paragraph_id"] == 1
    assert (recovered[-1]["audio_start"], recovered[-1]["audio_end"]) == (3, 3.8)


def test_short_turn_abstains_for_long_gap_or_new_scene():
    blocks, transcript, aligned = short_turn_fixture()
    for word in transcript["segments"][0]["words"][4:]:
        word["start"] += 20
        word["end"] += 20
    assert _recover_short_dialogue_alignments(transcript, aligned, blocks) == aligned
    blocks, transcript, aligned = short_turn_fixture()
    blocks[2] = "Capítulo novo"
    assert _recover_short_dialogue_alignments(transcript, aligned, blocks) == aligned


def test_inventory_retains_missing_and_ambiguous_quotes_without_invented_audio():
    blocks = ["— Abra — disse Iara. — Agora!", "— Sim?", '“Será verdade?”, pensou Nilo.', "Fim."]
    inventory = dialogue_inventory(blocks)
    assert len(inventory) == 4
    for item in inventory:
        assert blocks[item["paragraph"]][item["char_start"]:item["char_end"]] == item["text"]
    assert inventory[0]["turn_id"] == inventory[1]["turn_id"]
    assert inventory[-1]["requires_speech_validation"]
    coverage = audio_coverage(inventory, [{"book_paragraph_id": 0, "alignment_confidence": .99},
                                         {"book_paragraph_id": 3, "alignment_confidence": .99}],
                              [{"id": "0-0", "source": "book"}])
    assert coverage["candidates_located"] == 1
    assert coverage["candidates_not_detected"] == 3
    assert coverage["candidate_location_rate"] == .25
    assert all("start" not in candidate for candidate in coverage["candidates"])


def test_inventory_without_alignment_cannot_claim_book_is_missing_from_audio():
    coverage = audio_coverage(dialogue_inventory(["— Volte aqui!"]), [], [])
    assert coverage["scope"] == "unknown"
    assert coverage["book_candidates_total"] == 1
    assert coverage["candidate_location_rate"] is None
    assert coverage["candidates_not_detected"] == 0


def test_inventory_tracks_epub_continuation():
    inventory = dialogue_inventory(["— Preciso encontrar", "a saída."])
    assert len(inventory) == 2
    assert inventory[0]["turn_id"] == inventory[1]["turn_id"]


def test_new_described_people_are_not_merged_with_named_occupation_owner():
    blocks = ["O druida Nilo chegou.", "— Venha — disse um druida grisalho.",
              "— Pare — disse um druida ruivo."]
    transcript = {"segments": []}
    alignments = []
    for i, text in enumerate(("Venha", "Pare"), 1):
        transcript["segments"].append({"id": i, "text": text, "start": i, "end": i + .8,
                                       "words": [{"word": text, "start": i, "end": i + .8}]})
        alignments.append({"segment_id": i, "book_paragraph_id": i, "book_text": blocks[i],
                           "audio_start": i, "audio_end": i + .8, "alignment_confidence": .99})
    found = detect(transcript, alignments, {"nilo": "Nilo"}, blocks)
    assert [item["speaker"] for item in found] == ["Druida grisalho", "Druida ruivo"]


def test_chapter_local_ids_do_not_collapse_character_counts():
    files = [{"input": name, "dialogues": [{"id": "0-0", "turn_id": "transcript-0-0", "speaker": "Iara"}]}
             for name in ("capitulo1.mp3", "capitulo2.mp3")]
    report = summarize(files, {}, {}, 0, "fake", "fake")
    assert report["dialogues_detected"] == 2
    assert report["characters_detected"] == {"Iara": 2}


class RecordingProvider(LLMProvider):
    model = "synthetic"

    def __init__(self, confidence=.99):
        self.payloads = []
        self.confidence = confidence

    def infer(self, payload):
        self.payloads.append(copy.deepcopy(payload))
        return {"assignments": [{"id": item["id"], "speaker": "Iara", "confidence": self.confidence,
                                 "reason": "synthetic test"} for item in payload["target_dialogues"]]}


def test_second_reading_never_receives_first_proposal_or_target_guess(tmp_path):
    provider = RecordingProvider()
    target = {"id": "1", "speaker": "Nilo", "speaker_confidence": .1, "scene_id": 1,
              "book_paragraph_id": 0, "text": "Abra a porta", "reason": "old guess"}
    stats = review_scenes(provider, Cache(tmp_path), [target], ["— Abra a porta — disse Iara."],
                          {"Iara", "Nilo"}, .85)
    assert stats["assigned"] == 1
    assert stats["confidence_is_calibrated"] is False
    assert len(provider.payloads) == 2
    second = provider.payloads[1]
    assert second["review_pass"] == "blind_second_reading"
    assert "proposed_assignments" not in second
    assert "current_speaker" not in second["target_dialogues"][0]
    assert second["chronological_dialogues"][0]["speaker_if_anchored"] is None


def test_agreement_does_not_reduce_threshold_even_with_two_speakers(tmp_path):
    provider = RecordingProvider(.91)
    target = {"id": "t", "speaker": None, "speaker_confidence": 0, "scene_id": 1,
              "book_paragraph_id": 1, "text": "Abra a porta"}
    anchors = [{"id": name, "speaker": name, "speaker_confidence": .99, "scene_id": 1,
                "book_paragraph_id": i, "text": "Fala"} for i, name in enumerate(("Iara", "Nilo"))]
    stats = review_scenes(provider, Cache(tmp_path), [target, *anchors], ["texto", "— Abra a porta"],
                          {"Iara", "Nilo"}, .85)
    assert target["speaker"] is None
    assert stats["suggested_for_review"] == 1


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -1, 2, "certo", None, True, {}])
def test_invalid_confidence_cannot_turn_into_an_accepted_anchor(invalid):
    assert _confidence(invalid) == 0


def test_duplicate_decisions_abstain():
    assert _decisions([{"id": "1", "speaker": "Iara"}, {"id": "1", "speaker": "Nilo"}]) == {}
    assert _decisions([{"id": "1", "speaker": ["Iara"]}]) == {}


def test_llm_cache_tracks_prompt_and_endpoint(tmp_path, monkeypatch):
    provider = RecordingProvider()
    payload = {"target_dialogues": []}
    cache = Cache(tmp_path)
    cached_infer(provider, cache, payload)
    cached_infer(provider, cache, payload)
    assert len(provider.payloads) == 1
    monkeypatch.setattr("audiobook_voice_enhancer.llm.SYSTEM", "changed instruction")
    cached_infer(provider, cache, payload)
    provider.url = "http://another-local-provider"
    cached_infer(provider, cache, payload)
    assert len(provider.payloads) == 3
