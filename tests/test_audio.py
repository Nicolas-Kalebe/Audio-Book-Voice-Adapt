from pathlib import Path

from audiobook_voice_enhancer.audio import discover_audio, reconstruct


def test_natural_chapter_order(tmp_path):
    for name in ("Chapter 10.mp3", "Chapter 2.mp3", "Chapter 01.mp3", "ignore.txt"):
        (tmp_path / name).touch()
    assert [item.name for item in discover_audio(tmp_path)] == ["Chapter 01.mp3", "Chapter 2.mp3", "Chapter 10.mp3"]


def test_no_replacements_preserves_original_bytes(tmp_path):
    source, target = tmp_path / "source.mp3", tmp_path / "target.mp3"
    source.write_bytes(b"not decoded because copy is intentional")
    reconstruct(source, [], target, "320k")
    assert target.read_bytes() == source.read_bytes()
