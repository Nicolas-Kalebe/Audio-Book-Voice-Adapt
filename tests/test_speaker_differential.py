from audiobook_voice_enhancer.speaker_differential import compare_runs


def analysis(speakers):
    return {"files": [{"dialogues": [
        {"id": f"{paragraph}-0", "turn_id": f"book-{paragraph}",
         "fragment_index": 0, "book_paragraph_id": paragraph, "scene_id": 7,
         "speaker": speaker}
        for paragraph, speaker in enumerate(speakers, 1)
    ]}]}


def test_differential_records_saves_harms_and_safe_abstention():
    gold = {"version": 1, "name": "fixture", "spoken_by": {
        "Ana": ["1-0", "2-0", "3-0"], "Bia": ["4-0"]},
        "ambiguous_spoken": {}, "non_spoken": {}, "anonymous_role_labels": []}
    report = compare_runs(
        gold,
        analysis(["Ana", "Ana", None, "Ana"]),
        {"candidate": analysis(["Ana", "Bia", "Ana", None])},
    )
    summary = report["candidates"]["candidate"]
    assert summary["categories"] == {
        "both_correct": 1, "candidate_harms": 1, "candidate_saves": 1,
        "candidate_abstains_on_error": 1,
    }
    assert summary["net_correct"] == 0
    assert len(report["rows"]) == 4
