from __future__ import annotations

import re
from typing import Any

from .alignment import map_phrase_to_words


DIALOGUE_ALGORITHM_VERSION = "book-context-speaker-engine-v4"
SPEECH_VERBS = (r"disse|perguntou|respondeu|gritou|murmurou|sussurrou|exclamou|retrucou|declarou|"
                r"afirmou|falou|berrou|urrou|rosnou|vociferou|insistiu|interrompeu|interveio|"
                r"comentou|observou|anunciou|acrescentou|continuou|prosseguiu|repetiu|replicou|"
                r"protestou|refutou|concordou|discordou|admitiu|explicou|esclareceu|resmungou|"
                r"gemeu|suspirou|cochichou|balbuciou|ordenou|mandou|pediu|implorou|advertiu|"
                r"ameaçou|ironizou|zombou|riu|sorriu|bocejou|explodiu|disparou|sentenciou|"
                r"intrometeu|apoiou|adicionou|conclamou|assegurou|garantiu|confirmou|"
                r"said|asked|replied|shouted|whispered|murmured|exclaimed")
SPEECH_VERB = rf"(?:{SPEECH_VERBS})(?:-(?:lhe|lhes|[oa]s?|se|me))?"
NAME = r"[A-ZÀ-Ý][\wÀ-ÿ'-]+(?:\s+(?:(?:d[aeo]s?|e)\s+)?[A-ZÀ-Ý][\wÀ-ÿ'-]+){0,3}"
QUOTE = re.compile(r"[“\"]([^”\"]{2,}?)[”\"]")
DASH = re.compile(r"(?:^|\n)\s*[—–-]\s*([^\n—–]{2,}?)(?=\s+[—–]\s*|$)", re.M)
ATTR_AFTER = re.compile(rf"\b(?i:{SPEECH_VERB})\s+(?:(?i:a|o|the)\s+)?({NAME})")
ATTR_BEFORE = re.compile(rf"\b({NAME})\s+(?i:{SPEECH_VERB})\s*:")
UNSAFE_SHORT = re.compile(r"^(?:ah+|oh+|uh+|hm+|ha(?:ha)+|ai+|ei+|suspiro|risos?)[!.…]*$", re.I)
NARRATION_VERBS = (r"disse|perguntou|respondeu|gritou|murmurou|sussurrou|exclamou|retrucou|declarou|"
                   r"repetiu|continuou|acrescentou|prosseguiu|pensou|olhou|ouvira|ouviu|tremeu|"
                   r"sorriu|assentiu|levantou|baixou|virou|afastou|aproximou")
SUBJECT_ACTIONS = (r"ajeitou|apertou|assentiu|baixou|coçou|colocou|cruzou|deu|endireitou|ergueu|"
                   r"encolheu|fitou|inclinou|levantou|olhou|piscou|recuou|sacudiu|sorriu|tremeu|"
                   r"virou|voltou")
ROLE = (r"artesã|artesão|artista|anão|anã|bardo|bruxo|bruxa|cavaleiro|cavaleira|chanceler|"
        r"druida|elfo|elfa|feiticeiro|feiticeira|guerreiro|guerreira|mago|maga|poeta|"
        r"sacerdote|sacerdotisa|trovador|trovadora|gnomo|gnoma")
NON_NAMES = {"a", "as", "e", "ele", "ela", "em", "eu", "o", "os", "the", "um", "uma", "você", "vocês"}


def _canonical(value: str, aliases: dict[str, str]) -> str:
    return aliases.get(" ".join(value.split()).casefold(), value)


def _proper_names(value: str) -> list[str]:
    names = [" ".join(match.group(0).split()).strip(" ,.;:!?") for match in re.finditer(NAME, value)]
    return [name for name in names if len(name) > 1 and name.casefold() not in NON_NAMES]


