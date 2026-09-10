import copy

import pytest

from audiobook_voice_enhancer.attribution_contracts import CONTRACTS, configure
from audiobook_voice_enhancer.book_speakers import build_book, review_book
from audiobook_voice_enhancer.cache import Cache, FrozenCache, ReplayMiss
from audiobook_voice_enhancer.compact_speakers import SCHEMA, SYSTEM
from audiobook_voice_enhancer.llm import LLMProvider


class Provider(LLMProvider):
    model = 'contract-fixture'

    def __init__(self, edit=None):
        self.calls = []
        self.edit = edit

    def infer(self, payload):
        self.calls.append(copy.deepcopy(payload))
        assert payload.get('task') != 'repair_unresolved_continuation'
        iara = next(e['id'] for e in payload['entities'] if e['name'] == 'Iara')
        wants_kind = 'kind' in self.response_schema['properties']['assignments']['items']['properties']
        rows = [{'id': t['id'], 'speaker': iara, 'confidence': .97,
                 **({'kind': 'speech'} if wants_kind else {})} for t in payload['turns']]
        if self.edit:
            self.edit(rows)
        return {'entities': [], 'assignments': rows}


@pytest.mark.parametrize('contract', CONTRACTS)
def test_contract_changes_only_its_declared_request_components(contract):
    payload = {'entities': [{'id': 'E0'}], 'turns': [{'id': 'T0'}]}
    original = copy.deepcopy(payload)
    schema_before = copy.deepcopy(SCHEMA)
    provider = Provider()
    configure(provider, payload, {'T0': {'kind': 'speech'}}, contract, SYSTEM, SCHEMA)
    assert SCHEMA == schema_before
    if contract != 'speaker-only':
        assert payload == original
    if contract in {'baseline', 'catalog-schema'}:
        assert provider.system_prompt == SYSTEM
    if contract in {'baseline', 'catalog-prompt'}:
        assert provider.response_schema == SCHEMA
    if contract == 'catalog-schema':
        assert provider.response_schema != SCHEMA
    if contract == 'catalog-prompt':
        assert provider.system_prompt != SYSTEM
    if contract == 'speaker-only':
        assert 'kind' not in provider.response_schema['properties']['assignments']['items']['properties']
        assert payload['turns'][0]['input_kind'] == 'speech'


def test_speaker_only_accepts_identity_without_reclassifying_or_mutating_raw_answer(tmp_path):
    model = build_book(['— Olá — disse Iara.', '— Vou voltar.'])
    source = copy.deepcopy(model)
    provider = Provider()
    result = review_book(model, provider, Cache(tmp_path), protocol='hybrid',
                         attribution_contract='speaker-only', turn_consistency=False)
    assert model == source
    assert result['turns'][0]['status'] == 'explicit'
    turn = result['turns'][1]
    assert turn['status'] == 'contextual'
    assert turn['kind'] == turn['input_kind'] == 'speech'
    assert 'kind' not in turn['raw_decisions'][0]
    assert turn['classification_source'] == 'upstream_inventory'
    assert result['review']['total_llm_calls'] == 1


@pytest.mark.parametrize('input_kind', ['unknown', 'thought', 'citation'])
def test_speaker_only_cannot_voice_non_speech_even_in_repairable_window(tmp_path, input_kind):
    model = build_book(['— Olá — disse Iara.', '— Sim — disse Nilo.', '— Trecho em avaliação.'])
    model['turns'][2]['kind'] = input_kind
    provider = Provider()
    result = review_book(model, provider, Cache(tmp_path), protocol='hybrid', max_turns=2,
                         attribution_contract='speaker-only')
    assert result['turns'][2]['speaker_entity_id'] is None
    assert result['turns'][2]['kind'] == input_kind
    assert len(provider.calls) == 2
    assert result['review']['hybrid_router']['repair_calls'] == 0


@pytest.mark.parametrize('edit', [
    lambda rows: rows[1].update(kind='unknown'),  # Old responses must not be reinterpreted.
    lambda rows: rows[1].update(confidence=True),
    lambda rows: rows[1].update(confidence=float('nan')),
    lambda rows: rows[1].update(confidence=1.5),
    lambda rows: rows[1].update(speaker='N999'),
    lambda rows: rows.append(dict(rows[1])),
    lambda rows: rows[1].pop('speaker'),
])
def test_speaker_only_rejects_malformed_or_unbound_identity(tmp_path, edit):
    result = review_book(build_book(['— Olá — disse Iara.', '— Vou voltar.']),
                         Provider(edit), Cache(tmp_path), protocol='hybrid',
                         attribution_contract='speaker-only')
    assert result['turns'][1]['speaker_entity_id'] is None
    assert result['review']['structural_rejections'] == 1


@pytest.mark.parametrize('edit', [lambda rows: rows[1].update(speaker=None),
                                 lambda rows: rows[1].update(confidence=.3)])
def test_speaker_only_abstains_without_invalidating_speech(tmp_path, edit):
    result = review_book(build_book(['— Olá — disse Iara.', '— Vou voltar.']),
                         Provider(edit), Cache(tmp_path), protocol='hybrid',
                         attribution_contract='speaker-only')
    assert result['turns'][1]['speaker_entity_id'] is None
    assert result['turns'][1]['kind'] == 'speech'
    assert result['review']['structural_rejections'] == 0


def test_ablations_have_separate_cache_keys_and_replay_exactly(tmp_path):
    cache = Cache(tmp_path / 'cache')
    model = build_book(['— Olá — disse Iara.', '— Vou voltar.'])
    for contract in CONTRACTS:
        provider = Provider()
        review_book(model, provider, cache, protocol='hybrid', attribution_contract=contract)
        assert len(provider.calls) == 1
    assert cache.hits == 0
    assert cache.misses == 4
    for contract in CONTRACTS:
        provider = Provider()
        review_book(model, provider, Cache(tmp_path / 'replay'), protocol='hybrid',
                    attribution_contract=contract, base_cache=FrozenCache(cache.root))
        assert provider.calls == []


def test_old_cache_cannot_be_used_as_speaker_only(tmp_path):
    cache = Cache(tmp_path / 'cache')
    model = build_book(['— Olá — disse Iara.'])
    review_book(model, Provider(), cache, protocol='hybrid')
    with pytest.raises(ReplayMiss):
        review_book(model, Provider(), Cache(tmp_path / 'new'), protocol='hybrid',
                    attribution_contract='speaker-only', base_cache=FrozenCache(cache.root))


@pytest.mark.parametrize('protocol,contract', [('compact','speaker-only'),
                                             ('hybrid-catalog','catalog-schema'),
                                             ('hybrid','unrecognized')])
def test_incompatible_experiments_fail_before_inference(tmp_path, protocol, contract):
    provider = Provider()
    with pytest.raises(ValueError):
        review_book(build_book(['— Olá — disse Iara.']), provider, Cache(tmp_path),
                    protocol=protocol, attribution_contract=contract)
    assert not provider.calls


def test_benchmark_cli_rejects_incompatible_contract_before_reserving_output(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / 'never_created'
    args = [sys.executable, str(root / 'scripts/benchmark_book_speakers.py')]
    for key in ('book', 'transcription', 'alignment', 'gold'):
        args += ['--' + key, 'unused']
    args += ['--config', str(root / 'config/config.yaml'), '--output', str(output),
             '--protocol', 'compact', '--attribution-contract', 'speaker-only']
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode == 2
    assert 'require protocol hybrid' in result.stderr
    assert not output.exists()
