from audiobook_voice_enhancer.benchmark import evaluate, load_gold, render_markdown


def test_part01_gold_is_complete_and_has_no_duplicate_ids():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    gold = load_gold(root / "benchmarks" / "part01_gold.yaml")
    dialogues = []
    for speaker, ids in gold["spoken_by"].items():
        dialogues.extend({"id": str(item_id), "speaker": speaker,
                          "book_paragraph_id": int(str(item_id).split("-", 1)[0])} for item_id in ids)
    for label, detail in gold["ambiguous_spoken"].items():
        dialogues.extend({"id": str(item_id), "speaker": label,
                          "book_paragraph_id": int(str(item_id).split("-", 1)[0])}
                         for item_id in detail["ids"])
    for ids in gold["non_spoken"].values():
        dialogues.extend({"id": str(item_id), "speaker": None,
                          "book_paragraph_id": int(str(item_id).split("-", 1)[0])} for item_id in ids)
    result = evaluate(gold, {"files": [{"dialogues": dialogues}]})
    assert result["candidates_in_report"] == 267
    assert result["gold_source_turns"] == 255
    assert result["missing_source_turns"] == 5
    assert result["incomplete_detected_turns"] == 145
    assert result["complete_detected_turns"] == 105
    assert result["evaluation_protocol"]["independent_holdout"] is False
    assert result["evaluation_protocol"]["status"] == "development_regression"
    assert "development_regression" in render_markdown(result)


def test_benchmark_counts_abstention_as_end_to_end_error():
    gold = {
        "version": 1,
        "name": "mini",
        "spoken_by": {"Ana": ["1-0"], "Bia": ["2-0"]},
        "non_spoken": {},
        "missing_spoken": [{"id": "source-3-0", "book_paragraph_id": 3, "speaker": "Ana", "text": "Oi"}],
    }
    analysis = {"files": [{"dialogues": [
        {"id": "1-0", "speaker": "Ana", "book_paragraph_id": 1, "text": "Oi"},
        {"id": "2-0", "speaker": None, "book_paragraph_id": 2, "text": "Ola"},
    ]}]}
    result = evaluate(gold, analysis)
    assert result["speaker_accuracy_when_assigned"] == 1.0
    assert result["speaker_accuracy_all_detected"] == 0.5
    assert result["end_to_end_accuracy"] == 1 / 3
    assert sum(scene["correct"] for scene in result["per_scene"]) == 1
    assert sum(scene["total"] for scene in result["per_scene"]) == 3
    assert sum(scene["missing"] for scene in result["per_scene"]) == 1


def test_benchmark_reports_train_development_and_locked_test_separately():
    gold = {
        "version": 1, "name": "mini",
        "split": {"train": {"scenes": [1]}, "test_locked": {"scenes": [2]}},
        "spoken_by": {"Ana": ["1-0", "2-0"]}, "non_spoken": {}, "missing_spoken": [],
    }
    analysis = {"files": [{"dialogues": [
        {"id": "1-0", "speaker": "Ana", "book_paragraph_id": 1, "scene_id": 1},
        {"id": "2-0", "speaker": None, "book_paragraph_id": 2, "scene_id": 2},
    ]}]}
    result = evaluate(gold, analysis)
    metrics = {item["split"]: item for item in result["split_metrics"]}
    assert metrics["train"]["end_to_end_accuracy"] == 1.0
    assert metrics["test_locked"]["end_to_end_accuracy"] == 0.0
