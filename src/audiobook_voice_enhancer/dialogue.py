from __future__ import annotations

import re
from typing import Any

from .alignment import map_phrase_to_words

SPEECH_VERBS = r"disse|perguntou|respondeu|gritou|murmurou|sussurrou|exclamou|retrucou|declarou|said|asked|replied|shouted|whispered|murmured|exclaimed"
NAME = r"[A-ZÀ-Ý][\wÀ-ÿ'-]+(?:\s+(?:(?:d[aeo]s?|e)\s+)?[A-ZÀ-Ý][\wÀ-ÿ'-]+){0,3}"
QUOTE = re.compile(r"[“\"]([^”\"]{2,}?)[”\"]")
DASH = re.compile(r"(?:^|\n)\s*[—–-]\s*([^\n—–]{2,}?)(?=\s+[—–]\s*|$)", re.M)
ATTR_AFTER = re.compile(rf"\b(?i:{SPEECH_VERBS})\s+(?:(?i:a|o|the)\s+)?({NAME})")
ATTR_BEFORE = re.compile(rf"\b({NAME})\s+(?i:{SPEECH_VERBS})\s*:")
UNSAFE_SHORT = re.compile(r"^(?:ah+|oh+|uh+|hm+|ha(?:ha)+|ai+|ei+|suspiro|risos?)[!.…]*$", re.I)


def _canonical(value: str, aliases: dict[str, str]) -> str:
    return aliases.get(" ".join(value.split()).casefold(), value)


def _alias_match(context: str, aliases: dict[str, str], *, before: bool) -> str | None:
    if not aliases:
        return None
    choices = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
    if before:
        pattern = re.compile(rf"\b({choices})\s+(?:{SPEECH_VERBS})\s*:", re.I)
        matches = list(pattern.finditer(context))
        match = matches[-1] if matches else None
    else:
        pattern = re.compile(rf"\b(?:{SPEECH_VERBS})\s+(?:(?:a|o|the)\s+)?({choices})\b", re.I)
        match = pattern.search(context)
    return aliases.get(match.group(1).casefold()) if match else None


def _speaker(context: str, start: int, end: int, aliases: dict[str, str]) -> tuple[str | None, float, str]:
    after = context[end:end + 100]
    before = context[max(0, start - 100):start]
    alias = _alias_match(after, aliases, before=False)
    if alias:
        return alias, 0.98, "atribuição explícita por nome ou alias após a fala"
    match = ATTR_AFTER.search(after)
    if match:
        return _canonical(match.group(1), aliases), 0.98, "atribuição explícita após a fala"
    alias = _alias_match(before, aliases, before=True)
    if alias:
        return alias, 0.98, "atribuição explícita por nome ou alias antes da fala"
    matches = list(ATTR_BEFORE.finditer(before))
    if matches:
        return _canonical(matches[-1].group(1), aliases), 0.98, "atribuição explícita antes da fala"
    return None, 0.0, "falante não atribuído explicitamente"


def detect(transcript: dict[str, Any], alignments: list[dict[str, Any]] | None = None,
           speaker_aliases: dict[str, str] | None = None) -> list[dict[str, Any]]:
    aliases = speaker_aliases or {}
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
            speaker, speaker_score, reason = _speaker(context, match.start(), match.end(), aliases)
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
