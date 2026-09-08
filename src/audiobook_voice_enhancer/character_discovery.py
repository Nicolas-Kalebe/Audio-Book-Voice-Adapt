from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .dialogue import turn_representatives


IGNORED_NAMES = {
    "unknown", "desconhecido", "ele", "ela", "eles", "elas", "isso", "isto", "aquele", "aquela",
    "he", "she", "they", "it", "someone", "alguém", "homem", "mulher", "menino", "menina",
}


def build_alias_map(characters: dict[str, dict[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for name, item in characters.items():
        if name.startswith("__"):
            continue
        aliases[name.casefold()] = name
        configured_aliases = item.get("aliases", [])
        if isinstance(configured_aliases, str):
            configured_aliases = [configured_aliases]
        for alias in configured_aliases:
            normalized = " ".join(str(alias).split()).casefold()
            if normalized:
                aliases[normalized] = name
    return aliases


def _valid_character_name(value: Any, *, structured: bool = False) -> str | None:
    name = " ".join(str(value or "").split())
    if not structured:
        name = name.strip(".,:;!?—–-\"'()[]{}")
    if not name or name.casefold() in IGNORED_NAMES or name.startswith("__"):
        return None
    if len(name) > (160 if structured else 80) or len(name.split()) > (16 if structured else 4) or not name[0].isupper():
        return None
    return name


def discover_characters(report: dict[str, Any], confidence_threshold: float = 0.85) -> dict[str, dict[str, Any]]:
    observations: dict[str, list[float]] = defaultdict(list)
    for item in report.get("files", []):
        for dialogue in turn_representatives(item.get("dialogues", [])):
            name = _valid_character_name(dialogue.get("speaker"), structured=bool(dialogue.get("speaker_entity_id")))
            if name:
                observations[name].append(float(dialogue.get("speaker_confidence", 0)))
    discovered: dict[str, dict[str, Any]] = {}
    for name, values in sorted(observations.items(), key=lambda pair: pair[0].casefold()):
        strong = sum(value >= confidence_threshold for value in values)
        discovered[name] = {
            "mentions": len(values),
            "high_confidence_mentions": strong,
            "confidence": round(max(values), 4),
            "review_required": strong == 0,
        }
    return discovered


def merge_detected_characters(path: Path, report: dict[str, Any], confidence_threshold: float = 0.85) -> dict[str, list[str]]:
    characters = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"__narrator__": {"mode": "original"}}
    discovered = discover_characters(report, confidence_threshold)
    added: list[str] = []
    updated: list[str] = []
    existing_names = {name.casefold(): name for name in characters}
    for detected_name, detection in discovered.items():
        name = existing_names.get(detected_name.casefold(), detected_name)
        if name not in characters:
            characters[name] = {"mode": "original", "detection": {"automatic": True, **detection}}
            added.append(name)
            existing_names[name.casefold()] = name
        else:
            previous = characters[name].get("detection")
            if previous and previous.get("automatic"):
                reviewed = bool(previous.get("reviewed"))
                characters[name]["detection"] = {
                    "automatic": True,
                    **detection,
                    "review_required": False if reviewed else detection["review_required"],
                    "reviewed": reviewed,
                }
                updated.append(name)
    if added or updated:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(characters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    return {"added": added, "updated": updated}
