from audiobook_voice_enhancer.alignment import align_blocks, map_phrase_to_words, normalize
from audiobook_voice_enhancer.dialogue import (
    _addressed_characters,
    _dash_speech_fragments,
    _infer_conversation_turns,
    _infer_addressed_replies,
    _infer_preceding_named_actions,
    _resolve_role_coreference,
    detect,
)
from audiobook_voice_enhancer.book import load_book


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


def test_lowercase_pronoun_is_not_treated_as_character_name():
    text = "Não faça isso disse ele"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 4, "text": text, "words": words(text)}]}
    alignment = [{"segment_id": 0, "book_paragraph_id": 0, "audio_start": 0, "audio_end": 4,
                  "alignment_confidence": 0.95, "book_text": '“Não faça isso”, disse ele.'}]
    found = detect(transcript, alignment)
    assert found[0]["speaker"] is None


def test_configured_alias_maps_to_canonical_character():
    text = "Não faça isso disse o bruxo"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 4, "text": text, "words": words(text)}]}
    alignment = [{"segment_id": 0, "book_paragraph_id": 0, "audio_start": 0, "audio_end": 4,
                  "alignment_confidence": 0.95, "book_text": '“Não faça isso”, disse o bruxo.'}]
    found = detect(transcript, alignment, {"bruxo": "Geralt", "lobo branco": "Geralt"})
    assert found[0]["speaker"] == "Geralt"
    assert found[0]["speaker_confidence"] == 0.98


def test_multiword_alias_maps_to_canonical_character():
    text = "Vamos disse Lobo Branco"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 3, "text": text, "words": words(text)}]}
    alignment = [{"segment_id": 0, "book_paragraph_id": 0, "audio_start": 0, "audio_end": 3,
                  "alignment_confidence": 0.95, "book_text": '“Vamos”, disse Lobo Branco.'}]
    assert detect(transcript, alignment, {"lobo branco": "Geralt"})[0]["speaker"] == "Geralt"


def test_alignment_is_monotonic_and_fuzzy():
    transcript = {"segments": [{"id": 0, "start": 1, "end": 2, "text": "Era uma vez uma menina", "words": []}]}
    aligned = align_blocks(["Capítulo Primeiro", "Era uma vez, uma pequena menina."], transcript)
    assert aligned[0]["book_paragraph_id"] == 1
    assert aligned[0]["alignment_confidence"] > 0.6


def test_alignment_can_resume_at_later_chapter():
    transcript = {"segments": [{"id": 0, "start": 1, "end": 2, "text": "Texto exclusivo capítulo dois", "words": []}]}
    aligned = align_blocks(["Texto exclusivo capítulo um", "fim", "Texto exclusivo capítulo dois"], transcript, initial_cursor=2)
    assert aligned[0]["book_paragraph_id"] == 2


def test_alignment_does_not_jump_from_serie_to_ciri():
    book = [
        "O Sangue dos Elfos",
        "— Ciri!",
        "A cidade ardia diante deles enquanto a menina observava as torres antigas e os soldados corriam pelas ruas.",
        "Depois a noite chegou silenciosa sobre os campos e todos procuraram abrigo antes que a tempestade começasse.",
    ]
    transcript = {"segments": [
        {"id": 0, "start": 0, "end": 3, "text": "O terceiro volume da série The Witcher", "words": []},
        {"id": 1, "start": 3, "end": 8, "text": "A cidade ardia diante deles enquanto a menina observava", "words": []},
        {"id": 2, "start": 8, "end": 14, "text": "as torres antigas e os soldados corriam pelas ruas", "words": []},
        {"id": 3, "start": 14, "end": 20, "text": "Depois a noite chegou silenciosa sobre os campos e todos procuraram abrigo", "words": []},
        {"id": 4, "start": 20, "end": 24, "text": "antes que a tempestade começasse", "words": []},
    ]}
    aligned = align_blocks(book, transcript)
    by_segment = {item["segment_id"]: item for item in aligned}
    assert 0 not in by_segment
    assert by_segment[1]["book_paragraph_id"] == 2
    assert by_segment[3]["book_paragraph_id"] == 3
    assert all(item["book_paragraph_id"] != 1 for item in aligned)


