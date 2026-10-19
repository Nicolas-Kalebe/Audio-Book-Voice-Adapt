"""Teto da tarefa: um modelo de ponta atribui os mesmos turnos que o Qwen recebeu.

Mede se a imprecisao vem do modelo local ou da propria tarefa. Usa a deteccao de
uma rodada existente (mesmos turnos, mesmas falas nao localizadas) e troca apenas
o falante, para que o placar seja comparavel ao do Qwen.

    export  -> escreve o pacote de entrada (texto numerado + turnos), sem gabarito
    score   -> aplica as respostas a uma copia da analise e avalia contra o gabarito
"""
from __future__ import annotations

import argparse
import copy
import json
from collections import OrderedDict
from pathlib import Path

from audiobook_voice_enhancer.benchmark import evaluate, load_gold, render_markdown
from audiobook_voice_enhancer.book import load_book, paragraphs
from audiobook_voice_enhancer.dialogue import book_character_names

INSTRUCTIONS = """\
Tarefa: para cada turno de fala listado, diga QUEM fala, usando apenas o texto abaixo.

- Responda com o nome do personagem como ele aparece no texto.
- Se a fala vem de um papel sem nome (ex.: "um guarda"), descreva o papel.
- Se nao houver certeza razoavel, responda null. Abster e seguro; trocar a voz
  errada e o unico defeito que conta. Mas abster em excesso tambem reprova.
- Pensamentos ou contato mental entre aspas nao sao fala audivel: responda null.

Saida: um unico objeto JSON {"<turn_key>": "<nome>" | null, ...} com TODAS as
chaves listadas em TURNOS, e nada mais.
"""


def _turn_key(item: dict) -> str:
    turn_id = str(item.get("turn_id") or "")
    return turn_id if turn_id.startswith("book-") else f"id:{item['id']}"


def _turns(analysis: dict) -> "OrderedDict[str, list[dict]]":
    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for file_result in analysis.get("files", []):
        for item in file_result.get("dialogues", []):
            grouped.setdefault(_turn_key(item), []).append(item)
    return grouped


def export(args: argparse.Namespace) -> int:
    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    blocks = paragraphs(load_book(args.book))
    turns = _turns(analysis)
    numbers = [int(item["book_paragraph_id"]) for items in turns.values() for item in items
               if item.get("book_paragraph_id") is not None]
    first = max(0, min(numbers) - args.context_before)
    last = min(len(blocks) - 1, max(numbers) + args.context_after)
    names = sorted(book_character_names(blocks, {}))

    lines = [INSTRUCTIONS, "", "PERSONAGENS CONHECIDOS DO LIVRO (grafia de referencia):",
             ", ".join(names), "", f"TEXTO (paragrafos {first}-{last}):", ""]
    lines += [f"[{index}] {blocks[index]}" for index in range(first, last + 1)]
    lines += ["", "TURNOS (chave | paragrafo | inicio da fala detectada):", ""]
    for key, items in turns.items():
        primary = min(items, key=lambda item: int(item.get("fragment_index", 0)))
        snippet = " ".join(str(primary.get("text", "")).split())[:90]
        lines.append(f"{key} | {primary.get('book_paragraph_id')} | {snippet}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(turns)} turnos, paragrafos {first}-{last} -> {args.output}")
    return 0


def score(args: argparse.Namespace) -> int:
    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    answers = json.loads(args.answers.read_text(encoding="utf-8"))
    gold = load_gold(args.gold)

    replaced = copy.deepcopy(analysis)
    turns = _turns(replaced)
    missing = [key for key in turns if key not in answers]
    if missing:
        # Turno que o protocolo nao enxergou fica sem voz: abstencao, nunca palpite.
        print(f"Aviso: {len(missing)} turnos sem resposta contam como abstencao: {missing[:10]}")
    for key, items in turns.items():
        speaker = answers.get(key) or None
        for item in items:
            item["speaker"] = speaker
            item["source"] = "frontier_ceiling"

    baseline = evaluate(gold, analysis)
    result = evaluate(gold, replaced)
    markdown = render_markdown(result)
    print(markdown)
    print("| Dubláveis | Precisão | Cobertura | Cobertura dos detectados | Corretos | Errados | Abstenções | Não detectados |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for label, value in (("Qwen (rodada original)", baseline), (args.label, result)):
        row = next(item for item in value["by_class"] if item["class"] == "dublavel")
        detected_coverage = row["assigned"] / row["detected"] if row["detected"] else 0.0
        print(f"| {label} | {row['precision_by_identity']:.2%} | {row['coverage']:.2%} | "
              f"{detected_coverage:.2%} | {row['correct_by_identity']} | {row['wrong_by_identity']} | "
              f"{row['abstained']} | {row['missing']} |")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export")
    exp.add_argument("--analysis", type=Path, required=True)
    exp.add_argument("--book", type=Path, required=True)
    exp.add_argument("--output", type=Path, required=True)
    exp.add_argument("--context-before", type=int, default=40)
    exp.add_argument("--context-after", type=int, default=3)
    sc = sub.add_parser("score")
    sc.add_argument("--analysis", type=Path, required=True)
    sc.add_argument("--answers", type=Path, required=True)
    sc.add_argument("--gold", type=Path, required=True)
    sc.add_argument("--json-output", type=Path)
    sc.add_argument("--label", default="modelo de ponta")
    args = parser.parse_args()
    return export(args) if args.command == "export" else score(args)


if __name__ == "__main__":
    raise SystemExit(main())
