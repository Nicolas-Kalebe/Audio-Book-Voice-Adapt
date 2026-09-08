import copy

import pytest

from audiobook_voice_enhancer.book_speakers import build_book, review_book
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.compact_speakers import SCHEMA, SYSTEM
from audiobook_voice_enhancer.llm import LLMProvider
from audiobook_voice_enhancer.speaker_subjects import seed_subjects


def test_title_discovers_named_subject_without_audio_or_generated_catalog():
    model = build_book(['— Podemos ir — disse a capitã Luma.', '— Certo — respondeu o médico Bento.'])
    seed_subjects(model)
    assert [model['entities'][t['speaker_entity_id']]['name'] for t in model['turns']] == ['Luma', 'Bento']
    assert all(t['status'] == 'explicit' for t in model['turns'])
    for t in model['turns']:
        for span in t['evidence']:
            assert model['blocks'][span['paragraph']][span['start']:span['end']] == span['quote']


def test_possessed_name_is_not_the_speaking_group():
    model = build_book(['— Sim — disseram as filhas de Luma.', '— Vamos — piaram as filhas de Luma.'])
    seed_subjects(model)
    assert all(t['speaker_entity_id'] is None for t in model['turns'])
    assert not any(e['kind'] == 'named' for e in model['entities'].values())
    assert model['turns'][0]['source_subjects'][0]['quote'] == 'as filhas de Luma'
    assert model['turns'][1]['source_subjects'][0]['quote'] == 'as filhas de Luma'


def test_repeated_description_keeps_distinct_source_references():
    model = build_book(['— Abra — disse um guarda alto.', '— Feche — disse outro guarda.', '— Venha — disse um guarda alto.'])
    seed_subjects(model)
    first, last = model['turns'][0], model['turns'][2]
    assert first['source_subjects'][0]['entity_id'] != last['source_subjects'][0]['entity_id']
    assert all(t['speaker_entity_id'] is None for t in model['turns'])


@pytest.mark.parametrize('text', [
    '— Abra — disse para a capitã Luma.',
    '— Abra — ela olhou para a capitã Luma.',
    '— Abra — disse com a voz baixa.',
    '— Abra — disse ela.',
])
def test_non_subject_material_does_not_create_candidate(text):
    model = build_book([text])
    seed_subjects(model)
    assert not model['turns'][0].get('source_subjects')


def test_compact_reference_option_keeps_schema_and_known_candidates(tmp_path):
    model = build_book(['— Olá — disse Luma.', '— Venha — disse a capitã de uniforme azul.',
                        '— Bento está longe. — Luma suspirou.', '***', '— Sim — disse Bento.'])
    original = copy.deepcopy(model)
    calls = []

    class Provider(LLMProvider):
        model = 'source-subject-fixture'

        def infer(self, payload):
            calls.append(payload)
            assert self.response_schema == SCHEMA
            assert self.system_prompt.startswith(SYSTEM)
            ids = {e['name']: e['id'] for e in payload['entities']}
            assert {'Luma', 'Bento', 'capitã de uniforme azul'} <= ids.keys()
            reference = payload['turns'][1]['source_subject'][0]
            assert reference['candidate'] == ids['capitã de uniforme azul']
            # The description may refer to an already named person; selecting
            # that person must not force a new anonymous identity into the result.
            return {'entities': [], 'assignments': [
                {'id': t['id'], 'speaker': ids['Luma'], 'kind': 'speech', 'confidence': .96}
                for t in payload['turns']]}

    result = review_book(model, Provider(), Cache(tmp_path), (0, 2), protocol='compact', source_subjects=True)
    assert model == original
    assert len(calls) == result['review']['batches_reviewed'] == 1
    assert result['review']['errors'] == []
    assert result['entities'][result['turns'][1]['speaker_entity_id']]['name'] == 'Luma'


def test_plain_compact_remains_an_unchanged_control(tmp_path):
    model = build_book(['— Abra — disse a capitã Luma.'])
    class Provider(LLMProvider):
        model = 'plain-control-fixture'

        def infer(self, payload):
            assert self.system_prompt == SYSTEM and self.response_schema == SCHEMA
            assert 'source_subject' not in payload['turns'][0]
            assert payload['entities'] == []
            return {'entities': [], 'assignments': []}

    result = review_book(model, Provider(), Cache(tmp_path), protocol='compact')
    assert result['review']['errors'] == []
    assert result['turns'][0]['speaker_entity_id'] is None


def test_reference_option_cannot_silently_run_with_another_protocol(tmp_path):
    with pytest.raises(ValueError, match='only by compact'):
        review_book(build_book(['— Olá.']), None, Cache(tmp_path), protocol='lightweight', source_subjects=True)
