"""Turn-level comparison of speaker-attribution runs against a frozen gold set."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .benchmark import _fold, _flatten_gold, _role_aliases, _role_key, evaluate


def _correct(predicted: str | None, expected: str, accepted: set[str], aliases) -> bool:
    if not predicted:
        return False
    if _fold(predicted) == _fold(expected) or _fold(predicted) in accepted:
        return True
    key = _role_key(predicted)
    return bool(key) and (key == _role_key(expected) or key in aliases.get(_fold(expected), set()))


def turn_outcomes(gold: dict[str, Any], analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Expose the benchmark decision for every gold turn, including successes."""
    spoken, _, acceptable = _flatten_gold(gold)
    aliases = _role_aliases(gold)
    source_paragraphs = {}
    for missing in gold.get("missing_spoken", []):
        missing_id = str(missing["id"])
        spoken[missing_id] = str(missing["speaker"])
        source_paragraphs[missing_id] = int(missing["book_paragraph_id"])
    standalone = {str(value) for value in gold.get("standalone_quote_turn_ids", [])}
    continuations = {str(value) for value in gold.get("continuation_fragments", [])}
    anonymous = {_fold(value) for value in gold.get("anonymous_role_labels", [])}

    dialogue_by_key = defaultdict(list)
    scene_by_paragraph = {}
    analysis_turn_by_paragraph = {}
    for chapter in analysis.get("files", []):
        textual = chapter.get("book_speaker_analysis") or {}
        for turn in textual.get("turns", []):
            paragraphs = [int(fragment["paragraph"]) for fragment in turn.get("fragments", [])]
            for paragraph in paragraphs:
                analysis_turn_by_paragraph[paragraph] = turn
        for item in chapter.get("dialogues", []):
            item_id = str(item.get("id", ""))
            paragraph = item.get("book_paragraph_id")
            if paragraph is not None:
                paragraph = int(paragraph)
                scene_by_paragraph[paragraph] = item.get("scene_id")
            if item_id in standalone:
                key = f"id:{item_id}"
            else:
                turn_id = str(item.get("turn_id", ""))
                if turn_id.startswith("book-") and turn_id[5:].isdigit():
                    paragraph = int(turn_id[5:])
                key = f"p:{paragraph}"
            dialogue_by_key[key].append(item)

    outcomes = {}
    for item_id, expected in spoken.items():
        if item_id in continuations:
            continue
        paragraph = source_paragraphs.get(item_id)
        if paragraph is None:
            paragraph = int(item_id.split("-", 1)[0])
        key = f"id:{item_id}" if item_id in standalone else f"p:{paragraph}"
        items = sorted(dialogue_by_key.get(key, []),
                       key=lambda item: (int(item.get("fragment_index", 0)),
                                         float(item.get("start", 0))))
        primary = next((item for item in items if int(item.get("fragment_index", 0)) == 0),
                       items[0] if items else None)
        predicted = primary.get("speaker") if primary else None
        turn = analysis_turn_by_paragraph.get(paragraph, {})
        outcomes[item_id] = {
            "id": item_id,
            "paragraph": paragraph,
            "scene": (primary or {}).get("scene_id", scene_by_paragraph.get(paragraph)),
            "class": "figurante" if _fold(expected) in anonymous else "dublavel",
            "expected": expected,
            "predicted": predicted,
            "detected": bool(items),
            "assigned": bool(predicted),
            "correct": _correct(predicted, expected, acceptable.get(item_id, set()), aliases),
            "confidence": (primary or {}).get("speaker_confidence"),
            "status": (primary or {}).get("book_speaker_status", turn.get("status")),
            "review_issue": turn.get("review_issue"),
            "hybrid_repair": bool(turn.get("hybrid_repair")),
            # QUAL REGRA ESCREVEU ESTA VOZ. `turn_consistency` carimba cada turno
            # que reescreve (`sanduiche_de_tres_turnos`, `vocativos_reciprocos`,
            # `referencia_em_terceira_pessoa`, `resposta_ao_vocativo`) e cada um
            # que abstem por falta de alternativa. Sem trazer o carimbo para ca,
            # nao da para separar "faltou regra" de "regra existente causou dano"
            # — e as duas conclusoes levam a trabalhos opostos.
            "consistency_rule": turn.get("consistency_rule"),
        }
    return outcomes


def _category(base, candidate):
    if base["correct"] and candidate["correct"]:
        return "both_correct"
    if not base["correct"] and candidate["correct"]:
        return "candidate_saves"
    if base["correct"] and not candidate["correct"]:
        return "candidate_harms"
    if not base["assigned"] and candidate["assigned"]:
        return "candidate_fills_but_wrong"
    if base["assigned"] and not candidate["assigned"]:
        return "candidate_abstains_on_error"
    if base["predicted"] == candidate["predicted"]:
        return "both_wrong_same"
    return "both_wrong_different"


