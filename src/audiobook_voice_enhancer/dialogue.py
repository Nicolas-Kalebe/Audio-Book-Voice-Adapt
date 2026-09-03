from __future__ import annotations

import re
from typing import Any

from .alignment import map_phrase_to_words


DIALOGUE_ALGORITHM_VERSION = "paragraph-groups-v1"
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
    segments = transcript.get("segments", [])
    segment_by_id = {item["id"]: item for item in segments}
    aligned_ids = {item["segment_id"] for item in (alignments or [])}
    paragraph_groups: dict[int, list[dict[str, Any]]] = {}
    for item in alignments or []:
        paragraph_groups.setdefault(int(item["book_paragraph_id"]), []).append(item)

    # One EPUB paragraph usually spans several Whisper segments. Treat all of
    # their timed words as one unit so a long speech is not cut at ASR boundaries.
    units: list[tuple[float, str, list[dict[str, Any]], float, bool, int]] = []
    for paragraph_id, group in paragraph_groups.items():
        group.sort(key=lambda item: float(item["audio_start"]))
        grouped_segments = [segment_by_id[item["segment_id"]] for item in group
                            if item["segment_id"] in segment_by_id]
        if not grouped_segments:
            continue
        confidence = min(float(item["alignment_confidence"]) for item in group)
        units.append((float(group[0]["audio_start"]), group[0]["book_text"], grouped_segments,
                      confidence, True, paragraph_id))
    for segment in segments:
        if segment["id"] not in aligned_ids:
            units.append((float(segment["start"]), segment.get("text", ""), [segment], 0.0, False,
                          int(segment["id"])))
    units.sort(key=lambda item: item[0])

    dialogues: list[dict[str, Any]] = []
    last_explicit: str | None = None
    previous_speaker: str | None = None
    for _, context, grouped_segments, alignment_score, is_aligned, unit_id in units:
        matches = sorted(list(QUOTE.finditer(context)) + list(DASH.finditer(context)), key=lambda match: match.start())
        if not matches and not is_aligned:
            attribution = ATTR_BEFORE.search(context)
            if attribution:
                trailing = context[attribution.end():].strip(" :—–-")
                if trailing:
                    matches = [SyntheticMatch(trailing, attribution.end(), len(context))]
        combined_words = sorted((word for segment in grouped_segments for word in segment.get("words", [])),
                                key=lambda word: float(word.get("start", 0)))
        for local_index, match in enumerate(matches):
            text = match.group(1).strip(" \t\r\n—–-\"")
            mapped = map_phrase_to_words(text, combined_words)
            if not mapped:
                continue
            start, end, word_score = mapped
            owner = next((segment for segment in grouped_segments
                          if float(segment["start"]) <= start <= float(segment["end"])), grouped_segments[0])
            speaker, speaker_score, reason = _speaker(context, match.start(), match.end(), aliases)
            if speaker:
                last_explicit, previous_speaker = speaker, speaker
            elif last_explicit and previous_speaker and len(matches) == 1:
                speaker, speaker_score, reason = last_explicit, 0.72, "inferência de continuidade conversacional"
            confidence = min(alignment_score if is_aligned else word_score, word_score)
            dialogues.append({"id": f"{unit_id}-{local_index}", "segment_id": owner["id"], "text": text,
                              "start": start, "end": end, "speaker": speaker,
                              "speaker_confidence": round(speaker_score, 4), "alignment_confidence": round(confidence, 4),
                              "source": "book" if is_aligned else "transcript", "reason": reason,
                              "unsafe_short": bool(UNSAFE_SHORT.fullmatch(text.strip()))})
    return dialogues


class SyntheticMatch:
    def __init__(self, value: str, start: int, end: int):
        self.value, self._start, self._end = value, start, end

    def group(self, _: int) -> str:
        return self.value

    def start(self) -> int:
        return self._start

    def end(self) -> int:
        return self._end
