from __future__ import annotations

import re
from typing import Any

from .alignment import map_phrase_to_words

SPEECH_VERBS = r"disse|perguntou|respondeu|gritou|murmurou|sussurrou|exclamou|retrucou|declarou|said|asked|replied|shouted|whispered|murmured|exclaimed"
QUOTE = re.compile(r"[“\"]([^”\"]{2,}?)[”\"]")
DASH = re.compile(r"(?:^|\n)\s*[—–-]\s*([^\n—–]{2,}?)(?=\s+[—–]\s*|$)", re.M)
ATTR_AFTER = re.compile(rf"\b(?:{SPEECH_VERBS})\s+(?:a|o|the\s+)?([A-ZÀ-Ý][\wÀ-ÿ'-]+)", re.I)
ATTR_BEFORE = re.compile(rf"\b([A-ZÀ-Ý][\wÀ-ÿ'-]+)\s+(?:{SPEECH_VERBS})\s*:", re.I)
UNSAFE_SHORT = re.compile(r"^(?:ah+|oh+|uh+|hm+|ha(?:ha)+|ai+|ei+|suspiro|risos?)[!.…]*$", re.I)


def _speaker(context: str, start: int, end: int) -> tuple[str | None, float, str]:
    after = context[end:end + 100]
    before = context[max(0, start - 100):start]
    match = ATTR_AFTER.search(after)
    if match:
        return match.group(1), 0.98, "atribuição explícita após a fala"
    matches = list(ATTR_BEFORE.finditer(before))
    if matches:
        return matches[-1].group(1), 0.98, "atribuição explícita antes da fala"
    return None, 0.0, "falante não atribuído explicitamente"


def detect(transcript: dict[str, Any], alignments: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    by_segment = {item["segment_id"]: item for item in (alignments or [])}
    dialogues: list[dict[str, Any]] = []
    last_explicit: str | None = None
    previous_speaker: str | None = None
    for segment in transcript.get("segments", []):
        aligned = by_segment.get(segment["id"])
        context = aligned["book_text"] if aligned else segment["text"]
        matches = sorted(list(QUOTE.finditer(context)) + list(DASH.finditer(context)), key=lambda match: match.start())
        # Transcript punctuation often loses quotes. Only infer a clause when a speech verb gives an explicit anchor.
        if not matches and not aligned:
            attribution = ATTR_BEFORE.search(context)
            if attribution:
                trailing = context[attribution.end():].strip(" :—–-")
                if trailing:
                    matches = [SyntheticMatch(trailing, attribution.end(), len(context))]
        for local_index, match in enumerate(matches):
            text = match.group(1).strip(" \t\r\n—–-\"")
            mapped = map_phrase_to_words(text, segment.get("words", []))
            if not mapped:
                continue
            start, end, word_score = mapped
            speaker, speaker_score, reason = _speaker(context, match.start(), match.end())
            if speaker:
                last_explicit, previous_speaker = speaker, speaker
            elif last_explicit and previous_speaker and len(matches) == 1:
                # Conservative alternating-turn inference; deliberately below default threshold.
                speaker, speaker_score, reason = last_explicit, 0.72, "inferência de continuidade conversacional"
            confidence = min(float(aligned["alignment_confidence"]) if aligned else word_score, word_score)
            dialogues.append({"id": f"{segment['id']}-{local_index}", "segment_id": segment["id"], "text": text,
                              "start": start, "end": end, "speaker": speaker,
                              "speaker_confidence": round(speaker_score, 4), "alignment_confidence": round(confidence, 4),
                              "source": "book" if aligned else "transcript", "reason": reason,
                              "unsafe_short": bool(UNSAFE_SHORT.fullmatch(text.strip()))})
    return dialogues


class SyntheticMatch:
    def __init__(self, value: str, start: int, end: int):
        self.value, self._start, self._end = value, start, end
    def group(self, _: int) -> str: return self.value
    def start(self) -> int: return self._start
    def end(self) -> int: return self._end
