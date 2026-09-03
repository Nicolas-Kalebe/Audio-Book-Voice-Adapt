from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Word:
    word: str
    start: float
    end: float
    probability: float | None = None


@dataclass(slots=True)
class TranscriptSegment:
    id: int
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass(slots=True)
class Dialogue:
    id: str
    text: str
    start: float
    end: float
    speaker: str | None = None
    speaker_confidence: float = 0.0
    alignment_confidence: float = 0.0
    source: str = "transcript"
    reason: str = ""
    eligible: bool = False
    skip_reason: str | None = None


@dataclass(slots=True)
class AudioInfo:
    path: Path
    duration: float
    sample_rate: int
    channels: int
    codec: str
    format_name: str
    tags: dict[str, str] = field(default_factory=dict)


def serialise(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {k: serialise(v) for k, v in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [serialise(v) for v in value]
    if isinstance(value, dict):
        return {str(k): serialise(v) for k, v in value.items()}
    return value