def test_dialogue_can_span_multiple_transcript_segments():
    first = "Vamos embora"
    second = "agora disse Geralt"
    transcript = {"segments": [
        {"id": 0, "start": 0, "end": 1, "text": first, "words": words(first)},
        {"id": 1, "start": 1, "end": 3, "text": second,
         "words": [{"word": word, "start": 1 + index * 0.5, "end": 1.4 + index * 0.5}
                   for index, word in enumerate(second.split())]},
    ]}
    book_text = "— Vamos embora agora — disse Geralt."
    alignments = [
        {"segment_id": 0, "book_paragraph_id": 4, "audio_start": 0, "audio_end": 1,
         "alignment_confidence": 0.99, "book_text": book_text},
        {"segment_id": 1, "book_paragraph_id": 4, "audio_start": 1, "audio_end": 3,
         "alignment_confidence": 0.99, "book_text": book_text},
    ]
    found = detect(transcript, alignments)
    assert len(found) == 1
    assert found[0]["speaker"] == "Geralt"
    assert found[0]["start"] == 0
    assert found[0]["end"] >= 1.4


def test_dash_dialogue_keeps_continuation_but_excludes_narrator_attribution():
    paragraph = "— Primeira frase — disse Yennefer. — Segunda frase inteira."
    fragments = _dash_speech_fragments(paragraph)
    assert [item.group(1) for item in fragments] == ["Primeira frase", "Segunda frase inteira."]
    assert [item.continuation for item in fragments] == [False, True]


def test_dash_continuation_does_not_require_a_space_after_the_mark():
    paragraph = "— Primeira — disse o sacerdote. –Segunda sem espaço."
    assert [item.group(1) for item in _dash_speech_fragments(paragraph)] == [
        "Primeira", "Segunda sem espaço."
    ]


def test_continuation_is_a_separate_audio_region_with_the_same_speaker():
    spoken = "Primeira frase disse Yennefer Segunda frase inteira"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 4, "text": spoken, "words": words(spoken)}]}
    paragraph = "— Primeira frase — disse Yennefer. — Segunda frase inteira."
    alignment = [{"segment_id": 0, "book_paragraph_id": 3, "audio_start": 0,
                  "audio_end": 4, "alignment_confidence": 0.99, "book_text": paragraph}]
    found = detect(transcript, alignment, {"yennefer": "Yennefer"}, ["x", "x", "x", paragraph])
    assert [item["text"] for item in found] == ["Primeira frase", "Segunda frase inteira."]
    assert [item["speaker"] for item in found] == ["Yennefer", "Yennefer"]
    assert found[0]["end"] < found[1]["start"]
    assert found[0]["turn_id"] == found[1]["turn_id"]
    assert found[1]["is_continuation"] is True


def test_epub_paragraph_break_can_continue_an_unfinished_dash_turn():
    blocks = ["— A regra consta em nosso", "capítulo e deve ser obedecida."]
    first = "A regra consta em nosso"
    second = "capitulo e deve ser obedecida"
    transcript = {"segments": [
        {"id": 0, "start": 0, "end": 3, "text": first, "words": words(first)},
        {"id": 1, "start": 4, "end": 7, "text": second,
         "words": [{"word": item, "start": 4 + index * .5, "end": 4.4 + index * .5}
                   for index, item in enumerate(second.split())]},
    ]}
    alignments = [
        {"segment_id": 0, "book_paragraph_id": 0, "audio_start": 0, "audio_end": 3,
         "alignment_confidence": .99, "book_text": blocks[0]},
        {"segment_id": 1, "book_paragraph_id": 1, "audio_start": 4, "audio_end": 7,
         "alignment_confidence": .99, "book_text": blocks[1]},
    ]
    found = detect(transcript, alignments, {}, blocks)
    assert [item["text"] for item in found] == blocks[0][2:].split(" — ") + [blocks[1]]
    assert found[0]["turn_id"] == found[1]["turn_id"]
    assert found[0]["fragment_count"] == 2
    assert found[1]["fragment_count"] == 2
    assert found[1]["is_continuation"] is True


def test_continuation_cannot_override_speaker_anchored_at_start_of_turn():
    dialogues = [
        {"dialogue_style": "dash", "turn_id": "book-1", "fragment_index": 0,
         "speaker": "Yennefer", "speaker_confidence": .98},
        {"dialogue_style": "dash", "turn_id": "book-1", "fragment_index": 1,
         "speaker": "Geralt", "speaker_confidence": .9},
    ]
    from audiobook_voice_enhancer.dialogue import propagate_speaker_inside_turn
    propagate_speaker_inside_turn(dialogues)
    assert [item["speaker"] for item in dialogues] == ["Yennefer", "Yennefer"]


