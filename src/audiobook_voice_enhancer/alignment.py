from __future__ import annotations

import bisect
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from rapidfuzz.fuzz import ratio


ALIGNMENT_ALGORITHM_VERSION = "unique-7gram-anchors-v1"
ANCHOR_SIZE = 7
MAX_INTERPOLATION_GAP = 350


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return " ".join(re.findall(r"[\w']+", "".join(char for char in decomposed if not unicodedata.combining(char))))


def _book_tokens(book_blocks: list[str]) -> tuple[list[str], list[int], list[int]]:
    tokens: list[str] = []
    token_blocks: list[int] = []
    block_starts: list[int] = []
    for block_id, block in enumerate(book_blocks):
        block_starts.append(len(tokens))
        values = normalize(block).split()
        tokens.extend(values)
        token_blocks.extend([block_id] * len(values))
    return tokens, token_blocks, block_starts


def _audio_tokens(segments: list[dict[str, Any]]) -> tuple[list[str], list[tuple[int, int]]]:
    tokens: list[str] = []
    spans: list[tuple[int, int]] = []
    for segment in segments:
        start = len(tokens)
        tokens.extend(normalize(segment.get("text", "")).split())
        spans.append((start, len(tokens)))
    return tokens, spans


def _unique_ngram_index(tokens: list[str], start: int, size: int) -> dict[tuple[str, ...], int]:
    index: dict[tuple[str, ...], int] = {}
    repeated: set[tuple[str, ...]] = set()
    for position in range(start, len(tokens) - size + 1):
        key = tuple(tokens[position:position + size])
        if key in index:
            repeated.add(key)
        else:
            index[key] = position
    for key in repeated:
        index.pop(key, None)
    return index


