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


def analysis_com_regras(speakers, regras):
    """Analise com a camada textual, que e onde `turn_consistency` deixa o carimbo."""
    base = analysis(speakers)
    base["files"][0]["book_speaker_analysis"] = {"turns": [
        {"id": f"book-{paragraph}", "fragments": [{"paragraph": paragraph}],
         "consistency_rule": regra}
        for paragraph, regra in enumerate(regras, 1)
    ]}
    return base


def test_diferencial_separa_erro_de_regra_de_erro_da_primeira_leitura():
    """Sem esta separacao, "faltou regra" e "regra existente errou" ficam no mesmo
    balde — e as duas conclusoes levam a trabalhos opostos."""
    gold = {"version": 1, "name": "fixture", "spoken_by": {
        "Ana": ["1-0", "2-0", "3-0", "4-0"]},
        "ambiguous_spoken": {}, "non_spoken": {}, "anonymous_role_labels": []}
    report = compare_runs(
        gold,
        analysis(["Ana", "Ana", "Ana", "Ana"]),
        {"candidate": analysis_com_regras(
            # dois erros: um escrito por uma regra de consistencia, outro nao.
            ["Ana", "Bia", "Bia", "Ana"],
            [None, "sanduiche_de_tres_turnos", None, None],
        )},
    )
    summary = report["candidates"]["candidate"]
    assert summary["wrong_by_consistency_rule"] == {
        "sanduiche_de_tres_turnos": 1, "sem_regra": 1,
    }
    # O carimbo tambem viaja por turno, para o CSV permitir o filtro manual.
    por_id = {row["id"]: row["candidate_consistency_rule"] for row in report["rows"]}
    assert por_id["2-0"] == "sanduiche_de_tres_turnos"
    assert por_id["3-0"] is None


def test_turno_certo_nao_entra_na_conta_de_erro_por_regra():
    gold = {"version": 1, "name": "fixture", "spoken_by": {"Ana": ["1-0", "2-0"]},
            "ambiguous_spoken": {}, "non_spoken": {}, "anonymous_role_labels": []}
    report = compare_runs(
        gold,
        analysis(["Ana", None]),
        {"candidate": analysis_com_regras(["Ana", "Ana"], [None, "sanduiche_de_tres_turnos"])},
    )
    # A regra acertou; nao pode aparecer como causadora de dano.
    assert report["candidates"]["candidate"]["wrong_by_consistency_rule"] == {}
