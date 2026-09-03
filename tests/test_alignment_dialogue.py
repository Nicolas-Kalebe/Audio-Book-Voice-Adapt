from audiobook_voice_enhancer.alignment import align_blocks, map_phrase_to_words, normalize
from audiobook_voice_enhancer.dialogue import detect
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
