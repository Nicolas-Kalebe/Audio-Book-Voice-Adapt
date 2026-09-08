import pytest

from audiobook_voice_enhancer.book_speakers import build_book, review_book, windows
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.dialogue import _scene_numbers
from audiobook_voice_enhancer.llm import LLMProvider
from audiobook_voice_enhancer.scene_context import SceneContext


def test_chapter_word_inside_continuing_speech_keeps_scene_and_context(tmp_path):
    blocks = ['— A decisão foi tomada pelo nosso',
              'Capítulo reunido ontem. Você concorda?', '— Concordo.']
    model = build_book(blocks)
    assert len(model['scenes']) == 1
    assert [f['paragraph'] for f in model['turns'][0]['fragments']] == [0, 1]

    class Provider(LLMProvider):
        model = 'complete-context-fixture'

        def infer(self, payload):
            assert [p['text'] for p in payload['scene_text']] == blocks
            available = {p['paragraph'] for p in payload['scene_text']}
            assert all(f['paragraph'] in available for t in payload['turns'] for f in t['fragments'])
            return {'entities': [], 'assignments': [
                {'id': t['id'], 'speaker': None, 'kind': 'unknown', 'confidence': 0}
                for t in payload['turns']]}

    result = review_book(model, Provider(), Cache(tmp_path), protocol='lightweight')
    assert result['review']['errors'] == []
    assert result['review']['batches_reviewed'] == 1
    assert result['review']['dialogues_reviewed'] == 2


@pytest.mark.parametrize('heading', ['Capítulo', 'CAPÍTULO 12', 'Chapter IV', 'Capítulo 3 — A viagem', 'CAPÍTULO PRIMEIRO'])
def test_real_chapter_headings_still_start_scenes(heading):
    assert _scene_numbers(['Uma cena.', heading, 'Outra cena.']) == {0: 0, 1: 1, 2: 1}


def test_existing_cross_scene_turn_is_complete_or_explicitly_over_budget(tmp_path):
    model = build_book(['— A mensagem termina', 'aqui.'])
    # Represents imported/cached segmentation with a boundary inside the turn.
    model['scenes'] = [dict(id=0, first_paragraph=0, last_paragraph=0),
                       dict(id=1, first_paragraph=1, last_paragraph=1)]
    batch, = windows(model, None)
    assert (batch['first'], batch['last']) == (0, 1)
    expanded = SceneContext(model, None, Cache(tmp_path)).expand(batch)
    assert (expanded['first'], expanded['last']) == (0, 1)
    too_small, = windows(model, None, max_chars=len(model['blocks'][0]))
    assert too_small['error'] == 'context_limit'
    assert len(too_small['turns'][0]['fragments']) == 2