def _book_aliases(book_blocks: list[str] | None, configured: dict[str, str]) -> dict[str, str]:
    """Discover explicitly named speakers before the first analysis pass."""
    result = dict(configured)
    discovered: list[str] = []
    for block in book_blocks or []:
        for speech in DASH.finditer(block):
            attribution = block[speech.end():speech.end() + 160]
            verb = re.search(rf"\b{SPEECH_VERB}\b", attribution, re.I)
            if not verb or verb.start() > 50:
                continue
            clause = re.split(r"[—–.!?]", attribution[verb.end():], maxsplit=1)[0]
            candidates = []
            for candidate in re.finditer(NAME, clause):
                prefix = clause[:candidate.start()].rstrip().casefold()
                preceding = re.search(r"([a-zà-ÿ]+)\s*$", prefix)
                if preceding and preceding.group(1) in {"a", "ao", "à", "com", "da", "das", "de", "do", "dos", "para"}:
                    continue
                candidates.extend(_proper_names(candidate.group(0)))
            if candidates:
                discovered.append(candidates[-1])
        for introduction in re.finditer(rf"\b(?i:eu)\s*,\s*({NAME})", block):
            candidates = _proper_names(introduction.group(1))
            if candidates:
                discovered.append(candidates[0])
    configured_first: dict[str, set[str]] = {}
    for character in set(configured.values()):
        configured_first.setdefault(character.split()[0].casefold(), set()).add(character)
    discovered_first: dict[str, set[str]] = {}
    for name in discovered:
        discovered_first.setdefault(name.split()[0].casefold(), set()).add(name)
    for first, variants in discovered_first.items():
        configured_matches = configured_first.get(first, set())
        canonical = (next(iter(configured_matches)) if len(configured_matches) == 1
                     else max(variants, key=lambda value: (len(value.split()), len(value))))
        for name in variants:
            result.setdefault(name.casefold(), canonical)
    first_names: dict[str, set[str]] = {}
    for canonical in set(result.values()):
        first_names.setdefault(canonical.split()[0].casefold(), set()).add(canonical)
    for first, owners in first_names.items():
        if len(owners) == 1:
            result.setdefault(first, next(iter(owners)))
    return result


def _alias_match(context: str, aliases: dict[str, str], *, before: bool) -> str | None:
    if not aliases:
        return None
    choices = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
    if before:
        pattern = re.compile(rf"\b({choices})\s+(?:{SPEECH_VERB})\s*:", re.I)
        matches = list(pattern.finditer(context))
        match = matches[-1] if matches else None
    else:
        verb = re.search(rf"\b(?:{SPEECH_VERB})\b", context, re.I)
        if not verb:
            return None
        clause = re.split(r"[—–.!?]", context[verb.end():verb.end() + 140], maxsplit=1)[0]
        match = None
        for candidate in re.finditer(rf"\b({choices})\b", clause, re.I):
            prefix = clause[:candidate.start()].rstrip().casefold()
            preceding = re.search(r"([a-zà-ÿ]+)\s*$", prefix)
            if preceding and preceding.group(1) in {"a", "ao", "à", "com", "da", "das", "de", "do", "dos", "para"}:
                continue
            match = candidate
            break
    return aliases.get(match.group(1).casefold()) if match else None


def _speaker(context: str, start: int, end: int, aliases: dict[str, str]) -> tuple[str | None, float, str]:
    after = context[end:end + 100]
    narrative_after = context[end:end + 500]
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
    if aliases:
        choices = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
        acting_subject = re.match(rf"\s*(?:[—–-]\s*)?({choices})\s+(?:{SUBJECT_ACTIONS})(?:-se)?\b",
                                  narrative_after, re.I)
        if acting_subject:
            return aliases[acting_subject.group(1).casefold()], 0.96, "personagem nomeado como sujeito após a fala"
        narrative = re.search(rf"\bquem\b.{{0,180}}\b(?:dizia|falava)\b.{{0,80}}\bera\s+({choices})\b",
                              narrative_after, re.I)
        if narrative:
            return aliases[narrative.group(1).casefold()], 0.96, "atribuição explícita na narração após a fala"
        self_identity = _self_identified_speaker(context, aliases)
        if self_identity:
            return self_identity, 0.96, "autoidentificação explícita no mesmo parágrafo"
    return None, 0.0, "falante não atribuído explicitamente"


def _addressed_characters(text: str, aliases: dict[str, str]) -> set[str]:
    """Find known characters used as vocatives, not ordinary mentions."""
    found: set[str] = set()
    for alias, character in aliases.items():
        escaped = re.escape(alias)
        if (re.search(rf"^\s*{escaped}(?=\s*(?:[,.!?…:]|$))", text, re.I)
                or re.search(rf",\s*{escaped}(?=\s*(?:[,.!?…:]|$))", text, re.I)):
            found.add(character)
    return found


def _self_identified_speaker(text: str, aliases: dict[str, str]) -> str | None:
    if not aliases:
        return None
    choices = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
    match = re.search(rf"\b(?:eu\s*,\s*|me\s+chamo\s+|sou\s+(?:a|o)?\s*)({choices})\b", text, re.I)
    return aliases.get(match.group(1).casefold()) if match else None


