from audiobook_voice_enhancer.cache import Cache


def test_cache_reuses_value(tmp_path):
    cache = Cache(tmp_path)
    calls = []
    first = cache.json("alignment", "key", lambda: calls.append(1) or {"ok": True})
    second = cache.json("alignment", "key", lambda: calls.append(2) or {"ok": False})
    assert first == second == {"ok": True}
    assert calls == [1]
    assert (cache.misses, cache.hits) == (1, 1)