def test_two_person_conversation_is_inferred_from_vocatives_and_turns():
    texts = ["Ciri Acalme se", "Geralt", "Foi apenas um sonho", "Geralt eu", "Estou aqui Durma Ciri"]
    book = ["— Ciri. Acalme-se.", "— Geralt...", "— Foi apenas um sonho.",
            "— Geralt, eu...", "— Estou aqui. Durma, Ciri."]
    segments = []
    alignments = []
    cursor = 0.0
    for index, (spoken, paragraph) in enumerate(zip(texts, book)):
        timed = [{"word": word, "start": cursor + offset * 0.5, "end": cursor + offset * 0.5 + 0.4}
                 for offset, word in enumerate(spoken.split())]
        end = timed[-1]["end"]
        segments.append({"id": index, "start": cursor, "end": end, "text": spoken, "words": timed})
        alignments.append({"segment_id": index, "book_paragraph_id": 40 + index,
                           "audio_start": cursor, "audio_end": end,
                           "alignment_confidence": 0.99, "book_text": paragraph})
        cursor = end + 1
    found = detect({"segments": segments}, alignments, {"ciri": "Ciri", "geralt": "Geralt"})
    assert [item["speaker"] for item in found] == ["Geralt", "Ciri", "Geralt", "Ciri", "Geralt"]
    assert all(item["speaker_confidence"] >= 0.88 for item in found)


def test_reply_belongs_to_character_addressed_in_previous_turn():
    dialogues = [
        {"id": "a", "text": "Vejo que está vivo, Lobo.", "speaker": "Eskel",
         "scene_id": 4, "book_paragraph_id": 10, "dialogue_style": "dash", "start": 0},
        {"id": "b", "text": "Estou.", "speaker": None,
         "scene_id": 4, "book_paragraph_id": 11, "dialogue_style": "dash", "start": 2},
    ]
    _infer_addressed_replies(dialogues, {"lobo": "Geralt"})
    assert dialogues[1]["speaker"] == "Geralt"
    assert dialogues[1]["speaker_confidence"] == .95


def test_action_in_preceding_paragraph_carries_speaker_to_dialogue():
    dialogues = [{"id": "a", "text": "Ela é nosso destino.", "speaker": None,
                  "scene_id": 4, "book_paragraph_id": 1, "dialogue_style": "dash", "start": 2}]
    _infer_preceding_named_actions(dialogues, {"geralt": "Geralt"},
                                    ["As mãos de Geralt apertaram seus ombros.", "— Ela é nosso destino."])
    assert dialogues[0]["speaker"] == "Geralt"
    assert dialogues[0]["speaker_confidence"] == .92


def test_reply_uses_vocative_from_full_book_paragraph():
    dialogues = [
        {"id": "a", "text": "Quem vem lá?", "speaker": None, "scene_id": 2,
         "book_paragraph_id": 0, "dialogue_style": "dash", "start": 0},
        {"id": "b", "text": "Sim, Eskel, sou eu.", "speaker": None, "scene_id": 2,
         "book_paragraph_id": 1, "dialogue_style": "dash", "start": 2},
    ]
    book = ["— Quem vem lá? — perguntou a voz. — É você, Geralt?", "— Sim, Eskel, sou eu."]
    _infer_addressed_replies(dialogues, {"geralt": "Geralt", "eskel": "Eskel"}, book)
    assert dialogues[1]["speaker"] == "Geralt"


def test_turn_inference_stays_unknown_when_only_one_participant_is_named():
    spoken = ["Ciri venha", "Vamos embora", "Depressa"]
    paragraphs = ["— Ciri, venha.", "— Vamos embora.", "— Depressa."]
    transcript = {"segments": []}
    alignments = []
    for index, (text, paragraph) in enumerate(zip(spoken, paragraphs)):
        transcript["segments"].append({"id": index, "start": index * 2, "end": index * 2 + 1,
                                       "text": text, "words": words(text)})
        alignments.append({"segment_id": index, "book_paragraph_id": index, "audio_start": index * 2,
                           "audio_end": index * 2 + 1, "alignment_confidence": 0.99,
                           "book_text": paragraph})
    found = detect(transcript, alignments, {"ciri": "Ciri", "geralt": "Geralt"})
    assert all(item["speaker"] is None for item in found)


