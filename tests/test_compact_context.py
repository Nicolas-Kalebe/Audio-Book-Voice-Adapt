from audiobook_voice_enhancer.book_speakers import build_book, windows, review_book
from audiobook_voice_enhancer.compact_context import CompactContext, bounded_schema
from audiobook_voice_enhancer.compact_speakers import SCHEMA
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.llm import LLMProvider


def test_split_scene_retains_introduction_and_unique_target_ownership(tmp_path):
    blocks = ['— Venha — disse Iara.', '— Sim — disse Bento.'] + ['— Continue.'] * 9
    model = build_book(blocks)
    seen = []

    class Provider(LLMProvider):
        model = 'fixture'

        def infer(self, payload):
            seen.append(payload)
            assert payload['scene_text'][0]['text'] == blocks[0]
            assert {e['name'] for e in payload['entities']} == {'Iara', 'Bento'}
            props = self.response_schema['properties']['assignments']['items']['properties']
            assert props['id']['enum'] == [t['id'] for t in payload['turns']]
            assert 'N' not in props['speaker']['enum']
            return {'entities': [], 'assignments': [
                {'id': t['id'], 'speaker': None, 'kind': 'unknown', 'confidence': 0}
                for t in payload['turns']]}

    review_book(model, Provider(), Cache(tmp_path), protocol='compact', max_turns=3)
    assert len(seen) > 1
    ids = [t['id'] for payload in seen for t in payload['turns']]
    assert len(ids) == len(set(ids)) == len(model['turns'])
    assert all(payload['entities'] == seen[0]['entities'] for payload in seen)


def test_context_stays_inside_scene_and_character_budget():
    model = build_book(['— Oi — disse Iara.'] + ['— Continue.'] * 30)
    context = CompactContext(model, 90)
    for batch in windows(model, None, max_turns=2, max_chars=90):
        expanded = context.expand(batch)
        assert sum(map(len, model['blocks'][expanded['first']:expanded['last'] + 1])) <= 90
        assert expanded['turns'] == batch['turns']
        assert expanded['first'] <= batch['first'] <= batch['last'] <= expanded['last']


def test_schema_does_not_mutate_shared_template():
    schema = bounded_schema(SCHEMA, {'E9': 'iara'}, {'T42': {}})
    props = schema['properties']['assignments']['items']['properties']
    assert props['speaker']['enum'] == [None, 'E9', 'N0']
    assert 'enum' not in SCHEMA['properties']['assignments']['items']['properties']['speaker']
