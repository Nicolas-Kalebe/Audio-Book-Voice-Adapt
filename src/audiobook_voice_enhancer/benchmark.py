from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml


def _fold(value: str | None) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in value if not unicodedata.combining(char)).casefold().strip()


def _text_key(value: str | None) -> str:
    return " ".join(re.findall(r"\w+", _fold(value)))


# Palavras funcionais: nao distinguem uma pessoa de outra dentro de uma descricao.
ROLE_STOPWORDS = {"a", "as", "o", "os", "um", "uma", "uns", "umas", "de", "do", "da",
                  "dos", "das", "e", "com", "que", "the", "of", "and", "with"}


def _role_key(value: str | None) -> str:
    """Compara papeis anonimos por identidade, nao por grafia.

    Remove o desambiguador entre colchetes que o motor anexa quando dois rotulos
    colidem, dobra acentos, ignora artigos/preposicoes e a ordem das palavras.
    Nao aproxima descricoes diferentes: 'elfo alto' e 'elfo louro' seguem distintos.
    """
    stripped = re.sub(r"\s*\[[^\]]*\]\s*$", "", value or "")
    words = sorted(word for word in re.findall(r"\w+", _fold(stripped))
                   if word not in ROLE_STOPWORDS)
    return " ".join(words)


def _role_aliases(gold: dict[str, Any]) -> dict[str, set[str]]:
    """Descritores do livro que um humano aceitou como o mesmo papel do gabarito.

    Cada entrada e uma decisao revisada e congelada, escrita no gabarito antes da
    rodada. Nao ha reconciliacao automatica depois de ver as respostas do modelo.
    """
    table: dict[str, set[str]] = {}
    for label, accepted in (gold.get("role_aliases") or {}).items():
        table[_fold(label)] = {_role_key(label), *(_role_key(item) for item in accepted)}
    return table


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
    role_aliases = _role_aliases(gold)

    def same_identity(predicted: str | None, expected: str) -> bool:
        """Igualdade por identidade: mesma pessoa, escrita de outro jeito."""
        if not predicted:
            return False
        key = _role_key(predicted)
        return bool(key) and (key == _role_key(expected)
                              or key in role_aliases.get(_fold(expected), set()))

    files = analysis.get("files", [])
    candidates = [item for file_result in files for item in file_result.get("dialogues", [])]
    by_id = {str(item["id"]): item for item in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("O relatorio contem IDs duplicados")
    paragraph_scenes = {
        int(item["book_paragraph_id"]): int(item.get("scene_id", -1))
        for item in candidates if item.get("book_paragraph_id") is not None
    }

    def scene_for(paragraph: int) -> int:
        if paragraph in paragraph_scenes:
            return paragraph_scenes[paragraph]
        if not paragraph_scenes:
            return -1
        nearest = min(paragraph_scenes, key=lambda value: abs(value - paragraph))
        return paragraph_scenes[nearest]

    legacy_fragments = {str(value) for value in gold.get("continuation_fragments", [])}
    standalone_quotes = {str(value) for value in gold.get("standalone_quote_turn_ids", [])}
    turns: dict[str, dict[str, Any]] = {}

    def paragraph_from_id(item_id: str) -> int:
        return int(item_id.split("-", 1)[0])

    for item_id, speaker in spoken.items():
        if item_id in legacy_fragments:
            continue
        paragraph = paragraph_from_id(item_id)
        key = f"id:{item_id}" if item_id in standalone_quotes else f"p:{paragraph}"
        if key in turns:
            raise ValueError(f"Dois turnos principais ocupam a mesma chave: {key}")
        turns[key] = {"id": item_id, "paragraph": paragraph, "speaker": speaker,
                      "acceptable": acceptable.get(item_id, set())}
    for source in gold.get("missing_spoken", []):
        paragraph = int(source["book_paragraph_id"])
        key = f"p:{paragraph}"
        if key in turns:
            raise ValueError(f"Fala ausente duplica um turno anotado: {key}")
        turns[key] = {"id": str(source["id"]), "paragraph": paragraph,
                      "speaker": source["speaker"], "acceptable": set(), "text": source.get("text", "")}

    candidates_by_turn: dict[str, list[dict[str, Any]]] = defaultdict(list)
    detected_non_spoken: list[dict[str, Any]] = []
    unexpected: list[str] = []
    for item in candidates:
        item_id = str(item["id"])
        if item_id in standalone_quotes:
            key = f"id:{item_id}"
        else:
            turn_id = str(item.get("turn_id", ""))
            if turn_id.startswith("book-") and turn_id[5:].isdigit():
                paragraph = int(turn_id[5:])
            else:
                paragraph = item.get("book_paragraph_id")
                paragraph = int(paragraph) if paragraph is not None else -1
            key = f"p:{paragraph}"
        if item.get("dialogue_style") == "dash" and key in turns:
            candidates_by_turn[key].append(item)
        elif item_id in non_spoken:
            detected_non_spoken.append(item)
        elif key in turns:
            candidates_by_turn[key].append(item)
        else:
            unexpected.append(item_id)
    if unexpected:
        raise ValueError(f"Candidatos sem anotacao no gabarito: {sorted(unexpected)}")

    expected_counts = {paragraph_from_id(item_id): 2
                       for item_id in gold.get("incomplete_turn_ids", [])}
    expected_counts.update({int(key): int(value)
                            for key, value in gold.get("expected_fragment_count_overrides", {}).items()})
    text_expectations = {int(key): str(value)
                         for key, value in gold.get("boundary_text_expectations", {}).items()}
    figurante_labels = {_fold(label) for label in (gold.get("anonymous_role_labels") or [])}

    def turn_class(expected: str) -> str:
        """Figurante de uma cena so nao ganha voz; nao entra na conta que decide
        o produto. Decisao do proprietario em 08/09/2026."""
        return "figurante" if _fold(expected) in figurante_labels else "dublavel"

    total_source_turns = len(turns)
    assigned = 0
    correct = 0
    identity_correct = 0
    wrong_turns = 0
    identity_wrong = 0
    abstained = 0
    literal_only_misses: list[dict[str, Any]] = []
    by_class: dict[str, Counter[str]] = {"dublavel": Counter(), "figurante": Counter()}
    correct_and_complete = 0
    wrong: list[dict[str, Any]] = []
    confusion: Counter[tuple[str, str]] = Counter()
    per_speaker_total = Counter(turn["speaker"] for turn in turns.values())
    per_speaker_correct: Counter[str] = Counter()
    detected_turns = 0
    complete_detected_turns = 0
    dynamically_missing: list[dict[str, Any]] = []
    incomplete_turns: list[dict[str, Any]] = []
    split_scenes = {name: {int(scene) for scene in detail.get("scenes", [])}
                    for name, detail in gold.get("split", {}).items()}
    split_counts = {name: Counter() for name in split_scenes}
    scene_counts = defaultdict(Counter)

    ordered_turns = sorted(turns.items(), key=lambda pair: (pair[1]["paragraph"], pair[0]))
    for key, turn in ordered_turns:
        scene_counter = scene_counts[scene_for(turn["paragraph"])]
        scene_counter["total"] += 1
        klass = by_class[turn_class(turn["speaker"])]
        klass["total"] += 1
        split_name = next((name for name, scenes in split_scenes.items()
                           if scene_for(turn["paragraph"]) in scenes), None)
        if split_name:
            split_counts[split_name]["total"] += 1
        items = sorted(candidates_by_turn.get(key, []),
                       key=lambda item: (int(item.get("fragment_index", 0)), float(item.get("start", 0))))
        expected = turn["speaker"]
        if not items:
            scene_counter["missing"] += 1
            if split_name:
                split_counts[split_name]["missing"] += 1
            dynamically_missing.append({"id": turn["id"], "book_paragraph_id": turn["paragraph"],
                                        "speaker": expected, "text": turn.get("text", "")})
            confusion[(expected, "NAO DETECTADA")] += 1
            klass["missing"] += 1
            continue
        detected_turns += 1
        scene_counter["detected"] += 1
        if split_name:
            split_counts[split_name]["detected"] += 1
        primary = next((item for item in items if int(item.get("fragment_index", 0)) == 0), items[0])
        predicted = primary.get("speaker")
        klass["detected"] += 1
        if predicted:
            scene_counter["assigned"] += 1
            assigned += 1
            klass["assigned"] += 1
            if split_name:
                split_counts[split_name]["assigned"] += 1
        else:
            # Abster nao e erro: e a saida segura do produto, que mantem a voz
            # do narrador. Fica contada em separado, nunca somada com a troca
            # de voz errada.
            abstained += 1
            klass["abstained"] += 1
        is_correct = _fold(predicted) == _fold(expected)
        if turn["acceptable"] and _fold(predicted) in turn["acceptable"]:
            is_correct = True
        # Pontuacao por identidade, ao lado da literal e nunca no lugar dela.
        # Um papel anonimo escrito com outras palavras conta como acerto aqui e
        # como erro na coluna literal; as duas ficam visiveis no relatorio.
        by_identity = is_correct or same_identity(predicted, expected)
        if by_identity:
            identity_correct += 1
            klass["correct_identity"] += 1
            if not is_correct:
                literal_only_misses.append({"id": turn["id"], "paragraph": turn["paragraph"],
                                            "expected": expected, "predicted": predicted})
        elif predicted:
            identity_wrong += 1
            klass["wrong_identity"] += 1
        if predicted and not is_correct:
            wrong_turns += 1

        expected_count = expected_counts.get(turn["paragraph"], 1)
        indices = {int(item.get("fragment_index", 0)) for item in items}
        has_fragment_metadata = all(item.get("turn_id") for item in items)
        complete = expected_count == 1 or (has_fragment_metadata and set(range(expected_count)) <= indices)
        expected_text = text_expectations.get(turn["paragraph"])
        if expected_text is not None:
            complete = complete and _text_key(primary.get("text")) == _text_key(expected_text)
        if complete:
            complete_detected_turns += 1
        else:
            incomplete_turns.append({"id": turn["id"], "book_paragraph_id": turn["paragraph"],
                                     "expected_fragments": expected_count,
                                     "found_fragments": sorted(indices)})

        if is_correct:
            scene_counter["correct"] += 1
            correct += 1
            klass["correct"] += 1
            if split_name:
                split_counts[split_name]["correct"] += 1
            per_speaker_correct[expected] += 1
            every_fragment_correct = all(
                _fold(item.get("speaker")) == _fold(expected)
                or (turn["acceptable"] and _fold(item.get("speaker")) in turn["acceptable"])
                for item in items
            )
            if complete and every_fragment_correct:
                correct_and_complete += 1
        else:
            actual_label = predicted or "SEM ATRIBUICAO"
            confusion[(expected, actual_label)] += 1
            wrong.append({
                "id": turn["id"],
                "paragraph": turn["paragraph"],
                "expected": expected,
                "predicted": predicted,
                "suggestion": primary.get("llm_suggestion"),
                "text": primary.get("text", ""),
            })

    false_turn_candidates = len(detected_non_spoken)
    detection_precision = detected_turns / (detected_turns + false_turn_candidates)
    detection_recall = detected_turns / total_source_turns
    per_character = []
    for speaker, total in per_speaker_total.most_common():
        hit = per_speaker_correct[speaker]
        per_character.append({"speaker": speaker, "correct": hit, "total": total, "recall": hit / total})

    split_metrics = []
    for name, counts in split_counts.items():
        total, split_detected, split_assigned, hit = (
            counts[key] for key in ("total", "detected", "assigned", "correct")
        )
        split_metrics.append({
            "split": name, "total": total, "detected": split_detected,
            "assigned": split_assigned, "correct": hit,
            "end_to_end_accuracy": hit / total if total else 0.0,
            "accuracy_when_assigned": hit / split_assigned if split_assigned else 0.0,
            "coverage": split_assigned / split_detected if split_detected else 0.0,
        })

    return {
        "gold": gold["name"],
        "evaluation_protocol": gold.get("evaluation_protocol", {
            "status": "unverified", "independent_holdout": False,
            "note": "Protocolo independente nao documentado neste gabarito.",
        }),
        "candidates_in_report": len(candidates),
        "spoken_candidate_regions": sum(len(items) for items in candidates_by_turn.values()),
        "non_spoken_candidates": false_turn_candidates,
        "continuation_fragments": sum(max(0, len(items) - 1) for items in candidates_by_turn.values()),
        "gold_source_turns": total_source_turns,
        "detected_source_turns": detected_turns,
        "incomplete_detected_turns": detected_turns - complete_detected_turns,
        "complete_detected_turns": complete_detected_turns,
        "missing_source_turns": total_source_turns - detected_turns,
        "detection_precision": detection_precision,
        "detection_recall": detection_recall,
        "complete_turn_recall": complete_detected_turns / total_source_turns,
        "speaker_assigned_turns": assigned,
        "speaker_correct_turns": correct,
        "speaker_correct_turns_by_identity": identity_correct,
        "end_to_end_accuracy_by_identity": identity_correct / total_source_turns,
        "literal_only_misses": literal_only_misses,
        # Desfecho em tres, nunca em dois: trocar a voz errada e abster sao
        # coisas diferentes para quem escuta, e so uma delas e defeito.
        "speaker_wrong_turns": wrong_turns,
        "speaker_wrong_turns_by_identity": identity_wrong,
        "speaker_abstained_turns": abstained,
        "precision_when_assigned_by_identity": identity_correct / assigned if assigned else 0.0,
        "by_class": [{
            "class": name, "total": counts["total"], "detected": counts["detected"],
            "assigned": counts["assigned"], "abstained": counts["abstained"],
            "missing": counts["missing"], "correct": counts["correct"],
            "correct_by_identity": counts["correct_identity"],
            "wrong_by_identity": counts["wrong_identity"],
            "precision_by_identity": (counts["correct_identity"] / counts["assigned"]
                                      if counts["assigned"] else 0.0),
            "coverage": counts["assigned"] / counts["total"] if counts["total"] else 0.0,
        } for name, counts in by_class.items()],
        "speaker_accuracy_all_detected": correct / detected_turns,
        "speaker_accuracy_when_assigned": correct / assigned if assigned else 0.0,
        "automatic_attribution_coverage": assigned / detected_turns,
        "end_to_end_accuracy": correct / total_source_turns,
        "speaker_and_boundary_end_to_end_accuracy": correct_and_complete / total_source_turns,
        "speaker_correct_and_complete_turns": correct_and_complete,
        "per_character": per_character,
        "per_scene": [{"scene_id": scene, "total": counts["total"], "correct": counts["correct"],
                       "assigned": counts["assigned"], "missing": counts["missing"],
                       "end_to_end_accuracy": counts["correct"] / counts["total"]}
                      for scene, counts in sorted(scene_counts.items())],
        "split_metrics": split_metrics,
        "wrong_or_unassigned": wrong,
        "confusion": [
            {"expected": expected, "predicted": predicted, "count": count}
            for (expected, predicted), count in confusion.most_common()
        ],
        "missing_spoken": dynamically_missing,
        "incomplete_turns": incomplete_turns,
        "known_boundary_issues": gold.get("known_boundary_issues", []),
    }


def render_markdown(result: dict[str, Any]) -> str:
    pct = lambda value: f"{value * 100:.2f}%"
    lines = [
        f"# Baseline auditavel - {result['gold']}",
        "",
        "## Resultado executivo",
        "",
        f"Protocolo: {result.get('evaluation_protocol', {}).get('status', 'unverified')}. "
        f"{result.get('evaluation_protocol', {}).get('note', '')}",
        "Os limites completos abaixo verificam cobertura textual, nao substituem auditoria dos cortes no audio.",
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
        f"({pct(result['end_to_end_accuracy'])}) — comparacao literal, abstencao contada como erro. "
        f"Metrica historica, mantida para comparar com as rodadas antigas.",
        f"- Acuracia ponta a ponta por identidade: **{result.get('speaker_correct_turns_by_identity', 0)}/"
        f"{result['gold_source_turns']}** ({pct(result.get('end_to_end_accuracy_by_identity', 0))}) "
        f"— conta como acerto o papel anonimo descrito com outras palavras; "
        f"{len(result.get('literal_only_misses', []))} turnos separam as duas colunas.",
        f"- Personagem e limite ambos corretos: **{result['speaker_correct_and_complete_turns']}/"
        f"{result['gold_source_turns']}** ({pct(result['speaker_and_boundary_end_to_end_accuracy'])}).",
        "",
        "",
        "## O que decide o produto",
        "",
        "Regra do proprietario, 08/09/2026: **e melhor nao trocar uma voz do que trocar errado** — "
        "sem certeza, o turno fica sem atribuicao e mantem a voz do narrador. Logo abstencao **nao** "
        "e erro, e sim a saida segura; o defeito e a voz trocada errada. E **figurante de uma cena so "
        "nao precisa de voz**, entao esses turnos saem da conta que decide o produto.",
        "",
        f"- Voz trocada errada: **{result.get('speaker_wrong_turns_by_identity', 0)}** turnos. "
        f"Este e o unico numero que representa defeito audivel.",
        f"- Sem atribuicao (mantem o narrador): **{result.get('speaker_abstained_turns', 0)}** turnos.",
        f"- Precisao sobre o que foi atribuido: **{pct(result.get('precision_when_assigned_by_identity', 0))}**.",
        "",
        "| Classe | Total | Atribuidos | Corretos | Errados | Sem atribuicao | Precisao | Cobertura |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        *[f"| {item['class']} | {item['total']} | {item['assigned']} | {item['correct_by_identity']} | "
          f"{item['wrong_by_identity']} | {item['abstained']} | {pct(item['precision_by_identity'])} | "
          f"{pct(item['coverage'])} |" for item in result.get("by_class", [])],
        "",
        "A linha `dublavel` e a que vale. `figurante` fica visivel para auditoria, nunca escondida, "
        "mas nenhum desses turnos vira voz nova.",
        "",
        "## Por personagem ou papel",
        "",
        "| Personagem/papel | Corretas | Total | Recall |",
        "|---|---:|---:|---:|",
    ]
    for item in result["per_character"]:
        lines.append(f"| {item['speaker']} | {item['correct']} | {item['total']} | {pct(item['recall'])} |")
    if result.get("per_scene"):
        lines.extend(["", "## Por cena", "", "| Cena (ID) | Corretas | Total | Ponta a ponta |",
                      "|---|---:|---:|---:|"])
        for item in result["per_scene"]:
            lines.append(f"| {item['scene_id']} | {item['correct']} | {item['total']} | {pct(item['end_to_end_accuracy'])} |")
    lines.extend(["", "## Principais confusoes", "", "| Esperado | Motor atual | Quantidade |", "|---|---|---:|"])
    for item in result["confusion"]:
        lines.append(f"| {item['expected']} | {item['predicted']} | {item['count']} |")
    if result.get("split_metrics"):
        lines.extend(["", "## Separacao de desenvolvimento", "",
                      "| Conjunto | Corretas | Total | Ponta a ponta | Cobertura | Precisao atribuida |",
                      "|---|---:|---:|---:|---:|---:|"])
        for item in result["split_metrics"]:
            lines.append(f"| {item['split']} | {item['correct']} | {item['total']} | "
                         f"{pct(item['end_to_end_accuracy'])} | {pct(item['coverage'])} | "
                         f"{pct(item['accuracy_when_assigned'])} |")
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
