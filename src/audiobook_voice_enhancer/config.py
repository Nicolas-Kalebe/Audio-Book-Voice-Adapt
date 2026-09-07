from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

LOG = logging.getLogger(__name__)

DEFAULT_CONFIG = Path("config/config.yaml")
DEFAULT_CHARACTERS = Path("config/characters.json")


class ConfigurationError(ValueError):
    pass


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigurationError(f"Configuração não encontrada: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    required = ("speaker_confidence_threshold", "alignment_confidence_threshold", "voice_conversion")
    missing = [key for key in required if key not in data]
    if missing:
        raise ConfigurationError(f"Opções obrigatórias ausentes: {', '.join(missing)}")
    for key in ("speaker_confidence_threshold", "alignment_confidence_threshold"):
        if not 0 <= float(data[key]) <= 1:
            raise ConfigurationError(f"{key} deve estar entre 0 e 1")
    if float(data.get("minimum_segment_duration", 0)) < 0:
        raise ConfigurationError("minimum_segment_duration não pode ser negativo")
    book_first = data.get("book_first", {})
    if not isinstance(book_first, dict):
        raise ConfigurationError("book_first deve ser um objeto de configuração")
    if book_first.get("enabled"):
        if book_first.get("protocol", "evidence") not in {"compact", "evidence"}:
            raise ConfigurationError("Análise textual: protocol deve ser compact ou evidence")
        try:
            valid = (0 <= float(book_first.get("automatic_confidence", .90)) <= 1
                     and int(book_first.get("max_turns_per_window", 24)) > 0
                     and int(book_first.get("max_context_characters", 14000)) > 0)
        except (ValueError, TypeError, OverflowError):
            valid = False
        if not valid:
            raise ConfigurationError("Análise textual: confiança deve estar entre 0 e 1 e limites devem ser positivos")
    import math
    try:
        timeout = float(data["voice_conversion"].get("worker_timeout_seconds", 600))
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise ConfigurationError("worker_timeout_seconds deve ser positivo e finito")
    return data


def load_characters(path: Path = DEFAULT_CHARACTERS, *, project_root: Path | None = None,
                    allow_shared: bool = True, require_references: bool = False) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        raise ConfigurationError(f"Base de personagens não encontrada: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"JSON de personagens inválido: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError("characters.json deve ser um objeto nome -> configuração")
    root = project_root or Path.cwd()
    references: dict[Path, list[str]] = {}
    canonical_names = {name.casefold(): name for name in data}
    aliases: dict[str, str] = {}
    valid_modes = {"original", "convert", "auto", "ignore"}
    for name, item in data.items():
        if not isinstance(item, dict):
            raise ConfigurationError(f"Configuração inválida para {name!r}")
        # Read old files safely, but all writes use the explicit mode field.
        if "mode" not in item and "enabled" in item:
            item["mode"] = "convert" if item["enabled"] else "original"
            LOG.warning("Personagem %s usa 'enabled' legado; substitua por 'mode'", name)
        mode = item.get("mode", "original")
        if mode not in valid_modes:
            raise ConfigurationError(f"Modo inválido para {name!r}: {mode!r}. Use original, convert, auto ou ignore")
        if mode in {"convert", "auto"} and item.get("voice_reference"):
            ref = item.get("voice_reference")
            resolved = (root / ref).resolve() if not Path(ref).is_absolute() else Path(ref).resolve()
            item["_resolved_voice_reference"] = str(resolved)
            references.setdefault(resolved, []).append(name)
        if mode == "convert":
            if not item.get("voice_reference"):
                raise ConfigurationError(f'Character "{name}" is configured for conversion, but voice_reference is missing.')
            resolved = Path(item["_resolved_voice_reference"])
            if require_references and not resolved.is_file():
                raise ConfigurationError(f'Character "{name}" is configured for conversion, but voice_reference was not found: {resolved}')
        configured_aliases = item.get("aliases", [])
        if isinstance(configured_aliases, str):
            configured_aliases = [configured_aliases]
            item["aliases"] = configured_aliases
        if not isinstance(configured_aliases, list):
            raise ConfigurationError(f"Aliases inválidos para {name!r}; use uma lista de nomes")
        for alias in configured_aliases:
            normalized = " ".join(str(alias).split()).casefold()
            owner = canonical_names.get(normalized) or aliases.get(normalized)
            if owner and owner != name:
                raise ConfigurationError(f'Alias "{alias}" está associado a {owner} e não pode ser usado também por {name}.')
            if normalized:
                aliases[normalized] = name
    for ref, names in references.items():
        if len(names) > 1:
            message = f"Referência compartilhada por {', '.join(names)}: {ref}"
            if allow_shared:
                LOG.warning(message)
            else:
                raise ConfigurationError(message)
    return data
