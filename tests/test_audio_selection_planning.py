import pytest

from audiobook_voice_enhancer.audio import AudioToolError, discover_audio
from audiobook_voice_enhancer.planning import analysis_for_selection, clock, estimate_job


def test_discover_audio_filters_included_chapters(tmp_path):
    (tmp_path / "Parte 01.mp3").write_bytes(b"one")
    (tmp_path / "Parte 02.mp3").write_bytes(b"two")
    (tmp_path / "smoke.wav").write_bytes(b"test")
    found = discover_audio(tmp_path, ["Parte 02.mp3"])
    assert [path.name for path in found] == ["Parte 02.mp3"]
    with pytest.raises(AudioToolError):
        discover_audio(tmp_path, ["missing.mp3"])


def test_job_estimate_reports_space_and_time_range():
    estimate = estimate_job(3600, "320k", {"original_duration": 3600, "elapsed_seconds": 600,
                                            "estimated_conversion_seconds": 120})
    assert 130 < estimate["output_mb"] < 150
    assert estimate["minimum_seconds"] == 60
    assert estimate["maximum_seconds"] == 240
    assert clock(3661) == "01:01:01"


def test_analysis_estimate_uses_only_selected_convertible_dialogues():
    report = {"original_duration": 200, "elapsed_seconds": 20, "files": [
        {"input": "Parte 01.mp3", "duration": 100, "dialogues": [
            {"speaker": "Geralt", "speaker_confidence": .98, "alignment_confidence": .95, "start": 1, "end": 11},
            {"speaker": "Ciri", "speaker_confidence": .98, "alignment_confidence": .95, "start": 20, "end": 30},
        ]},
        {"input": "Parte 02.mp3", "duration": 100, "dialogues": []},
    ]}
    selected = analysis_for_selection(report, {"Parte 01.mp3"}, {"Geralt"}, .85, .8)
    assert selected["original_duration"] == 100
    assert selected["elapsed_seconds"] == 10
    assert selected["estimated_conversion_seconds"] == 10