def compare_runs(gold, baseline, candidates):
    """Compare one baseline with named candidates without changing runtime decisions."""
    base = turn_outcomes(gold, baseline)
    candidate_outcomes = {name: turn_outcomes(gold, run) for name, run in candidates.items()}
    rows = []
    for item_id, reference in base.items():
        row = {key: value for key, value in reference.items()
               if key not in {"predicted", "correct", "assigned"}}
        row.update(baseline_predicted=reference["predicted"],
                   baseline_correct=reference["correct"],
                   baseline_assigned=reference["assigned"])
        for name, outcomes in candidate_outcomes.items():
            current = outcomes[item_id]
            row[f"{name}_predicted"] = current["predicted"]
            row[f"{name}_correct"] = current["correct"]
            row[f"{name}_assigned"] = current["assigned"]
            row[f"{name}_confidence"] = current["confidence"]
            row[f"{name}_status"] = current["status"]
            row[f"{name}_review_issue"] = current["review_issue"]
            row[f"{name}_hybrid_repair"] = current["hybrid_repair"]
            row[f"{name}_consistency_rule"] = current["consistency_rule"]
            row[f"{name}_category"] = _category(
                {"predicted": row["baseline_predicted"], "correct": row["baseline_correct"],
                 "assigned": row["baseline_assigned"]}, current)
        rows.append(row)

    summaries = {}
    for name in candidates:
        dublavel = [row for row in rows if row["class"] == "dublavel"]
        counts = Counter(row[f"{name}_category"] for row in dublavel)
        scene_counts = defaultdict(Counter)
        for row in dublavel:
            scene_counts[str(row["scene"])][row[f"{name}_category"]] += 1
        # ── DE ONDE VEM O ERRO QUE SOBROU ──────────────────────────────────
        # Um erro atribuido por uma regra de consistencia e um erro que o motor
        # ja teve a chance de decidir e decidiu errado; um erro sem carimbo veio
        # da primeira leitura. Separar os dois e o que diz se o proximo passo e
        # apertar regra existente ou escrever mecanismo novo.
        wrong_by_rule = Counter()
        for row in dublavel:
            if row[f"{name}_assigned"] and not row[f"{name}_correct"]:
                wrong_by_rule[row[f"{name}_consistency_rule"] or "sem_regra"] += 1
        summaries[name] = {
            "categories": dict(counts),
            "net_correct": counts["candidate_saves"] - counts["candidate_harms"],
            "wrong_by_consistency_rule": dict(wrong_by_rule),
            "per_scene": {scene: dict(values) for scene, values in scene_counts.items()
                          if values["candidate_saves"] or values["candidate_harms"]},
            "baseline_metrics": evaluate(gold, baseline).get("by_class", []),
            "candidate_metrics": evaluate(gold, candidates[name]).get("by_class", []),
        }
    return {"gold": gold.get("name"), "rows": rows, "candidates": summaries}


def render_markdown(report):
    lines = [f"# Diferencial por turno — {report['gold']}", "",
             "Este relatório compara decisões; o motor em produção não consulta o gabarito.", ""]
    for name, summary in report["candidates"].items():
        counts = summary["categories"]
        lines.extend([
            f"## {name}", "",
            f"- Salva erros/abstenções do baseline: **{counts.get('candidate_saves', 0)}**.",
            f"- Estraga acertos do baseline: **{counts.get('candidate_harms', 0)}**.",
            f"- Saldo de acertos: **{summary['net_correct']:+d}**.",
            f"- Preenche uma lacuna com voz errada: **{counts.get('candidate_fills_but_wrong', 0)}**.",
            f"- Abstém onde o baseline errava: **{counts.get('candidate_abstains_on_error', 0)}**.",
            "", "### Cenas em que houve ganho ou dano", "",
            "| Cena | Salva | Estraga | Saldo |", "|---:|---:|---:|---:|",
        ])
        for scene, values in sorted(summary["per_scene"].items(), key=lambda item: int(item[0])):
            saves = values.get("candidate_saves", 0)
            harms = values.get("candidate_harms", 0)
            lines.append(f"| {scene} | {saves} | {harms} | {saves - harms:+d} |")
        # Onde o erro que sobrou foi decidido: `sem_regra` veio da primeira
        # leitura; o resto passou por uma regra de consistencia que teve a chance
        # de decidir e decidiu errado.
        por_regra = summary.get("wrong_by_consistency_rule") or {}
        lines.extend(["", "### Erros que restaram, por regra que escreveu a voz", "",
                      "| Regra | Erros |", "|---|---:|"])
        for regra, total in sorted(por_regra.items(), key=lambda item: -item[1]):
            lines.append(f"| {regra} | {total} |")
        lines.append("")
    return "\n".join(lines)


