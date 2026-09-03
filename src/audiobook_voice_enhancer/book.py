from __future__ import annotations

import json
import re
from pathlib import Path


def load_book(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8-sig")
    if suffix == ".srt":
        text = path.read_text(encoding="utf-8-sig")
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
        return "\n\n".join(BeautifulSoup(item.get_content(), "html.parser").get_text(" ", strip=True)
                              for item in book.get_items_of_type(ITEM_DOCUMENT))
    raise ValueError(f"Formato de livro não suportado: {suffix}. Use TXT, EPUB, SRT ou JSON.")


def paragraphs(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", block).strip() for block in re.split(r"\n\s*\n|(?=\b(?:chapter|capítulo)\s+\w+\b)", text, flags=re.I)
            if block.strip()]