def _trim_dash_narration(text: str, aliases: dict[str, str]) -> tuple[str, int]:
    """Split an unclosed dash speech when a named subject clearly starts narration."""
    if not aliases:
        return text, len(text)
    choices = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
    boundary = re.search(rf"(?<=[.!?…])\s+(?=(?:{choices})\s+(?:{NARRATION_VERBS})\b)", text, re.I)
    if not boundary:
        return text, len(text)
    return text[:boundary.start()].rstrip(), boundary.start()


def _scene_numbers(book_blocks: list[str] | None) -> dict[int, int]:
    scene = 0
    result: dict[int, int] = {}
    for index, block in enumerate(book_blocks or []):
        cleaned = block.strip()
        if cleaned in {"—", "–", "-", "*", "***", "•"} or re.match(r"^(?:capítulo|chapter)\b", cleaned, re.I):
            scene += 1
        result[index] = scene
    return result


def _scene_role_owners(book_blocks: list[str] | None, aliases: dict[str, str],
                       scenes: dict[int, int]) -> dict[int, dict[str, str]]:
    candidates: dict[int, dict[str, set[str]]] = {}
    if not aliases:
        return {}
    choices = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
    for index, block in enumerate(book_blocks or []):
        scene = scenes.get(index, 0)
        found: list[tuple[str, str]] = []
        for match in re.finditer(rf"\b(?:o|a|um|uma)\s+(?:[a-zà-ÿ'-]+\s+){{0,3}}?({ROLE})\s+({choices})\b",
                                 block, re.I):
            found.append((match.group(1).casefold(), aliases[match.group(2).casefold()]))
        identity = _self_identified_speaker(block, aliases)
        if identity:
            # In introductions such as "disse uma esbelta guerreira ... eu, Rayla",
            # the role before the self-identification belongs to that character.
            prefix = block[:block.casefold().find(identity.split()[0].casefold())]
            role_matches = list(re.finditer(rf"\b(?:o|a|um|uma)\s+(?:[a-zà-ÿ'-]+\s+){{0,3}}?({ROLE})\b",
                                            prefix, re.I))
            if role_matches:
                found.append((role_matches[-1].group(1).casefold(), identity))
        for role, character in found:
            candidates.setdefault(scene, {}).setdefault(role, set()).add(character)
    return {scene: {role: next(iter(owners)) for role, owners in roles.items() if len(owners) == 1}
            for scene, roles in candidates.items()}


def _attribution_role(context: str, speech_end: int) -> str | None:
    after = context[speech_end:speech_end + 180]
    verb = re.search(rf"\b{SPEECH_VERB}\b", after, re.I)
    if not verb or verb.start() > 60:
        return None
    clause = re.split(r"[—–,.!?]", after[verb.end():], maxsplit=1)[0]
    roles = list(re.finditer(rf"\b({ROLE})\b", clause, re.I))
    return roles[-1].group(1).casefold() if roles else None