def test_self_introduction_is_not_mistaken_for_a_vocative():
    aliases = {"rayla de líria": "Rayla de Líria", "geralt": "Geralt"}
    assert _addressed_characters("Eu, Rayla de Líria, conheço Geralt.", aliases) == set()


def test_alternation_is_rejected_when_right_anchor_disagrees():
    dialogues = [
        {"id": "1", "turn_id": "book-1", "text": "Primeira", "speaker": "Ana",
         "speaker_confidence": .98, "scene_id": 1, "book_paragraph_id": 1,
         "dialogue_style": "dash", "start": 0, "end": 1},
        {"id": "2", "turn_id": "book-2", "text": "Segunda", "speaker": None,
         "speaker_confidence": 0, "scene_id": 1, "book_paragraph_id": 2,
         "dialogue_style": "dash", "start": 2, "end": 3},
        {"id": "3", "turn_id": "book-3", "text": "Terceira, Bia.", "speaker": "Bia",
         "speaker_confidence": .98, "scene_id": 1, "book_paragraph_id": 3,
         "dialogue_style": "dash", "start": 4, "end": 5},
    ]
    _infer_conversation_turns(dialogues, {"ana": "Ana", "bia": "Bia"})
    assert dialogues[1]["speaker"] is None


def test_fragments_of_one_turn_do_not_advance_conversation_parity():
    dialogues = [
        {"id": "1-0", "turn_id": "book-1", "fragment_index": 0, "text": "Olá, Bia.",
         "speaker": "Ana", "speaker_confidence": .98, "scene_id": 1,
         "book_paragraph_id": 1, "dialogue_style": "dash", "start": 0, "end": 1},
        {"id": "1-1", "turn_id": "book-1", "fragment_index": 1, "text": "Ainda sou eu.",
         "speaker": "Ana", "speaker_confidence": .98, "scene_id": 1,
         "book_paragraph_id": 1, "dialogue_style": "dash", "start": 1.2, "end": 2},
        {"id": "2-0", "turn_id": "book-2", "fragment_index": 0, "text": "Resposta.",
         "speaker": None, "speaker_confidence": 0, "scene_id": 1,
         "book_paragraph_id": 2, "dialogue_style": "dash", "start": 3, "end": 4},
        {"id": "3-0", "turn_id": "book-3", "fragment_index": 0, "text": "Outra fala, Bia.",
         "speaker": "Ana", "speaker_confidence": .98, "scene_id": 1,
         "book_paragraph_id": 3, "dialogue_style": "dash", "start": 5, "end": 6},
    ]
    _infer_conversation_turns(dialogues, {"ana": "Ana", "bia": "Bia"})
    assert dialogues[2]["speaker"] == "Bia"


def test_topic_name_does_not_expand_cast_when_two_speakers_are_anchored():
    dialogues = []
    speakers = ["Yennefer", None, None, "Jaskier"]
    texts = ["Não faça isso.", "Sim, você disse.", "E Rience?", "Suponhamos..."]
    for index, (speaker, text) in enumerate(zip(speakers, texts)):
        dialogues.append({"id": str(index), "turn_id": f"book-{index}", "text": text,
                          "speaker": speaker, "speaker_confidence": .98 if speaker else 0,
                          "scene_id": 1, "book_paragraph_id": index,
                          "dialogue_style": "dash", "start": index * 2, "end": index * 2 + 1})
    aliases = {"yennefer": "Yennefer", "jaskier": "Jaskier", "rience": "Rience"}
    _infer_conversation_turns(dialogues, aliases)
    assert [item["speaker"] for item in dialogues] == ["Yennefer", "Jaskier", "Yennefer", "Jaskier"]


