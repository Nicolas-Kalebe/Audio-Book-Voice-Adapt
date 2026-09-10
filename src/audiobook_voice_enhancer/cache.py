from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable


class ReplayMiss(RuntimeError):
    """A frozen request was not recorded; never substitute a fresh inference."""


class Cache:
    STAGES = ("transcription", "alignment", "dialogue_detection", "speaker_analysis", "llm", "llm_diagnostics", "converted_audio", "checkpoints", "book_speakers")

    def __init__(self, root: Path):
        self.root = root
        for stage in self.STAGES:
            (root / stage).mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    @staticmethod
    def digest(*values: Any) -> str:
        payload = json.dumps(values, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def file_fingerprint(path: Path) -> dict[str, Any]:
        stat = path.stat()
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            head = stream.read(1024 * 1024)
            hasher.update(head)
            if stat.st_size > 1024 * 1024:
                stream.seek(max(0, stat.st_size - 1024 * 1024))
                hasher.update(stream.read())
        return {"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sample_hash": hasher.hexdigest()}

    def path(self, stage: str, key: str, suffix: str = ".json") -> Path:
        return self.root / stage / f"{key}{suffix}"

    def json(self, stage: str, key: str, producer: Callable[[], Any]) -> Any:
        target = self.path(stage, key)
        if target.is_file():
            self.hits += 1
            return json.loads(target.read_text(encoding="utf-8"))
        self.misses += 1
        value = producer()
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temporary.replace(target)
        return value


class FrozenCache(Cache):
    """Read-only exact-request replay. Does not create folders or call producers."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        if not self.root.is_dir():
            raise ValueError(f"Frozen cache not found: {self.root}")
        self.hits = self.misses = 0
        self.used = {}

    def json(self, stage, key, producer):
        target = self.path(stage, key)
        if not target.is_file():
            self.misses += 1
            raise ReplayMiss(f"Frozen request missing: {stage}/{key}")
        raw = target.read_bytes()
        value = json.loads(raw)
        self.hits += 1
        self.used[f"{stage}/{key}"] = hashlib.sha256(raw).hexdigest()
        return value
