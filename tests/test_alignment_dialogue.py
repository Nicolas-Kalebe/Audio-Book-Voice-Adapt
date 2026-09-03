from audiobook_voice_enhancer.alignment import align_blocks, map_phrase_to_words, normalize
from audiobook_voice_enhancer.dialogue import detect


def words(text):
    return [{"word": word, "start": index * 0.5, "end": index * 0.5 + 0.4} for index, word in enumerate(text.split())]


def test_normalize_accents_and_punctuation():
    assert normalize("Não, FAÇA isso!") == "nao faca isso"


def test_phrase_maps_to_word_boundaries():
    value = map_phrase_to_words("Não faça isso", words("Yennefer olhou Não faça isso agora"))
    assert value is not None
    assert value[0] == 1.0
    assert value[1] >= 2.4


def test_explicit_dialogue_uses_only_dialogue_words():
    text = "Yennefer olhou. Não faça isso disse Yennefer"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 4, "text": text, "words": words(text)}]}
    alignment = [{"segment_id": 0, "book_paragraph_id": 0, "audio_start": 0, "audio_end": 4,
                  "alignment_confidence": 0.95, "book_text": 'Yennefer olhou. “Não faça isso”, disse Yennefer.'}]
    found = detect(transcript, alignment)
    assert len(found) == 1
    assert found[0]["speaker"] == "Yennefer"
    assert found[0]["speaker_confidence"] == 0.98
    assert found[0]["start"] > 0


def test_alignment_is_monotonic_and_fuzzy():
    transcript = {"segments": [{"id": 0, "start": 1, "end": 2, "text": "Era uma vez uma menina", "words": []}]}
    aligned = align_blocks(["Capítulo Primeiro", "Era uma vez, uma pequena menina."], transcript)
    assert aligned[0]["book_paragraph_id"] == 1
    assert aligned[0]["alignment_confidence"] > 0.6

