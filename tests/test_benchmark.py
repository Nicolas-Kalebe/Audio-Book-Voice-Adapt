from audiobook_voice_enhancer.benchmark import evaluate, load_gold


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
