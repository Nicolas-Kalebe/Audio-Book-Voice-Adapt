"""Roda o protocolo frontier sem API: exporta os pedidos e aplica respostas obtidas por fora.

Os pedidos são exatamente os que o AnthropicProvider enviaria (system + texto + schema),
e as respostas passam pela mesma validação e política de abstenção do pipeline.

    export -> request-NN.md por lote
    apply  -> lê response-NN.json e escreve answers.json {turn_id: nome | null}
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audiobook_voice_enhancer.book import load_book, paragraphs
from audiobook_voice_enhancer.book_speakers import build_book, merge_partial_names
from audiobook_voice_enhancer.frontier_speakers import SCHEMA, SYSTEM, apply_answer, batches, build_prompt, new_stats


def _model(args: argparse.Namespace) -> tuple[dict, list[dict]]:
    blocks = (json.loads(args.blocks.read_text(encoding="utf-8")) if args.blocks
              else paragraphs(load_book(args.book)))
    model = build_book(blocks, {})
    return model, batches(model, (args.first, args.last), args.max_chars)


def export(args: argparse.Namespace) -> int:
    model, selected = _model(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for index, batch in enumerate(selected, 1):
        prompt, _ = build_prompt(model, batch)
        request = ("# SYSTEM\n\n" + SYSTEM + "\n\n# USER\n\n" + prompt + "\n# FORMATO DE SAÍDA (JSON Schema)\n\n"
                   + json.dumps(SCHEMA, ensure_ascii=False, indent=1) + "\n")
        (args.out_dir / f"request-{index:02d}.md").write_text(request, encoding="utf-8")
        print(f"request-{index:02d}.md: paragrafos {batch['first']}-{batch['last']}, {len(batch['turns'])} turnos, "
              f"{len(request)} caracteres")
    return 0


def apply(args: argparse.Namespace) -> int:
    model, selected = _model(args)
    stats = new_stats()
    for index, batch in enumerate(selected, 1):
        _, local = build_prompt(model, batch)
        response = json.loads((args.responses / f"response-{index:02d}.json").read_text(encoding="utf-8"))
        apply_answer(model, batch, local, response, threshold=args.threshold, stats=stats)
    # Como no pipeline (project_to_audio): "Fulano" e "Fulano de Tal" viram uma pessoa so.
    merge_partial_names(model)
    answers = {}
    for batch in selected:
        for turn in batch["turns"]:
            entity = model["entities"].get(turn["speaker_entity_id"])
            answers[turn["id"]] = entity["name"] if entity and turn["status"] != "conflict" else None
    args.answers_out.parent.mkdir(parents=True, exist_ok=True)
    args.answers_out.write_text(json.dumps(answers, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.decisions_out:
        decisions = {turn["id"]: {"status": turn["status"], "proposal": turn.get("proposal"),
                                  "issue": turn.get("review_issue")}
                     for batch in selected for turn in batch["turns"]}
        args.decisions_out.write_text(json.dumps(decisions, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("export", "apply"):
        command = sub.add_parser(name)
        source = command.add_mutually_exclusive_group(required=True)
        source.add_argument("--book", type=Path)
        source.add_argument("--blocks", type=Path, help="JSON com a lista de paragrafos (pacote cego)")
        command.add_argument("--first", type=int, required=True)
        command.add_argument("--last", type=int, required=True)
        command.add_argument("--max-chars", type=int, default=150_000)
        if name == "export":
            command.add_argument("--out-dir", type=Path, required=True)
        else:
            command.add_argument("--responses", type=Path, required=True)
            command.add_argument("--answers-out", type=Path, required=True)
            command.add_argument("--decisions-out", type=Path)
            command.add_argument("--threshold", type=float, default=.70)
    args = parser.parse_args()
    return export(args) if args.command == "export" else apply(args)


if __name__ == "__main__":
    raise SystemExit(main())