def _longest_increasing(matches: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Return the longest chain whose book positions strictly increase."""
    if not matches:
        return []
    tails: list[int] = []
    tail_indices: list[int] = []
    parents = [-1] * len(matches)
    for index, (_, book_position) in enumerate(matches):
        slot = bisect.bisect_left(tails, book_position)
        if slot == len(tails):
            tails.append(book_position)
            tail_indices.append(index)
        else:
            tails[slot] = book_position
            tail_indices[slot] = index
        if slot:
            parents[index] = tail_indices[slot - 1]
    chain: list[tuple[int, int]] = []
    cursor = tail_indices[-1]
    while cursor >= 0:
        chain.append(matches[cursor])
        cursor = parents[cursor]
    return list(reversed(chain))


def _anchor_alignment(book_blocks: list[str], segments: list[dict[str, Any]], initial_cursor: int) -> list[dict[str, Any]]:
    book_tokens, token_blocks, block_starts = _book_tokens(book_blocks)
    audio_tokens, segment_spans = _audio_tokens(segments)
    if len(book_tokens) < ANCHOR_SIZE or len(audio_tokens) < ANCHOR_SIZE:
        return []
    first_book_token = block_starts[min(max(0, initial_cursor), len(block_starts) - 1)]
    book_index = _unique_ngram_index(book_tokens, first_book_token, ANCHOR_SIZE)
    matches = [(audio_position, book_index[key])
               for audio_position in range(len(audio_tokens) - ANCHOR_SIZE + 1)
               if (key := tuple(audio_tokens[audio_position:audio_position + ANCHOR_SIZE])) in book_index]
    anchors = _longest_increasing(matches)
    if len(anchors) < 2:
        return []

    anchor_audio = [item[0] for item in anchors]
    result: list[dict[str, Any]] = []
    for segment_index, segment in enumerate(segments):
        span_start, span_end = segment_spans[segment_index]
        if span_end <= span_start:
            continue
        midpoint = (span_start + span_end - 1) / 2
        right = bisect.bisect_left(anchor_audio, midpoint)
        left = right - 1
        overlapping = bisect.bisect_left(anchor_audio, span_start)
        has_anchor = overlapping < len(anchors) and anchor_audio[overlapping] < span_end
        if has_anchor:
            book_position = anchors[overlapping][1] + max(0, int(midpoint - anchors[overlapping][0]))
            confidence = 0.99
        elif left >= 0 and right < len(anchors):
            audio_left, book_left = anchors[left]
            audio_right, book_right = anchors[right]
            gap = audio_right - audio_left
            if gap <= 0 or gap > MAX_INTERPOLATION_GAP:
                continue
            fraction = (midpoint - audio_left) / gap
            book_position = round(book_left + fraction * (book_right - book_left))
            confidence = 0.96 if gap <= 80 else 0.90
        else:
            # Covers a short sentence at the edge, but deliberately refuses intros,
            # adverts and outros that are absent from the book.
            if right == 0:
                continue
            nearest = anchors[0] if right < len(anchors) else anchors[-1]
            distance = abs(midpoint - nearest[0])
            if distance > 20:
                continue
            book_position = round(nearest[1] + (midpoint - nearest[0]))
            confidence = 0.85
        book_position = min(max(first_book_token, book_position), len(token_blocks) - 1)
        book_id = token_blocks[book_position]
        result.append({"segment_id": segment["id"], "book_paragraph_id": book_id,
                       "audio_start": segment["start"], "audio_end": segment["end"],
                       "alignment_confidence": round(confidence, 4), "book_text": book_blocks[book_id]})
    return result


def _fuzzy_alignment(book_blocks: list[str], segments: list[dict[str, Any]], window: int,
                     initial_cursor: int) -> list[dict[str, Any]]:
    """Safe fallback for tiny inputs that cannot contain two seven-word anchors."""
    normalized_books = [normalize(block) for block in book_blocks]
    cursor = min(max(0, initial_cursor), len(book_blocks) - 1)
    result: list[dict[str, Any]] = []
    for segment in segments:
        needle = normalize(segment.get("text", ""))
        if not needle:
            continue
        lookahead = max(window, 200) if not result and initial_cursor == 0 else max(2, window)
        upper = min(len(book_blocks), cursor + lookahead)
        candidates = [(ratio(needle, normalized_books[book_id]) / 100, book_id)
                      for book_id in range(max(0, cursor - 1), upper)]
        best_score, best_id = max(candidates, default=(0.0, cursor))
        if best_score < 0.45:
            continue
        cursor = best_id
        result.append({"segment_id": segment["id"], "book_paragraph_id": best_id,
                       "audio_start": segment["start"], "audio_end": segment["end"],
                       "alignment_confidence": round(best_score, 4), "book_text": book_blocks[best_id]})
    return result


def align_blocks(book_blocks: list[str], transcript: dict[str, Any], window: int = 40,
                 initial_cursor: int = 0) -> list[dict[str, Any]]:
    """Align ASR to a book using unique exact anchors and monotonic outlier rejection."""
    segments = transcript.get("segments", [])
    if not book_blocks or not segments:
        return []
    anchored = _anchor_alignment(book_blocks, segments, initial_cursor)
    return anchored or _fuzzy_alignment(book_blocks, segments, window, initial_cursor)


def map_phrase_to_words(phrase: str, words: list[dict[str, Any]]) -> tuple[float, float, float] | None:
    phrase_tokens = normalize(phrase).split()
    timed_tokens = [(normalize(word.get("word", "")), word) for word in words]
    timed_tokens = [(token, word) for token, word in timed_tokens if token]
    audio_tokens = [token for token, _ in timed_tokens]
    if not phrase_tokens or not audio_tokens:
        return None
    matcher = SequenceMatcher(None, audio_tokens, phrase_tokens, autojunk=False)
    block = max(matcher.get_matching_blocks(), key=lambda item: item.size)
    coverage = block.size / max(1, len(phrase_tokens))
    if coverage < 0.45:
        size = min(len(audio_tokens), len(phrase_tokens))
        candidates = [(ratio(" ".join(phrase_tokens), " ".join(audio_tokens[i:i + size])) / 100, i)
                      for i in range(max(1, len(audio_tokens) - size + 1))]
        score, start_index = max(candidates)
        if score < 0.55:
            return None
        end_index = min(len(timed_tokens) - 1, start_index + size - 1)
        return float(timed_tokens[start_index][1]["start"]), float(timed_tokens[end_index][1]["end"]), score
    start_index = block.a
    end_index = min(len(timed_tokens) - 1, block.a + max(block.size, len(phrase_tokens)) - 1)
    return (float(timed_tokens[start_index][1]["start"]),
            float(timed_tokens[end_index][1]["end"]), coverage)
