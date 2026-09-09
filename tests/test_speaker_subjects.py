import copy

import pytest

from audiobook_voice_enhancer.book_speakers import build_book, review_book
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.compact_speakers import MEMORY_SUFFIX, SCHEMA, SYSTEM
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


def test_same_description_in_one_scene_is_one_person():
    """A mesma descricao repetida na cena e a mesma pessoa; outra descricao nao.

    Sem isso, o mesmo figurante recebe uma identidade por mencao e o audiobook
    lhe da uma voz diferente a cada fala.
    """
    model = build_book(['— Abra — disse um guarda alto.', '— Feche — disse um guarda gordo.', '— Venha — disse um guarda alto.'])
    seed_subjects(model)
    first, other, last = (t['source_subjects'][0]['entity_id'] for t in model['turns'])
    assert first == last
    assert other != first
    assert all(t['speaker_entity_id'] is None for t in model['turns'])


def test_mention_scope_restores_one_identity_per_occurrence():
    """O comportamento antigo continua a uma linha de configuracao de distancia."""
    model = build_book(['— Abra — disse um guarda alto.', '— Venha — disse um guarda alto.'],
                       anonymous_scope='mention')
    seed_subjects(model)
    first, last = (t['source_subjects'][0]['entity_id'] for t in model['turns'])
    assert first != last


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


def test_plain_compact_now_anchors_the_name_behind_a_title(tmp_path):
    """"disse a capitã Luma" ancora sozinho, sem a opcao source_subjects.

    Era esta descoberta que justificava o `source_subjects`, e ele a pagava caro:
    oferecia tambem as descricoes sem nome como candidatos, e o modelo passou a
    tratar cada uma como pessoa nova. A ancora resolve a metade que funciona —
    cargo entre o artigo e o nome — sem a metade que fragmentava identidades.

    O turno nao carrega `source_subject` e o protocolo segue sendo o compacto:
    prompt e schema intactos, uma chamada por janela.
    """
    model = build_book(['— Abra — disse a capitã Luma.'])
    seen = {}

    class Provider(LLMProvider):
        model = 'plain-control-fixture'

        def infer(self, payload):
            assert self.system_prompt == SYSTEM + MEMORY_SUFFIX and self.response_schema == SCHEMA
            assert 'source_subject' not in payload['turns'][0]
            seen['entities'] = payload['entities']
            return {'entities': [], 'assignments': []}

    result = review_book(model, Provider(), Cache(tmp_path), protocol='compact')
    assert result['review']['errors'] == []
    assert [e['name'] for e in seen['entities']] == ['Luma']
    assert result['turns'][0]['status'] == 'explicit'
    assert model['entities'][result['turns'][0]['speaker_entity_id']]['name'] == 'Luma'


def test_reference_option_cannot_silently_run_with_another_protocol(tmp_path):
    with pytest.raises(ValueError, match='only by compact'):
        review_book(build_book(['— Olá.']), None, Cache(tmp_path), protocol='lightweight', source_subjects=True)
