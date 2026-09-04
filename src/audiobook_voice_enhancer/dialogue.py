from __future__ import annotations

import re
from typing import Any

from .alignment import map_phrase_to_words


DIALOGUE_ALGORITHM_VERSION = "book-context-speaker-engine-v25-stable-roles"
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
DASH_MARK = re.compile(r"(?<!\w)[—–-]")
ATTR_AFTER = re.compile(rf"\b(?i:{SPEECH_VERB})\s+(?:(?i:a|o|the)\s+)?({NAME})")
ATTR_BEFORE = re.compile(rf"\b({NAME})\s+(?i:{SPEECH_VERB})\s*:")
UNSAFE_SHORT = re.compile(r"^(?:ah+|oh+|uh+|hm+|ha(?:ha)+|ai+|ei+|suspiro|risos?)[!.…]*$", re.I)
NARRATION_VERBS = (r"disse|perguntou|respondeu|gritou|murmurou|sussurrou|exclamou|retrucou|declarou|"
                   r"repetiu|continuou|acrescentou|prosseguiu|pensou|olhou|ouvira|ouviu|tremeu|"
                   r"sorriu|assentiu|levantou|baixou|virou|afastou|aproximou|fixou")
SUBJECT_ACTIONS = (r"ajeitou|apertou|apertaram|apertava|assentiu|baixou|coçou|colocou|cruzou|deu|endireitou|ergueu|"
                   r"encolheu|fitou|inclinou|levantou|olhou|piscou|recuou|sacudiu|sorriu|tremeu|"
                   r"virou|voltou")
ROLE = (r"artesã|artesão|artista|anão|anã|bardo|bruxo|bruxa|cavaleiro|cavaleira|chanceler|"
        r"druida|elfo|elfa|feiticeiro|feiticeira|guerreiro|guerreira|mago|maga|poeta|"
        r"sacerdote|sacerdotisas?|trovador|trovadora|gnomo|gnoma|taberneiro|taberneira|"
        r"albergueiro|albergueira|filhas?")
ROLE_SPEECH_VERB = rf"(?:{SPEECH_VERB}|piou|piaram|latiu|apoiaram|indagou)"
NON_NAMES = {"a", "as", "e", "ele", "ela", "em", "eu", "o", "os", "the", "um", "uma", "você", "vocês"}


def _is_possessed_name(prefix: str) -> bool:
    return bool(re.search(r"\b(?:de|do|da|dos|das)\s+(?:[a-zà-ÿ'-]+\s+){0,3}[a-zà-ÿ'-]+\s*$",
                          prefix.casefold()))


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
                if _is_possessed_name(prefix):
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


def book_character_names(book_blocks: list[str] | None, configured: dict[str, str]) -> set[str]:
    """Names explicitly supported by the book or the user's configuration."""
    return set(_book_aliases(book_blocks, configured).values())


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
            if _is_possessed_name(prefix):
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
        reacting_to_other = bool(acting_subject and re.match(
            r"\s+(?:assustad[oa]\s+)?(?:para|em dire[cç][aã]o a)\s+(?:ele|ela|o|a)\b",
            narrative_after[acting_subject.end():], re.I,
        ))
        if acting_subject and not reacting_to_other:
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
        at_start = re.search(rf"^\s*{escaped}(?=\s*(?:[,.!?…:]|$))", text, re.I)
        internal = re.search(rf",\s*{escaped}(?=\s*(?:[,.!?…:]|$))", text, re.I)
        # ``Eu, Rayla, ...`` is a self-introduction, not Rayla being addressed.
        # The old rule poisoned the following reply and then an entire alternating run.
        self_introduction = bool(internal and re.search(r"\beu\s*$", text[:internal.start()], re.I))
        if at_start or (internal and not self_introduction):
            found.add(character)
    return found


def _addressed_roles(text: str) -> set[str]:
    """Return occupational addressees without adding common nouns as name aliases."""
    return {match.group(1).casefold().capitalize()
            for match in re.finditer(rf"\b(?i:senhor|senhora)\s+({ROLE})\b", text)}


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


