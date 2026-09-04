from __future__ import annotations

import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml


def _fold(value: str | None) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in value if not unicodedata.combining(char)).casefold().strip()


def load_gold(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Gabarito ausente ou com versao nao suportada")
    return data


def _flatten_gold(gold: dict[str, Any]) -> tuple[dict[str, str], dict[str, str], dict[str, set[str]]]:
    spoken: dict[str, str] = {}
    non_spoken: dict[str, str] = {}
    acceptable: dict[str, set[str]] = {}

    def add(target: dict[str, str], item_id: str, label: str) -> None:
        if item_id in spoken or item_id in non_spoken:
            raise ValueError(f"ID duplicado no gabarito: {item_id}")
        target[item_id] = label

    for speaker, ids in gold.get("spoken_by", {}).items():
        for item_id in ids:
            add(spoken, str(item_id), speaker)
    for label, detail in gold.get("ambiguous_spoken", {}).items():
        for item_id in detail.get("ids", []):
            item_id = str(item_id)
            add(spoken, item_id, label)
            acceptable[item_id] = {_fold(value) for value in detail.get("acceptable_named_speakers", [])}
    for category, ids in gold.get("non_spoken", {}).items():
        for item_id in ids:
            add(non_spoken, str(item_id), category)
    return spoken, non_spoken, acceptable


def evaluate(gold: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    spoken, non_spoken, acceptable = _flatten_gold(gold)
    files = analysis.get("files", [])
    candidates = [item for file_result in files for item in file_result.get("dialogues", [])]
    by_id = {str(item["id"]): item for item in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("O relatorio contem IDs duplicados")

    expected_candidate_ids = set(spoken) | set(non_spoken)
    missing_annotations = sorted(set(by_id) - expected_candidate_ids)
    stale_annotations = sorted(expected_candidate_ids - set(by_id))
    if missing_annotations or stale_annotations:
        raise ValueError(
            f"Gabarito nao corresponde ao relatorio: sem rotulo={missing_annotations}, "
            f"IDs inexistentes={stale_annotations}"
        )

    fragments = {str(value) for value in gold.get("continuation_fragments", [])}
    turn_ids = set(spoken) - fragments
    incomplete = {str(value) for value in gold.get("incomplete_turn_ids", [])}
    if not incomplete <= turn_ids:
        raise ValueError(f"Limites incompletos apontam para IDs invalidos: {sorted(incomplete - turn_ids)}")
    missing_source = list(gold.get("missing_spoken", []))
    total_source_turns = len(turn_ids) + len(missing_source)
    assigned = 0
    correct = 0
    correct_and_complete = 0
    wrong: list[dict[str, Any]] = []
    confusion: Counter[tuple[str, str]] = Counter()
    per_speaker_total = Counter(spoken[item_id] for item_id in turn_ids)
    per_speaker_correct: Counter[str] = Counter()
    per_speaker_missing = Counter(item["speaker"] for item in missing_source)
    per_speaker_total.update(per_speaker_missing)

    for item_id in sorted(turn_ids, key=lambda value: tuple(int(part) for part in value.split("-"))):
        item = by_id[item_id]
        expected = spoken[item_id]
        predicted = item.get("speaker")
        if predicted:
            assigned += 1
        is_correct = _fold(predicted) == _fold(expected)
        if item_id in acceptable and _fold(predicted) in acceptable[item_id]:
            is_correct = True
        if is_correct:
            correct += 1
            per_speaker_correct[expected] += 1
            if item_id not in incomplete:
                correct_and_complete += 1
        else:
            actual_label = predicted or "SEM ATRIBUICAO"
            confusion[(expected, actual_label)] += 1
            wrong.append({
                "id": item_id,
                "paragraph": item.get("book_paragraph_id"),
                "expected": expected,
                "predicted": predicted,
                "suggestion": item.get("llm_suggestion"),
                "text": item.get("text", ""),
            })

    detected_turns = len(turn_ids)
    complete_detected_turns = detected_turns - len(incomplete)
    false_turn_candidates = len(non_spoken)
    detection_precision = detected_turns / (detected_turns + false_turn_candidates)
    detection_recall = detected_turns / total_source_turns
    per_character = []
    for speaker, total in per_speaker_total.most_common():
        hit = per_speaker_correct[speaker]
        per_character.append({"speaker": speaker, "correct": hit, "total": total, "recall": hit / total})

    return {
        "gold": gold["name"],
        "candidates_in_report": len(candidates),
        "spoken_candidate_regions": len(spoken),
        "non_spoken_candidates": len(non_spoken),
        "continuation_fragments": len(fragments),
        "gold_source_turns": total_source_turns,
        "detected_source_turns": detected_turns,
        "incomplete_detected_turns": len(incomplete),
        "complete_detected_turns": complete_detected_turns,
        "missing_source_turns": len(missing_source),
        "detection_precision": detection_precision,
        "detection_recall": detection_recall,
        "complete_turn_recall": complete_detected_turns / total_source_turns,
        "speaker_assigned_turns": assigned,
        "speaker_correct_turns": correct,
        "speaker_accuracy_all_detected": correct / detected_turns,
        "speaker_accuracy_when_assigned": correct / assigned if assigned else 0.0,
        "automatic_attribution_coverage": assigned / detected_turns,
        "end_to_end_accuracy": correct / total_source_turns,
        "speaker_and_boundary_end_to_end_accuracy": correct_and_complete / total_source_turns,
        "speaker_correct_and_complete_turns": correct_and_complete,
        "per_character": per_character,
        "wrong_or_unassigned": wrong,
        "confusion": [
            {"expected": expected, "predicted": predicted, "count": count}
            for (expected, predicted), count in confusion.most_common()
        ],
        "missing_spoken": missing_source,
        "known_boundary_issues": gold.get("known_boundary_issues", []),
    }


def render_markdown(result: dict[str, Any]) -> str:
    pct = lambda value: f"{value * 100:.2f}%"
    lines = [
        "# Baseline auditavel - Parte 01",
        "",
        "## Resultado executivo",
        "",
        f"- Turnos falados no gabarito: **{result['gold_source_turns']}**.",
        f"- Turnos encontrados: **{result['detected_source_turns']}**; perdidos: **{result['missing_source_turns']}**.",
        f"- Recall de deteccao: **{pct(result['detection_recall'])}**.",
        f"- Turnos encontrados por inteiro: **{result['complete_detected_turns']}/{result['gold_source_turns']}** "
        f"({pct(result['complete_turn_recall'])}); **{result['incomplete_detected_turns']}** param no meio da fala.",
        f"- Candidatos que eram pensamento ou texto escrito: **{result['non_spoken_candidates']}**.",
        f"- Precisao da deteccao por turno: **{pct(result['detection_precision'])}**.",
        f"- Turnos com personagem atribuido: **{result['speaker_assigned_turns']}/{result['detected_source_turns']}** "
        f"({pct(result['automatic_attribution_coverage'])}).",
        f"- Atribuicoes corretas: **{result['speaker_correct_turns']}/{result['detected_source_turns']}** "
        f"({pct(result['speaker_accuracy_all_detected'])}).",
        f"- Acuracia apenas entre respostas emitidas: **{pct(result['speaker_accuracy_when_assigned'])}**.",
        f"- Acuracia ponta a ponta: **{result['speaker_correct_turns']}/{result['gold_source_turns']}** "
        f"({pct(result['end_to_end_accuracy'])}).",
        f"- Personagem e limite ambos corretos: **{result['speaker_correct_and_complete_turns']}/"
        f"{result['gold_source_turns']}** ({pct(result['speaker_and_boundary_end_to_end_accuracy'])}).",
        "",
        "A metrica principal e a acuracia ponta a ponta: omissoes e recusas contam como erro. "
        "Acuracia apenas entre respostas emitidas pode parecer boa mesmo com baixa cobertura.",
        "",
        "## Por personagem ou papel",
        "",
        "| Personagem/papel | Corretas | Total | Recall |",
        "|---|---:|---:|---:|",
    ]
    for item in result["per_character"]:
        lines.append(f"| {item['speaker']} | {item['correct']} | {item['total']} | {pct(item['recall'])} |")
    lines.extend(["", "## Principais confusoes", "", "| Esperado | Motor atual | Quantidade |", "|---|---|---:|"])
    for item in result["confusion"]:
        lines.append(f"| {item['expected']} | {item['predicted']} | {item['count']} |")
    lines.extend(["", "## Falas inteiras perdidas", ""])
    for item in result["missing_spoken"]:
        lines.append(f"- P{item['book_paragraph_id']} - {item['speaker']}: `{item['text']}`")
    lines.extend([
        "",
        "## Observacoes de qualidade",
        "",
        f"- O relatorio possui {result['continuation_fragments']} fragmentos audiveis que pertencem a turnos ja contados; "
        "eles recebem a voz do falante, mas nao inflam a quantidade de turnos.",
    ])
    for issue in result["known_boundary_issues"]:
        lines.append(f"- `{issue['id']}`: {issue['issue']}")
    lines.append("")
    return "\n".join(lines)


def evaluate_files(gold_path: Path, analysis_path: Path) -> tuple[dict[str, Any], str]:
    gold = load_gold(gold_path)
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    result = evaluate(gold, analysis)
    return result, render_markdown(result)