def test_third_person_vocative_blocks_two_person_alternation():
    dialogues = []
    speakers = ["Jaskier", None, None, "Yennefer"]
    texts = ["Obrigado.", "Ei, senhor taberneiro!", "Às ordens.", "Continue."]
    for index, (speaker, value) in enumerate(zip(speakers, texts)):
        dialogues.append({"id": str(index), "turn_id": f"book-{index}", "text": value,
                          "speaker": speaker, "speaker_confidence": .98 if speaker else 0,
                          "scene_id": 1, "book_paragraph_id": index,
                          "dialogue_style": "dash", "start": index * 2, "end": index * 2 + 1})
    aliases = {"jaskier": "Jaskier", "yennefer": "Yennefer", "taberneiro": "Taberneiro"}
    _infer_conversation_turns(dialogues, aliases)
    assert dialogues[1]["speaker"] is None
    assert dialogues[2]["speaker"] is None


def test_quoted_thought_is_not_inferred_as_spoken_turn():
    spoken = ["Por que ninguem me ajuda", "Ciri Acalme se", "Geralt", "Durma Ciri"]
    paragraphs = ['Ela pensou: “Por que ninguém me ajuda?”', "— Ciri. Acalme-se.",
                  "— Geralt...", "— Durma, Ciri."]
    transcript = {"segments": []}
    alignments = []
    for index, (text, paragraph) in enumerate(zip(spoken, paragraphs)):
        timed = [{"word": word, "start": index * 2 + offset * 0.2,
                  "end": index * 2 + offset * 0.2 + 0.15} for offset, word in enumerate(text.split())]
        transcript["segments"].append({"id": index, "start": index * 2, "end": timed[-1]["end"],
                                       "text": text, "words": timed})
        alignments.append({"segment_id": index, "book_paragraph_id": 36 + index,
                           "audio_start": index * 2, "audio_end": timed[-1]["end"],
                           "alignment_confidence": 0.99, "book_text": paragraph})
    found = detect(transcript, alignments, {"ciri": "Ciri", "geralt": "Geralt"})
    assert found[0]["speaker"] is None
    assert [item["speaker"] for item in found[1:]] == ["Geralt", "Ciri", "Geralt"]


def test_unclosed_dash_does_not_include_following_narration():
    spoken = "Foi apenas um sonho Durma tranquila Ele nao voltara Ciri ouvira essas palavras"
    timed = words(spoken)
    transcript = {"segments": [{"id": 0, "start": 0, "end": timed[-1]["end"],
                                 "text": spoken, "words": timed}]}
    paragraph = "— Foi apenas um sonho. Durma tranquila. Ele não voltará. Ciri ouvira essas palavras."
    alignment = [{"segment_id": 0, "book_paragraph_id": 56, "audio_start": 0,
                  "audio_end": timed[-1]["end"], "alignment_confidence": 0.99,
                  "book_text": paragraph}]
    found = detect(transcript, alignment, {"ciri": "Ciri", "geralt": "Geralt"})
    assert found[0]["text"] == "Foi apenas um sonho. Durma tranquila. Ele não voltará."
    assert found[0]["end"] < timed[-1]["end"]


def test_named_speaker_is_discovered_from_book_on_first_pass():
    text = "Nao foi apenas isso falou Radcliffe"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 3, "text": text, "words": words(text)}]}
    block = "— Não foi apenas isso — falou Radcliffe com voz firme."
    alignment = [{"segment_id": 0, "book_paragraph_id": 0, "audio_start": 0, "audio_end": 3,
                  "alignment_confidence": 0.99, "book_text": block}]
    found = detect(transcript, alignment, {}, [block])
    assert found[0]["speaker"] == "Radcliffe"
    assert found[0]["speaker_confidence"] == 0.98


def test_self_introduction_discovers_full_character_name():
    text = "Pois eu Rayla de Liria conheco Geralt"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 4, "text": text, "words": words(text)}]}
    block = "— Pois eu, Rayla de Líria, conheço Geralt — afirmou a guerreira."
    alignment = [{"segment_id": 0, "book_paragraph_id": 0, "audio_start": 0, "audio_end": 4,
                  "alignment_confidence": 0.99, "book_text": block}]
    found = detect(transcript, alignment, {}, [block])
    assert found[0]["speaker"] == "Rayla de Líria"


def test_addressee_in_attribution_is_not_selected_as_speaker():
    text = "Gostaria de saber do lado de quem"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 4, "text": text, "words": words(text)}]}
    block = "— Gostaria de saber do lado de quem — comentou com Radcliffe o chanceler Vilibert."
    alignment = [{"segment_id": 0, "book_paragraph_id": 0, "audio_start": 0, "audio_end": 4,
                  "alignment_confidence": 0.99, "book_text": block}]
    found = detect(transcript, alignment, {"radcliffe": "Radcliffe", "vilibert": "Vilibert"}, [block])
    assert found[0]["speaker"] == "Vilibert"