def _dash_speech_fragments(text: str) -> list["TextMatch"]:
    """Return every spoken fragment from one dash-dialogue paragraph.

    Portuguese literary dialogue alternates dash-delimited speech and attribution:
    ``— speech — said X. — continued speech``.  A paragraph is one speaker turn,
    but each spoken fragment needs its own audio range so the narrator attribution
    between them is never voice-converted.
    """
    marks = list(DASH_MARK.finditer(text))
    if not marks or text[:marks[0].start()].strip():
        return []
    fragments: list[TextMatch] = []
    # Text after marks 0, 2, 4... is speech; text after marks 1, 3, 5... is narration.
    for mark_index in range(0, len(marks), 2):
        start = marks[mark_index].end()
        end = marks[mark_index + 1].start() if mark_index + 1 < len(marks) else len(text)
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end - start >= 2:
            fragments.append(TextMatch(text[start:end], start, end, style="dash",
                                       continuation=mark_index > 0))
    return fragments


def _continued_dash_turn(book_blocks: list[str] | None, paragraph: int) -> int | None:
    """Detect an EPUB paragraph break in the middle of an unfinished dash turn."""
    if not book_blocks or paragraph <= 0 or paragraph >= len(book_blocks):
        return None
    current = book_blocks[paragraph].strip()
    previous = book_blocks[paragraph - 1].rstrip()
    if not current or _dash_speech_fragments(current) or not _dash_speech_fragments(previous):
        return None
    if previous.endswith((".", "!", "?", "…", '”', '"')):
        return None
    return paragraph - 1


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
    # Empty value preserves known ambiguity, preventing creation of one synthetic
    # character for several named people sharing the same occupation.
    return {scene: {role: next(iter(owners)) if len(owners) == 1 else ""
                    for role, owners in roles.items()}
            for scene, roles in candidates.items()}


def _attribution_role(context: str, speech_end: int) -> str | None:
    after = context[speech_end:speech_end + 180]
    verb = re.search(rf"\b{ROLE_SPEECH_VERB}\b", after, re.I)
    if not verb or verb.start() > 60:
        return None
    clause = re.split(r"[—–,.!?]", after[verb.end():], maxsplit=1)[0]
    roles = []
    for candidate in re.finditer(rf"\b({ROLE})\b", clause, re.I):
        preceding = re.search(r"([a-zà-ÿ]+)\s*$", clause[:candidate.start()], re.I)
        if preceding and preceding.group(1).casefold() in {"de", "do", "da", "dos", "das"}:
            continue
        roles.append(candidate)
    return roles[-1].group(1).casefold() if roles else None


def _anonymous_role_label(context: str, speech_end: int, role: str | None) -> str | None:
    """Build a readable identity from an explicit unnamed attribution."""
    if not role:
        return None
    after = context[speech_end:speech_end + 180]
    verb = re.search(rf"\b{ROLE_SPEECH_VERB}\b", after, re.I)
    if not verb or verb.start() > 60:
        return None
    clause = re.split(r"[—–,.!?]", after[verb.end():], maxsplit=1)[0]
    match = re.search(rf"\b{re.escape(role)}\b", clause, re.I)
    if not match:
        return None
    label = role.capitalize()
    suffix = clause[match.end():].strip()
    relation = re.match(r"((?:de|do|da|dos|das)\s+[a-zà-ÿ'-]+(?:\s+[A-ZÀ-Ý][\wÀ-ÿ'-]+)?)", suffix)
    if relation and not re.match(r"(?:de|do|da|dos|das)\s+(?:cima|baixo|alto)\b", relation.group(1), re.I):
        return label + " " + relation.group(1)
    suffix_match = re.match(r"([a-zà-ÿ'-]+)", suffix, re.I)
    if (suffix_match and not suffix_match.group(1).casefold().endswith("mente")
            and suffix_match.group(1).casefold() not in {
        "com", "de", "do", "da", "dos", "das", "que", "vestido", "vestida", "sentado", "sentada",
    }):
        label += " " + suffix_match.group(1).casefold()
    else:
        prefix = clause[:match.start()].strip()
        words = re.findall(r"[a-zà-ÿ'-]+", prefix, re.I)
        ignored = {"o", "a", "um", "uma", "os", "as", "e", "com", "voz", "muito", "repentinamente"}
        modifiers = [word.casefold() for word in words if word.casefold() not in ignored]
        if modifiers and not modifiers[-1].endswith("mente"):
            label += " " + modifiers[-1]
    return label if " " in label else None