def _conversation_runs(dialogues: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    runs: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    spoken_turns = [item for item in dialogues if item.get("dialogue_style") == "dash"]
    for dialogue in sorted(spoken_turns, key=lambda item: float(item["start"])):
        if current:
            paragraph_gap = int(dialogue.get("book_paragraph_id", -1000)) - int(current[-1].get("book_paragraph_id", 1000))
            audio_gap = float(dialogue["start"]) - float(current[-1]["end"])
            scene_changed = dialogue.get("scene_id") != current[-1].get("scene_id")
            if scene_changed or paragraph_gap < 0 or paragraph_gap > 5 or audio_gap > 75:
                runs.append(current)
                current = []
        current.append(dialogue)
    if current:
        runs.append(current)
    return runs


def _infer_conversation_turns(dialogues: list[dict[str, Any]], aliases: dict[str, str]) -> None:
    """Infer alternating two-person book dialogue only when vocatives identify both participants."""
    for run in _conversation_runs(dialogues):
        addressed = [_addressed_characters(item["text"], aliases) for item in run]
        participants = set().union(*addressed) if addressed else set()
        participants.update(item["speaker"] for item in run if item.get("speaker"))
        if len(run) < 3 or len(participants) != 2:
            continue
        pair = tuple(sorted(participants))

        # A vocative names the listener, so in a verified two-person exchange the
        # other participant is the speaker. These are strong anchors.
        for item, listeners in zip(run, addressed):
            if item.get("speaker") or len(listeners) != 1:
                continue
            listener = next(iter(listeners))
            if listener in participants:
                item["speaker"] = pair[1] if listener == pair[0] else pair[0]
                item["speaker_confidence"] = 0.93
                item["reason"] = "inferência por vocativo em conversa entre dois personagens"

        previous_speaker: str | None = None
        for item in run:
            if item.get("speaker") in participants:
                previous_speaker = item["speaker"]
                continue
            if not previous_speaker:
                continue
            if item.get("_continues_previous"):
                item["speaker"] = previous_speaker
                item["speaker_confidence"] = 0.9
                item["reason"] = "inferência de continuação explícita da fala anterior"
            else:
                item["speaker"] = pair[1] if previous_speaker == pair[0] else pair[0]
                item["speaker_confidence"] = 0.88
                item["reason"] = "inferência de alternância em conversa entre dois personagens"
            previous_speaker = item["speaker"]


def detect(transcript: dict[str, Any], alignments: list[dict[str, Any]] | None = None,
           speaker_aliases: dict[str, str] | None = None,
           book_blocks: list[str] | None = None) -> list[dict[str, Any]]:
    aliases = _book_aliases(book_blocks, speaker_aliases or {})
    scenes = _scene_numbers(book_blocks)
    role_owners = _scene_role_owners(book_blocks, aliases, scenes)
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
    for _, context, grouped_segments, alignment_score, is_aligned, unit_id in units:
        dash_matches = list(DASH.finditer(context))
        quote_matches = [quote for quote in QUOTE.finditer(context)
                         if not any(dash.start() <= quote.start() and quote.end() <= dash.end()
                                    for dash in dash_matches)]
        matches = sorted(quote_matches + dash_matches, key=lambda match: match.start())
        if not matches and not is_aligned:
            attribution = ATTR_BEFORE.search(context)
            if attribution:
                trailing = context[attribution.end():].strip(" :—–-")
                if trailing:
                    matches = [SyntheticMatch(trailing, attribution.end(), len(context))]
        combined_words = sorted((word for segment in grouped_segments for word in segment.get("words", [])),
                                key=lambda word: float(word.get("start", 0)))
        for local_index, match in enumerate(matches):
            raw_text = match.group(1)
            speech_end = match.end()
            if getattr(match, "re", None) is DASH:
                raw_text, relative_end = _trim_dash_narration(raw_text, aliases)
                speech_end = match.start(1) + relative_end
            text = raw_text.strip(" \t\r\n—–-\"")
            mapped = map_phrase_to_words(text, combined_words)
            if not mapped:
                continue
            start, end, word_score = mapped
            owner = next((segment for segment in grouped_segments
                          if float(segment["start"]) <= start <= float(segment["end"])), grouped_segments[0])
            speaker, speaker_score, reason = _speaker(context, match.start(), speech_end, aliases)
            attribution_role = _attribution_role(context, speech_end)
            role_speaker = role_owners.get(scenes.get(unit_id, 0), {}).get(attribution_role or "")
            if not speaker and role_speaker:
                speaker, speaker_score, reason = role_speaker, 0.94, "memória de papel do personagem nesta cena"
            introduced = _self_identified_speaker(text, aliases)
            if not speaker and introduced:
                speaker, speaker_score, reason = introduced, 0.98, "autoidentificação explícita dentro da fala"
            continuation = bool(re.match(r"\s*(?:[,.;:]|[—–-])?\s*(?:repetiu|continuou|acrescentou|prosseguiu)\b",
                                         context[speech_end:], re.I))
            confidence = min(alignment_score if is_aligned else word_score, word_score)
            dialogues.append({"id": f"{unit_id}-{local_index}", "segment_id": owner["id"], "text": text,
                              "start": start, "end": end, "speaker": speaker,
                              "speaker_confidence": round(speaker_score, 4), "alignment_confidence": round(confidence, 4),
                              "source": "book" if is_aligned else "transcript", "reason": reason,
                              "book_paragraph_id": unit_id if is_aligned else None,
                              "book_context": book_blocks[max(0, unit_id - 2):unit_id + 3] if is_aligned and book_blocks else [context],
                              "scene_id": scenes.get(unit_id, 0) if is_aligned else -1,
                              "attribution_role": attribution_role,
                              "dialogue_style": "dash" if getattr(match, "re", None) is DASH else "quote",
                              "_continues_previous": continuation,
                              "unsafe_short": bool(UNSAFE_SHORT.fullmatch(text.strip()))})
    _infer_conversation_turns(dialogues, aliases)
    for dialogue in dialogues:
        dialogue.pop("_continues_previous", None)
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
