from __future__ import annotations

import json
import re
from pathlib import Path


def load_book(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return read_text_robust(path)
    if suffix == ".srt":
        text = read_text_robust(path)
        text = re.sub(r"(?m)^\d+\s*$|^\d\d:\d\d:\d\d[,.]\d+\s+-->.*$", "", text)
        return re.sub(r"<[^>]+>", "", text)
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, str):
            return data
        if isinstance(data, list):
            return "\n\n".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in data)
        if isinstance(data, dict):
            if "text" in data:
                return str(data["text"])
            if "segments" in data:
                return "\n".join(str(item.get("text", "")) for item in data["segments"])
    if suffix == ".epub":
        from bs4 import BeautifulSoup
        from ebooklib import ITEM_DOCUMENT, epub
        book = epub.read_epub(str(path), options={"ignore_ncx": True})
        documents: list[str] = []
        for item in book.get_items_of_type(ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_content(), "html.parser")
            blocks = [tag.get_text(" ", strip=True) for tag in soup.select("h1, h2, h3, h4, h5, h6, p, blockquote")]
            blocks = [block for block in blocks if block]
            if blocks:
                documents.append("\n\n".join(blocks))
        return "\n\n".join(documents)
    raise ValueError(f"Formato de livro não suportado: {suffix}. Use TXT, EPUB, SRT ou JSON.")


def read_text_robust(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    # latin-1 maps every byte and is preferable to silently dropping book content.
    return raw.decode("latin-1")


def paragraphs(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", block).strip() for block in re.split(r"\n\s*\n|(?=\b(?:chapter|capítulo)\s+\w+\b)", text, flags=re.I)
            if block.strip()]
