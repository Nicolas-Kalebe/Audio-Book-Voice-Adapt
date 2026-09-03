from audiobook_voice_enhancer.reporting import summarize


def test_dry_run_has_conversion_plan():
    files = [{"duration": 10, "segments_analyzed": 2, "dialogues": [
        {"speaker": "Vesemir", "eligible": True, "action": "would_convert", "start": 1, "end": 3,
         "character_mode": "convert", "character_configured": True},
        {"speaker": "Geralt", "eligible": False, "action": "skipped", "start": 4, "end": 6,
         "character_mode": "original", "character_configured": True, "skip_reason": "character mode is original"}],
        "errors": [], "warnings": []}]
    report = summarize(files, {}, {"hits": 0, "misses": 0}, 1, "fw", "seedvc")
    assert report["characters_planned_for_conversion"] == {"Vesemir": 1}
    assert report["characters_intentionally_preserved"]["Geralt"] == 1