def test_quote_inside_dash_speech_is_not_a_separate_dialogue():
    text = "Lembrem se da profecia o mundo vai morrer assim falou a sibila"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 6, "text": text, "words": words(text)}]}
    block = '— Lembrem-se da profecia: “O mundo vai morrer.” Assim falou a sibila!'
    alignment = [{"segment_id": 0, "book_paragraph_id": 0, "audio_start": 0, "audio_end": 6,
                  "alignment_confidence": 0.99, "book_text": block}]
    found = detect(transcript, alignment, {}, [block])
    assert len(found) == 1


def test_named_subject_action_after_speech_identifies_speaker():
    text = "Voce acha"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 2, "text": text, "words": words(text)}]}
    block = "— Você acha? — Yennefer endireitou-se e pegou a adaga."
    alignment = [{"segment_id": 0, "book_paragraph_id": 0, "audio_start": 0, "audio_end": 2,
                  "alignment_confidence": 0.99, "book_text": block}]
    found = detect(transcript, alignment, {"yennefer": "Yennefer"}, [block])
    assert found[0]["speaker"] == "Yennefer"


def test_listener_reaction_after_speech_is_not_selected_as_speaker():
    text = "Que droga Uma menina Ciri olhou para ele assustada"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 5, "text": text, "words": words(text)}]}
    block = "— Que droga! — rosnou. — Uma menina. Ciri olhou para ele assustada."
    alignment = [{"segment_id": 0, "book_paragraph_id": 0, "audio_start": 0,
                  "audio_end": 5, "alignment_confidence": .99, "book_text": block}]
    found = detect(transcript, alignment, {"ciri": "Ciri"}, [block])
    assert all(item["speaker"] is None for item in found)


def test_explicit_anonymous_role_becomes_selectable_character():
    text = "Calma calma disse com voz forte um druida grisalho"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 4, "text": text, "words": words(text)}]}
    block = "— Calma, calma! — disse com voz forte um druida grisalho vestido de branco."
    alignment = [{"segment_id": 0, "book_paragraph_id": 0, "audio_start": 0,
                  "audio_end": 4, "alignment_confidence": .99, "book_text": block}]
    found = detect(transcript, alignment, {}, [block])
    assert found[0]["speaker"] == "Druida grisalho"
    assert found[0]["speaker_confidence"] == .96


def test_plural_speech_verb_identifies_anonymous_group():
    text = "Nao poderia apoiaram as sacerdotisas"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 3, "text": text, "words": words(text)}]}
    block = "— Não poderia! — apoiaram as sacerdotisas assustadas."
    alignment = [{"segment_id": 0, "book_paragraph_id": 0, "audio_start": 0,
                  "audio_end": 3, "alignment_confidence": .99, "book_text": block}]
    found = detect(transcript, alignment, {}, [block])
    assert found[0]["speaker"] == "Sacerdotisas assustadas"


def test_name_inside_possessed_role_is_not_selected_as_speaker():
    text = "Nao poderia apoiaram as filhas do chanceler Vilibert"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 4, "text": text, "words": words(text)}]}
    block = "— Não poderia! — apoiaram as filhas do chanceler Vilibert."
    alignment = [{"segment_id": 0, "book_paragraph_id": 0, "audio_start": 0,
                  "audio_end": 4, "alignment_confidence": .99, "book_text": block}]
    found = detect(transcript, alignment, {"vilibert": "Vilibert"}, [block])
    assert found[0]["speaker"] == "Filhas do chanceler Vilibert"


def test_anonymous_role_uses_one_stable_description_per_scene():
    dialogues = [
        {"id": "1", "turn_id": "book-1", "fragment_index": 0, "speaker": "Gnomo narigudo",
         "speaker_confidence": .96, "reason": "personagem anônimo descrito explicitamente",
         "attribution_role": "gnomo", "scene_id": 2},
        {"id": "2", "turn_id": "book-2", "fragment_index": 0, "speaker": "Gnomo dos artigos",
         "speaker_confidence": .96, "reason": "personagem anônimo descrito explicitamente",
         "attribution_role": "gnomo", "scene_id": 2},
    ]
    _resolve_role_coreference(dialogues)
    assert [item["speaker"] for item in dialogues] == ["Gnomo dos artigos", "Gnomo dos artigos"]


