from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .audio import conform_segment, extract_segment, probe
from .config import ConfigurationError, load_characters, load_config
from .voice_conversion import select_converter


def generate_preview(root: Path, source: Path, character_name: str, config_path: Path,
                     characters_path: Path, output: Path, start: float = 0, duration: float = 20) -> dict[str, Path]:
    root = root.resolve()
    config = load_config(config_path)
    characters = load_characters(characters_path, project_root=root, require_references=False)
    if character_name not in characters:
        raise ConfigurationError(f"Personagem não encontrado: {character_name}")
    character: dict[str, Any] = characters[character_name]
    configured_reference = character.get("_resolved_voice_reference") or character.get("voice_reference")
    reference = ((root / configured_reference).resolve() if configured_reference and not Path(configured_reference).is_absolute()
                 else Path(configured_reference).resolve() if configured_reference else None)
    if not reference or not reference.is_file():
        raise ConfigurationError(f"Escolha uma referência de voz válida para {character_name}.")
    info = probe(source)
    start = min(max(0.0, start), max(0.0, info.duration - 0.1))
    duration = min(max(3.0, duration), 60.0, max(0.1, info.duration - start))
    end = start + duration
    slug = re.sub(r"[^a-z0-9]+", "_", character_name.casefold()).strip("_") or "character"
    output.mkdir(parents=True, exist_ok=True)
    original = output / f"{slug}-original.wav"
    raw = output / f"{slug}-converted-raw.wav"
    converted = output / f"{slug}-converted.wav"
    extract_segment(source, original, start, end)
    converter = select_converter(config, root)
    try:
        converter.convert(original, reference, raw, character)
    finally:
        if hasattr(converter, "close"):
            converter.close()
    crossfade = config.get("crossfade", {})
    fade = min(int(crossfade.get("max_ms", 150)), max(int(crossfade.get("min_ms", 30)), round(duration * 100)))
    conform_segment(raw, original, converted, duration, fade)
    raw.unlink(missing_ok=True)
    return {"original": original, "converted": converted}
