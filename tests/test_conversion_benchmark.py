from pathlib import Path
import runpy


def test_sample_selection_covers_voices_lengths_and_respects_conversion_mode():
    select = runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "benchmark_conversion.py"))["select_samples"]
    turns = [{"id": f"{name}-{length}", "speaker": name, "start": 0, "end": length, "eligible": True}
             for name in ("Iara", "Nilo", "Preservado") for length in (3, 12, 30)]
    selected = select({"files": [{"input": "chapter.mp3", "dialogues": turns}]},
                      {"Iara": {"mode": "convert"}, "Nilo": {"mode": "convert"},
                       "Preservado": {"mode": "original"}}, 4)
    assert [turn["id"] for _, turn in selected] == ["Iara-3", "Nilo-3", "Iara-30", "Nilo-30"]
    assert len(turns) == 9
