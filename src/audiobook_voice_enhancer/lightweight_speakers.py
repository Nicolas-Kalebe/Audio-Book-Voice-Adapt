"""Bounded attribution inputs; no generated scene catalogue or extra LLM pass."""
from __future__ import annotations

import copy
import re

from .book_speakers import _narration
from .dialogue import ROLE_SPEECH_VERB

VERSION = "lightweight-speakers-v1"
SUFFIX = """
O catálogo contém candidatos, não uma afirmação de presença. narration_mentions
mostra ocorrências locais fora das falas; elas também podem mencionar ausentes.
Leia o texto completo para resolver ações, pronomes e descrições. local_narration
destaca a narração do parágrafo do turno, sem atribuir automaticamente seu sujeito.
Os nomes em uma pergunta podem ser destinatários. Uma resposta pode nomear outra
pessoa. Preserve a identidade ao longo da conversa usando o contexto posterior.
Se faltar um falante, use N0, N1 etc. com uma menção literal curta e seu parágrafo.
Não gere cadastro de todos os personagens: proponha apenas falantes necessários
às respostas desta janela. Use exatamente os IDs permitidos pelo schema."""


def fragments_by_paragraph(model):
    parts = {}
    for turn in model["turns"]:
        for fragment in turn["fragments"]:
            parts.setdefault(fragment["paragraph"], []).append(fragment)
    return parts


def narration(model, paragraph, parts):
    block = model["blocks"][paragraph]
    return [{"paragraph": paragraph, "start": a, "end": b, "text": block[a:b]}
            for a, b in _narration(block, parts.get(paragraph, [])) if block[a:b].strip(" —–-\t\n")]


def attach_subjects(model):
    """Recover named subjects after short speech-verb modifiers, not proximity."""
    owners = {}
    for entity in model["entities"].values():
        if entity["kind"] == "named":
            for alias in entity["aliases"]:
                owners.setdefault(alias.casefold(), set()).add(entity["id"])
    unique = {a: next(iter(ids)) for a, ids in owners.items() if len(ids) == 1}
    if not unique:
        return
    names = "|".join(re.escape(a) for a in sorted(unique, key=len, reverse=True))
    modifier = r"(?:por\s+(?:ele|ela|eles|elas)|baixinho|alto|finalmente|calmamente|secamente|lentamente)"
    pattern = re.compile(rf"^[\s—–-]*{ROLE_SPEECH_VERB}\s+(?:{modifier}\s+){{1,2}}"
                         rf"(?P<name>{names})(?!\w)", re.I)
    parts = fragments_by_paragraph(model)
    for turn in model["turns"]:
        if turn["status"] == "explicit":
            continue
        matches = []
        for fragment in turn["fragments"]:
            for span in narration(model, fragment["paragraph"], parts):
                if span["start"] != fragment["char_end"]:
                    continue
                match = pattern.match(span["text"])
                if match and not re.match(r"\s+e\s+", span["text"][match.end():], re.I):
                    matches.append((unique[match["name"].casefold()], {
                        "paragraph": span["paragraph"], "start": span["start"],
                        "end": span["start"] + match.end(), "quote": match[0]}))
        if len({identity for identity, _ in matches}) == 1:
            turn.update(speaker_entity_id=matches[0][0], confidence=.99, status="explicit",
                        kind="speech", evidence=[s for _, s in matches],
                        anchor_origin="modified_speech_subject")


def enrich(payload, model, targets):
    parts = fragments_by_paragraph(model)
    local = {p["paragraph"]: narration(model, p["paragraph"], parts) for p in payload["scene_text"]}
    for entity in payload["entities"]:
        entity["narration_mentions"] = []
        for paragraph, spans in local.items():
            if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", span["text"], re.I)
                   for alias in entity["aliases"] for span in spans):
                entity["narration_mentions"].append(paragraph)
        entity["narration_mentions"] = entity["narration_mentions"][:8]
    for row in payload["turns"]:
        turn = targets[row["id"]]
        paragraphs = sorted({f["paragraph"] for f in turn["fragments"]})
        # Pointers into the original scene_text keep responses and input compact.
        row["local_narration"] = [{"paragraph": p, "start": s["start"], "end": s["end"]}
                                  for p in paragraphs for s in local[p]]
        row["anchor_evidence"] = turn["evidence"] if turn["status"] == "explicit" else []


def response_schema(base, payload):
    schema = copy.deepcopy(base)
    new_ids = [f"N{i}" for i in range(len(payload["turns"]))]
    entities = schema["properties"]["entities"]
    entities["maxItems"] = len(new_ids)
    entities["items"]["properties"]["id"] = {"enum": new_ids}
    entities["items"]["properties"]["paragraph"] = {
        "enum": [p["paragraph"] for p in payload["scene_text"]]}
    assignments = schema["properties"]["assignments"]
    assignments.update(minItems=len(payload["turns"]), maxItems=len(payload["turns"]))
    assignments["items"]["properties"]["id"] = {"enum": [t["id"] for t in payload["turns"]]}
    assignments["items"]["properties"]["speaker"] = {
        "enum": [e["id"] for e in payload["entities"]] + new_ids + [None]}
    return schema
