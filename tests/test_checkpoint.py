import json
from types import SimpleNamespace

from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.pipeline import Pipeline


def test_checkpoint_round_trip_for_analysis(tmp_path):
    path = tmp_path / "checkpoints" / "run.json"
    path.parent.mkdir()
    Pipeline._save_checkpoint(path, 2, 42, [{"input": "one.mp3"}, {"input": "two.mp3"}])
    loaded = Pipeline._load_checkpoint(path, "analyze", False)
    assert loaded["next_index"] == 2
    assert loaded["book_cursor"] == 42


def test_process_checkpoint_requires_generated_outputs(tmp_path):
    path = tmp_path / "run.json"
    path.write_text(json.dumps({"next_index": 1, "book_cursor": 0,
                                "results": [{"input": "one.mp3", "output": str(tmp_path / "missing.mp3")}]}), encoding="utf-8")
    assert Pipeline._load_checkpoint(path, "process", False) == {}


def test_pipeline_reuses_completed_chapter_checkpoint(monkeypatch, tmp_path):
    files = [tmp_path / "one.mp3", tmp_path / "two.mp3"]
    for path in files:
        path.write_bytes(path.name.encode())

    def instance():
        pipeline = Pipeline.__new__(Pipeline)
        pipeline.root = tmp_path
        pipeline.config = {"speaker_confidence_threshold": .85, "transcription": {}, "device": "cpu"}
        pipeline.characters = {"__narrator__": {"mode": "original"}}
        pipeline.characters_path = tmp_path / "characters.json"
        pipeline.characters_path.write_text('{"__narrator__":{"mode":"original"}}', encoding="utf-8")
        pipeline.cache = Cache(tmp_path / "cache")
        pipeline.voice_fingerprints = {}
        pipeline.output = tmp_path / "output"
        pipeline.hardware = {}
        pipeline.converter = SimpleNamespace(name="fake")
        return pipeline

    monkeypatch.setattr("audiobook_voice_enhancer.pipeline.discover_audio", lambda source, include: files)
    first = instance()
    calls = []

    def fake_one(path, **kwargs):
        calls.append(path.name)
        return {"input": str(path), "duration": 10, "final_duration": 10, "segments_analyzed": 0,
                "dialogues": [], "errors": [], "warnings": [], "_book_cursor": kwargs["book_cursor"]}

    monkeypatch.setattr(first, "_one", fake_one)
    first.run(tmp_path, command="process", language="pt", book_text=None, dry_run=True)
    assert calls == ["one.mp3", "two.mp3"]

    resumed = instance()
    monkeypatch.setattr(resumed, "_one", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should resume")))
    report = resumed.run(tmp_path, command="process", language="pt", book_text=None, dry_run=True)
    assert len(report["files"]) == 2
