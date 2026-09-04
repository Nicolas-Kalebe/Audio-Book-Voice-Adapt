from __future__ import annotations

import argparse
import copy
import json
import time
from collections import Counter
from pathlib import Path

from audiobook_voice_enhancer.book import load_book, paragraphs
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.character_discovery import build_alias_map
from audiobook_voice_enhancer.config import load_characters, load_config
from audiobook_voice_enhancer.dialogue import book_character_names
from audiobook_voice_enhancer.llm import build_provider, review_scenes


def main() -> None:
    parser = argparse.ArgumentParser(description="Mede a revisão contextual local em um relatório existente")
    parser.add_argument("analysis", type=Path)
    parser.add_argument("book", type=Path)
    parser.add_argument("--config", type=Path, default=Path("config/config.yaml"))
    parser.add_argument("--characters", type=Path, default=Path("config/characters.json"))
    parser.add_argument("--cache", type=Path, default=Path("cache/benchmark-llm"))
    parser.add_argument("--scene", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    config = load_config(args.config)
    provider = build_provider(config.get("llm", {}))
    if not provider:
        raise SystemExit("LLM desativado ou sem modelo configurado")
    report = json.loads(args.analysis.read_text(encoding="utf-8"))
    dialogues = copy.deepcopy(report["files"][0]["dialogues"])
    if args.scene is not None:
        dialogues = [item for item in dialogues if int(item.get("scene_id", -1)) == args.scene]
    blocks = paragraphs(load_book(args.book))
    characters = load_characters(args.characters, project_root=args.characters.parent.parent,
                                 allow_shared=True, require_references=False)
    aliases = build_alias_map(characters)
    known = book_character_names(blocks, aliases) | set(characters)
    before = Counter(item.get("speaker") or "unknown" for item in dialogues)
    wall_started = time.perf_counter()
    stats = review_scenes(provider, Cache(args.cache), dialogues, blocks, known,
                          float(config["speaker_confidence_threshold"]))
    result = {
        "model": provider.model,
        "scene_filter": args.scene,
        "wall_seconds": round(time.perf_counter() - wall_started, 3),
        "engine_stats": stats,
        "before": dict(before),
        "after": dict(Counter(item.get("speaker") or "unknown" for item in dialogues)),
        "decisions": [
            {key: item.get(key) for key in ("id", "scene_id", "book_paragraph_id", "text", "speaker",
                                            "speaker_confidence", "llm_suggestion", "llm_confidence", "llm_reason")}
            for item in dialogues if item.get("llm_suggestion")
        ],
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