def test_self_identification_in_same_paragraph_attributes_opening_speech():
    text = "Agradeco lhe mestre Jaskier Permitam que eu Radcliffe de Oxenfurt diga algumas palavras"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 8, "text": text, "words": words(text)}]}
    block = "— Agradeço-lhe, mestre Jaskier — disse com voz baixa. — Permitam que eu, Radcliffe de Oxenfurt, diga algumas palavras."
    alignment = [{"segment_id": 0, "book_paragraph_id": 0, "audio_start": 0, "audio_end": 8,
                  "alignment_confidence": 0.99, "book_text": block}]
    found = detect(transcript, alignment, {"jaskier": "Jaskier"}, [block])
    assert found[0]["speaker"] == "Radcliffe de Oxenfurt"


def test_role_memory_resolves_character_later_in_same_scene():
    blocks = ["— Eu confirmo — disse uma esbelta guerreira. — Eu, Rayla de Líria, conheço Geralt.",
              "— Não acredito nisso — refutou a guerreira."]
    transcript = {"segments": []}
    alignments = []
    for index, text in enumerate(("Eu confirmo", "Nao acredito nisso")):
        timed = words(text)
        for word in timed:
            word["start"] += index * 3
            word["end"] += index * 3
        transcript["segments"].append({"id": index, "start": index * 3, "end": timed[-1]["end"],
                                       "text": text, "words": timed})
        alignments.append({"segment_id": index, "book_paragraph_id": index,
                           "audio_start": index * 3, "audio_end": timed[-1]["end"],
                           "alignment_confidence": 0.99, "book_text": blocks[index]})
    found = detect(transcript, alignments, {}, blocks)
    assert found[-1]["speaker"] == "Rayla de Líria"
    assert found[-1]["reason"] == "memória de papel do personagem nesta cena"


def test_ambiguous_role_is_not_learned():
    blocks = ["O feiticeiro Radcliffe chegou. O feiticeiro Artorius sentou-se.",
              "— Silêncio — disse o feiticeiro."]
    text = "Silencio"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 1, "text": text, "words": words(text)}]}
    alignment = [{"segment_id": 0, "book_paragraph_id": 1, "audio_start": 0, "audio_end": 1,
                  "alignment_confidence": 0.99, "book_text": blocks[1]}]
    found = detect(transcript, alignment, {"radcliffe": "Radcliffe", "artorius": "Artorius"}, blocks)
    assert found[0]["speaker"] is None


def test_role_mentioned_after_pronoun_is_not_the_speaker():
    blocks = ["O feiticeiro Radcliffe chegou.",
              "— Continuarei — disse ele, sem olhar para o feiticeiro."]
    text = "Continuarei"
    transcript = {"segments": [{"id": 0, "start": 0, "end": 1, "text": text, "words": words(text)}]}
    alignment = [{"segment_id": 0, "book_paragraph_id": 1, "audio_start": 0, "audio_end": 1,
                  "alignment_confidence": 0.99, "book_text": blocks[1]}]
    found = detect(transcript, alignment, {"radcliffe": "Radcliffe"}, blocks)
    assert found[0]["speaker"] is None


def test_book_txt_accepts_windows_1252(tmp_path):
    path = tmp_path / "livro.txt"
    path.write_bytes("Capítulo — não".encode("cp1252"))
    assert load_book(path) == "Capítulo — não"


def test_epub_preserves_paragraph_boundaries(tmp_path):
    from ebooklib import epub
    book = epub.EpubBook()
    book.set_identifier("test")
    book.set_title("Teste")
    book.set_language("pt")
    chapter = epub.EpubHtml(title="Capítulo", file_name="chapter.xhtml", lang="pt")
    chapter.content = "<h1>Capítulo primeiro</h1><p>Primeiro parágrafo.</p><p>Segundo parágrafo.</p>"
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = [chapter]
    target = tmp_path / "book.epub"
    epub.write_epub(str(target), book)
    content = load_book(target)
    assert "Capítulo primeiro\n\nPrimeiro parágrafo.\n\nSegundo parágrafo." in content
