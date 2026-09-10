from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.cache import FrozenCache, ReplayMiss
import pytest


def test_cache_reuses_value(tmp_path):
    cache = Cache(tmp_path)
    calls = []
    first = cache.json("alignment", "key", lambda: calls.append(1) or {"ok": True})
    second = cache.json("alignment", "key", lambda: calls.append(2) or {"ok": False})
    assert first == second == {"ok": True}
    assert calls == [1]
    assert (cache.misses, cache.hits) == (1, 1)


def test_frozen_cache_never_infers_or_writes(tmp_path):
    original = Cache(tmp_path)
    original.json("llm", "known", lambda: {"assignments": []})
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    frozen = FrozenCache(tmp_path)
    def forbidden():
        pytest.fail("Replay must never run inference")
    assert frozen.json("llm", "known", forbidden) == {"assignments": []}
    with pytest.raises(ReplayMiss):
        frozen.json("llm", "unknown", forbidden)
    assert frozen.hits == frozen.misses == 1
    assert len(frozen.used["llm/known"]) == 64
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

