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


def test_alignment_is_monotonic_and_fuzzy():
    transcript = {"segments": [{"id": 0, "start": 1, "end": 2, "text": "Era uma vez uma menina", "words": []}]}
    aligned = align_blocks(["Capítulo Primeiro", "Era uma vez, uma pequena menina."], transcript)
    assert aligned[0]["book_paragraph_id"] == 1
    assert aligned[0]["alignment_confidence"] > 0.6


def test_alignment_can_resume_at_later_chapter():
    transcript = {"segments": [{"id": 0, "start": 1, "end": 2, "text": "Texto exclusivo capítulo dois", "words": []}]}
    aligned = align_blocks(["Texto exclusivo capítulo um", "fim", "Texto exclusivo capítulo dois"], transcript, initial_cursor=2)
    assert aligned[0]["book_paragraph_id"] == 2


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
