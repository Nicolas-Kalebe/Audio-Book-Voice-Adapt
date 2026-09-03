from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .pipeline import Pipeline


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="Audiobook Voice Enhancer", description="Converte somente diálogos elegíveis de personagens configurados.")
    sub = result.add_subparsers(dest="command", required=True)
    for name in ("analyze", "process"):
        command = sub.add_parser(name, help="Analisa sem alterar áudio" if name == "analyze" else "Analisa e converte")
        command.add_argument("source", type=Path, help="Arquivo de áudio ou diretório de capítulos")
        command.add_argument("--book-text", type=Path, help="Livro em TXT, EPUB, SRT ou JSON")
        command.add_argument("--language", default="auto", help="auto, pt, en, ...")
        command.add_argument("--model", help="Sobrescreve transcription.model (útil para teste rápido)")
        command.add_argument("--device", choices=("auto", "cuda", "cpu"), help="Sobrescreve device")
        command.add_argument("--config", type=Path, default=Path("config/config.yaml"))
        command.add_argument("--characters", type=Path, default=Path("config/characters.json"))
        command.add_argument("--output", type=Path, default=Path("output"))
        command.add_argument("--cache", type=Path, default=Path("cache"))
        command.add_argument("--dry-run", action="store_true", help="Não modifica áudio; gera analysis.json")
    character = sub.add_parser("character", help="Gerencia config/characters.json")
    character_sub = character.add_subparsers(dest="character_command", required=True)
    listing = character_sub.add_parser("list", help="Lista personagens")
    listing.add_argument("--characters", type=Path, default=Path("config/characters.json"))
    for action in ("add", "set"):
        item = character_sub.add_parser(action, help=f"{action} personagem")
        item.add_argument("name")
        item.add_argument("--mode", required=True, choices=("original", "convert", "auto", "ignore"))
        item.add_argument("--voice", type=Path)
        item.add_argument("--gender")
        item.add_argument("--age-group")
        item.add_argument("--pitch-shift", type=float)
        item.add_argument("--characters", type=Path, default=Path("config/characters.json"))
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "character":
        return _character(args)
    try:
        pipeline = Pipeline(Path.cwd(), args.config, args.characters, args.output, args.cache)
        if args.model:
            pipeline.config.setdefault("transcription", {})["model"] = args.model
        if args.device:
            pipeline.config["device"] = args.device
        report = pipeline.run(args.source, command=args.command, language=args.language, book_text=args.book_text, dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("Interrompido; caches concluídos foram preservados.", file=sys.stderr)
        return 130
    except Exception as exc:
        logging.getLogger(__name__).exception("Processamento falhou")
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    print(f"Segments analyzed: {report['segments_analyzed']}")
    print(f"Dialogues detected: {report['dialogues_detected']}")
    print(f"Segments converted: {report['segments_converted']}")
    if report.get("characters_planned_for_conversion"):
        print("Conversion plan:")
        for name, count in report["characters_planned_for_conversion"].items():
            print(f"  {name}: {count} segments")
    print(f"Low confidence segments: {report['low_confidence_segments']}")
    print(f"Estimated audio requiring conversion: {report['estimated_conversion_seconds'] / 60:.1f} minutes")
    print(f"Reports: {args.output.resolve()}")
    return 0


def _character(args: argparse.Namespace) -> int:
    path: Path = args.characters
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"__narrator__": {"mode": "original"}}
        if args.character_command == "list":
            print("CHARACTERS\n")
            for name, item in data.items():
                print(name)
                print(f"Mode: {item.get('mode', 'original')}")
                if item.get("voice_reference"):
                    print(f"Voice: {Path(item['voice_reference']).name}")
                print()
            return 0
        exists = args.name in data
        if args.character_command == "add" and exists:
            raise ValueError(f"Character {args.name!r} already exists; use 'character set'.")
        current = dict(data.get(args.name, {}))
        current["mode"] = args.mode
        if args.voice is not None: current["voice_reference"] = str(args.voice).replace("\\", "/")
        if args.gender is not None: current["gender"] = args.gender
        if args.age_group is not None: current["age_group"] = args.age_group
        if args.pitch_shift is not None: current["pitch_shift"] = args.pitch_shift
        if args.mode == "convert" and not current.get("voice_reference"):
            raise ValueError("mode convert requires --voice or an existing voice_reference")
        data[args.name] = current
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        print(f"{args.name}: mode={args.mode}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