def _conversation_runs(dialogues: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    runs: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    spoken_turns = [item for item in turn_representatives(dialogues)
                    if item.get("dialogue_style") == "dash"]
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
    """Fill only alternating intervals that agree with reliable anchors on both sides.

    Literary dialogue is not guaranteed to alternate: a character may speak twice,
    narration may interrupt them, or a third person may enter.  Consequently an
    anchor on just the left is insufficient.  We accept an interval only when its
    right anchor independently confirms the same parity.
    """
    for run in _conversation_runs(dialogues):
        addressed = [_addressed_characters(item["text"], aliases) | _addressed_roles(item["text"])
                     for item in run]
        participants = {item["speaker"] for item in run
                        if item.get("speaker") and float(item.get("speaker_confidence", 0)) >= .92}
        # Anchored speakers define the cast more reliably than names at the start
        # of a sentence: ``Rience. Ele é feiticeiro?`` names the topic, not a listener.
        if len(participants) < 2:
            participants.update(set().union(*addressed) if addressed else set())
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

        anchors = [(index, item["speaker"]) for index, item in enumerate(run)
                   if item.get("speaker") in participants
                   and float(item.get("speaker_confidence", 0)) >= .92]
        for (left_index, left_speaker), (right_index, right_speaker) in zip(anchors, anchors[1:]):
            if right_index - left_index <= 1:
                continue
            expected_right = (left_speaker if (right_index - left_index) % 2 == 0
                              else pair[1] if left_speaker == pair[0] else pair[0])
            if expected_right != right_speaker:
                continue
            interval_listeners = set().union(*addressed[left_index:right_index + 1])
            if interval_listeners - participants:
                continue
            speaker = left_speaker
            for item in run[left_index + 1:right_index]:
                speaker = pair[1] if speaker == pair[0] else pair[0]
                if item.get("speaker"):
                    continue
                item["speaker"] = speaker
                item["speaker_confidence"] = 0.9
                item["reason"] = "alternância confirmada por âncoras textuais nos dois lados"


def _infer_recent_vocative_turns(dialogues: list[dict[str, Any]], aliases: dict[str, str]) -> None:
    """Resolve a vocative from the two recent anchored speakers, even inside a larger scene."""
    ordered = sorted((item for item in turn_representatives(dialogues)
                      if item.get("dialogue_style") == "dash"),
                     key=lambda item: float(item["start"]))
    for index, item in enumerate(ordered):
        if item.get("speaker"):
            continue
        listeners = _addressed_characters(item.get("text", ""), aliases)
        if len(listeners) != 1:
            continue
        listener = next(iter(listeners))
        paragraph = int(item.get("book_paragraph_id", -1000))
        recent: list[str] = []
        for previous in reversed(ordered[max(0, index - 8):index]):
            if previous.get("scene_id") != item.get("scene_id"):
                break
            previous_paragraph = int(previous.get("book_paragraph_id", -1000))
            if paragraph - previous_paragraph > 6:
                break
            speaker = previous.get("speaker")
            if speaker and speaker not in recent:
                recent.append(speaker)
            if len(recent) == 2:
                break
        if len(recent) == 2 and recent[0] == listener:
            item["speaker"] = recent[1]
            item["speaker_confidence"] = 0.93
            item["reason"] = "inferência por vocativo e dois falantes ancorados no trecho recente"


def _infer_addressed_replies(dialogues: list[dict[str, Any]], aliases: dict[str, str],
                             book_blocks: list[str] | None = None) -> None:
    """A direct reply normally belongs to the character addressed in the preceding turn."""
    ordered = sorted((item for item in turn_representatives(dialogues)
                      if item.get("dialogue_style") == "dash"),
                     key=lambda item: float(item["start"]))
    for current, following in zip(ordered, ordered[1:]):
        if following.get("speaker") or current.get("scene_id") != following.get("scene_id"):
            continue
        paragraph_gap = int(following.get("book_paragraph_id", -1000)) - int(current.get("book_paragraph_id", 1000))
        if paragraph_gap != 1:
            continue
        paragraph = int(current.get("book_paragraph_id", -1))
        source = (book_blocks[paragraph] if book_blocks and 0 <= paragraph < len(book_blocks)
                  else current.get("text", ""))
        if not current.get("speaker") and "?" not in source:
            continue
        listeners = _addressed_characters(source, aliases)
        if len(listeners) == 1:
            following["speaker"] = next(iter(listeners))
            following["speaker_confidence"] = 0.95
            following["reason"] = "resposta direta ao personagem chamado na fala anterior"


def _infer_mutual_vocatives(dialogues: list[dict[str, Any]], aliases: dict[str, str],
                            book_blocks: list[str] | None = None) -> None:
    """Two adjacent turns addressing each other identify both speakers."""
    ordered = sorted((item for item in turn_representatives(dialogues)
                      if item.get("dialogue_style") == "dash"),
                     key=lambda item: float(item["start"]))
    for current, following in zip(ordered, ordered[1:]):
        if current.get("scene_id") != following.get("scene_id"):
            continue
        if int(following.get("book_paragraph_id", -1000)) - int(current.get("book_paragraph_id", 1000)) != 1:
            continue
        sources = []
        for item in (current, following):
            paragraph = int(item.get("book_paragraph_id", -1))
            sources.append(book_blocks[paragraph] if book_blocks and 0 <= paragraph < len(book_blocks)
                           else item.get("text", ""))
        first, second = _addressed_characters(sources[0], aliases), _addressed_characters(sources[1], aliases)
        if len(first) != 1 or len(second) != 1 or first == second:
            continue
        first_listener, second_listener = next(iter(first)), next(iter(second))
        if not current.get("speaker"):
            current["speaker"] = second_listener
            current["speaker_confidence"] = 0.95
            current["reason"] = "vocativos mútuos em falas consecutivas"
        if not following.get("speaker"):
            following["speaker"] = first_listener
            following["speaker_confidence"] = 0.95
            following["reason"] = "vocativos mútuos em falas consecutivas"


def _infer_preceding_named_actions(dialogues: list[dict[str, Any]], aliases: dict[str, str],
                                    book_blocks: list[str] | None) -> None:
    if not book_blocks or not aliases:
        return
    choices = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
    adverb = r"(?:(?:então|logo|rapidamente|lentamente|silenciosamente)\s+)?"
    action = re.compile(rf"\b({choices})\b\s+{adverb}(?:{SUBJECT_ACTIONS})\b", re.I)
    for item in dialogues:
        if item.get("speaker") or item.get("dialogue_style") != "dash":
            continue
        paragraph = int(item.get("book_paragraph_id", -1))
        if paragraph <= 0:
            continue
        preceding = book_blocks[paragraph - 1]
        if _dash_speech_fragments(preceding):
            continue
        matches = list(action.finditer(preceding))
        if matches:
            item["speaker"] = aliases[matches[-1].group(1).casefold()]
            item["speaker_confidence"] = 0.92
            item["reason"] = "ação do personagem imediatamente antes da fala"


def _resolve_role_coreference(dialogues: list[dict[str, Any]]) -> None:
    """Replace generic occupation labels when the same scene ties that role to one named speaker."""
    owners: dict[tuple[int, str], set[str]] = {}
    anonymous: dict[tuple[int, str], set[str]] = {}
    for item in turn_representatives(dialogues):
        role, speaker = item.get("attribution_role"), item.get("speaker")
        if not role or not speaker:
            continue
        if item.get("reason") == "personagem anônimo descrito explicitamente":
            anonymous.setdefault((int(item.get("scene_id", -1)), str(role)), set()).add(str(speaker))
            continue
        owners.setdefault((int(item.get("scene_id", -1)), str(role)), set()).add(str(speaker))
    unique = {key: next(iter(values)) for key, values in owners.items() if len(values) == 1}
    role_labels = {
        key: max(values, key=lambda value: (
            bool(re.search(r"\b(?:de|do|da|dos|das)\b", value, re.I)),
            len(value.split()), len(value),
        ))
        for key, values in anonymous.items()
    }
    for item in dialogues:
        if item.get("reason") != "personagem anônimo descrito explicitamente":
            continue
        key = (int(item.get("scene_id", -1)), str(item.get("attribution_role")))
        owner = unique.get(key)
        if owner:
            item["speaker"] = owner
            item["speaker_confidence"] = .94
            item["reason"] = "papel ligado a um único personagem nomeado nesta cena"
        elif key in role_labels:
            item["speaker"] = role_labels[key]


def propagate_speaker_inside_turn(dialogues: list[dict[str, Any]]) -> None:
    turns: dict[str, list[dict[str, Any]]] = {}
    for item in dialogues:
        if item.get("dialogue_style") == "dash" and item.get("turn_id"):
            turns.setdefault(str(item["turn_id"]), []).append(item)
    for fragments in turns.values():
        fragments.sort(key=lambda item: int(item.get("fragment_index", 0)))
        confirmed = [item for item in fragments if item.get("manually_confirmed") and item.get("speaker")]
        if confirmed:
            source = confirmed[-1]
            for item in fragments:
                item["speaker"] = source["speaker"]
                item["speaker_confidence"] = 1.0
                item["reason"] = "confirmação manual do usuário no mesmo turno literário"
                item["manually_confirmed"] = True
            continue
        primary = fragments[0]
        if primary.get("speaker"):
            for item in fragments[1:]:
                item["speaker"] = primary["speaker"]
                item["speaker_confidence"] = primary["speaker_confidence"]
                item["reason"] = "mesmo turno literário após atribuição narrativa"
            continue
        anchored = {item["speaker"] for item in fragments if item.get("speaker")}
        if len(anchored) != 1:
            continue
        speaker = next(iter(anchored))
        source = max((item for item in fragments if item.get("speaker") == speaker),
                     key=lambda item: float(item.get("speaker_confidence", 0)))
        for item in fragments:
            if item.get("speaker"):
                continue
            item["speaker"] = speaker
            item["speaker_confidence"] = source["speaker_confidence"]
            item["reason"] = "mesmo turno literário após atribuição narrativa"


def turn_representatives(dialogues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse audio fragments into literary turns for counts and character weights."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for index, item in enumerate(dialogues):
        key = str(item.get("turn_id") or item.get("id") or f"legacy-{index}")
        grouped.setdefault(key, []).append(item)
    return [
        min(items, key=lambda item: (int(item.get("fragment_index", 0)), float(item.get("start", 0))))
        for items in grouped.values()
    ]


def refine_speaker_sequence(dialogues: list[dict[str, Any]], aliases: dict[str, str]) -> None:
    """Use newly reviewed anchors to fill only bidirectionally confirmed gaps."""
    _infer_conversation_turns(dialogues, aliases)
    propagate_speaker_inside_turn(dialogues)


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
        continued_turn = _continued_dash_turn(book_blocks, unit_id) if is_aligned else None
        dash_matches = _dash_speech_fragments(context)
        if continued_turn is not None:
            start = len(context) - len(context.lstrip())
            dash_matches = [TextMatch(context.strip(), start, len(context.rstrip()), style="dash",
                                      continuation=True)]
        quote_matches = [quote for quote in QUOTE.finditer(context)
                         if not dash_matches]
        matches: list[tuple[Any, str, bool]] = [
            *((match, "dash", match.continuation) for match in dash_matches),
            *((match, "quote", False) for match in quote_matches),
        ]
        matches.sort(key=lambda value: value[0].start())
        if not matches and not is_aligned:
            attribution = ATTR_BEFORE.search(context)
            if attribution:
                trailing = context[attribution.end():].strip(" :—–-")
                if trailing:
                    matches = [(TextMatch(trailing, attribution.end(), len(context), style="transcript"),
                                "transcript", False)]
        combined_words = sorted((word for segment in grouped_segments for word in segment.get("words", [])),
                                key=lambda word: float(word.get("start", 0)))
        following_continues = bool(
            is_aligned and book_blocks and unit_id + 1 < len(book_blocks)
            and _continued_dash_turn(book_blocks, unit_id + 1) == unit_id
        )
        previous_fragment_count = (len(_dash_speech_fragments(book_blocks[continued_turn]))
                                   if continued_turn is not None and book_blocks else 0)
        fragment_total = previous_fragment_count + len(dash_matches) + int(following_continues)
        for local_index, (match, style, is_continuation) in enumerate(matches):
            raw_text = match.group(1)
            speech_end = match.end()
            if style == "dash":
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
            scene_roles = role_owners.get(scenes.get(unit_id, 0), {})
            role_is_known = attribution_role in scene_roles
            role_speaker = scene_roles.get(attribution_role or "")
            if not speaker and role_speaker:
                speaker, speaker_score, reason = role_speaker, 0.94, "memória de papel do personagem nesta cena"
            if not speaker and attribution_role and not role_is_known:
                role_label = _anonymous_role_label(context, speech_end, attribution_role)
                if role_label:
                    speaker, speaker_score, reason = role_label, 0.96, "personagem anônimo descrito explicitamente"
            introduced = _self_identified_speaker(text, aliases)
            if not speaker and introduced:
                speaker, speaker_score, reason = introduced, 0.98, "autoidentificação explícita dentro da fala"
            continuation = is_continuation or bool(re.match(
                r"\s*(?:[,.;:]|[—–-])?\s*(?:repetiu|continuou|acrescentou|prosseguiu)\b",
                context[speech_end:], re.I))
            confidence = min(alignment_score if is_aligned else word_score, word_score)
            turn_unit_id = continued_turn if continued_turn is not None else unit_id
            turn_id = (f"book-{turn_unit_id}" if is_aligned and style == "dash"
                       else f"book-{unit_id}-{local_index}" if is_aligned else f"transcript-{unit_id}-{local_index}")
            dialogues.append({"id": f"{unit_id}-{local_index}", "segment_id": owner["id"], "text": text,
                              "start": start, "end": end, "speaker": speaker,
                              "speaker_confidence": round(speaker_score, 4), "alignment_confidence": round(confidence, 4),
                              "source": "book" if is_aligned else "transcript", "reason": reason,
                              "book_paragraph_id": unit_id if is_aligned else None,
                              "book_context": book_blocks[max(0, unit_id - 2):unit_id + 3] if is_aligned and book_blocks else [context],
                              "scene_id": scenes.get(unit_id, 0) if is_aligned else -1,
                              "attribution_role": attribution_role,
                              "dialogue_style": "dash" if style == "dash" else "quote",
                              "turn_id": turn_id,
                              "fragment_index": (previous_fragment_count + local_index)
                              if style == "dash" else 0,
                              "fragment_count": fragment_total if style == "dash" else 1,
                              "is_continuation": is_continuation,
                              "_continues_previous": continuation,
                              "unsafe_short": bool(UNSAFE_SHORT.fullmatch(text.strip()))})
    _resolve_role_coreference(dialogues)
    for item in dialogues:
        if item.get("reason") == "personagem anônimo descrito explicitamente":
            item["_anonymous_role_candidate"] = (item["speaker"], item["speaker_confidence"], item["reason"])
            item["speaker"], item["speaker_confidence"] = None, 0.0
            item["reason"] = "papel anônimo aguardando resolução dos personagens nomeados"
    propagate_speaker_inside_turn(dialogues)
    _infer_preceding_named_actions(dialogues, aliases, book_blocks)
    _infer_mutual_vocatives(dialogues, aliases, book_blocks)
    _infer_addressed_replies(dialogues, aliases, book_blocks)
    _infer_recent_vocative_turns(dialogues, aliases)
    _infer_conversation_turns(dialogues, aliases)
    for item in dialogues:
        candidate = item.pop("_anonymous_role_candidate", None)
        if candidate and not item.get("speaker"):
            item["speaker"], item["speaker_confidence"], item["reason"] = candidate
    propagate_speaker_inside_turn(dialogues)
    for dialogue in dialogues:
        dialogue.pop("_continues_previous", None)
    return dialogues


class TextMatch:
    def __init__(self, value: str, start: int, end: int, *, style: str,
                 continuation: bool = False):
        self.value, self._start, self._end = value, start, end
        self.style = style
        self.continuation = continuation

    def group(self, _: int) -> str:
        return self.value

    def start(self, _: int | None = None) -> int:
        return self._start

    def end(self) -> int:
        return self._end
