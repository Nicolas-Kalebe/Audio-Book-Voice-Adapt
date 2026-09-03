from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from rapidfuzz.fuzz import partial_ratio, ratio


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return " ".join(re.findall(r"[\w']+", "".join(char for char in decomposed if not unicodedata.combining(char))))


def align_blocks(book_blocks: list[str], transcript: dict[str, Any], window: int = 40,
                 initial_cursor: int = 0) -> list[dict[str, Any]]:
    """Monotonic, windowed fuzzy block alignment; never jumps backwards in the book."""
    segments = transcript.get("segments", [])
    if not book_blocks or not segments:
        return []
    normalized_books = [normalize(block) for block in book_blocks]
    cursor = min(max(0, initial_cursor), len(book_blocks) - 1)
    result: list[dict[str, Any]] = []
    for segment in segments:
        needle = normalize(segment.get("text", ""))
        if not needle:
            continue
        best_id, best_score = cursor, 0.0
        # The first audio file may omit cover/front matter; allow a wider initial seek.
        lookahead = max(window, 200) if not result and initial_cursor == 0 else max(2, window)
        upper = min(len(book_blocks), cursor + lookahead)
        for book_id in range(max(0, cursor - 1), upper):
            candidate = normalized_books[book_id]
            score = max(ratio(needle, candidate[:max(len(needle) * 2, 40)]) / 100,
                        ratio(needle, candidate) / 100, partial_ratio(needle, candidate) / 100)
            if score > best_score:
                best_id, best_score = book_id, score
        if best_score >= 0.35:
            cursor = best_id
        result.append({"segment_id": segment["id"], "book_paragraph_id": best_id,
                       "audio_start": segment["start"], "audio_end": segment["end"],
                       "alignment_confidence": round(best_score, 4), "book_text": book_blocks[best_id]})
        if best_score > 0.72 and len(needle) >= len(normalized_books[best_id]) * 0.7:
            cursor = min(best_id + 1, len(book_blocks) - 1)
    return result


def map_phrase_to_words(phrase: str, words: list[dict[str, Any]]) -> tuple[float, float, float] | None:
    phrase_tokens = normalize(phrase).split()
    audio_tokens = [normalize(word.get("word", "")) for word in words]
    audio_tokens = [token for token in audio_tokens if token]
    if not phrase_tokens or not audio_tokens:
        return None
    matcher = SequenceMatcher(None, audio_tokens, phrase_tokens, autojunk=False)
    block = max(matcher.get_matching_blocks(), key=lambda item: item.size)
    coverage = block.size / max(1, len(phrase_tokens))
    if coverage < 0.45:
        # Sliding fuzzy fallback handles short ASR substitutions.
        size = min(len(audio_tokens), len(phrase_tokens))
        candidates = [(ratio(" ".join(phrase_tokens), " ".join(audio_tokens[i:i + size])) / 100, i)
                      for i in range(max(1, len(audio_tokens) - size + 1))]
        score, start_index = max(candidates)
        if score < 0.55:
            return None
        end_index = min(len(words) - 1, start_index + size - 1)
        return float(words[start_index]["start"]), float(words[end_index]["end"]), score
    start_index = block.a
    end_index = min(len(words) - 1, block.a + max(block.size, len(phrase_tokens)) - 1)
    return float(words[start_index]["start"]), float(words[end_index]["end"]), coverage
