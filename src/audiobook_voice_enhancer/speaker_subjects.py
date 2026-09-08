"""Literal narrator subjects as candidates for the compact attribution protocol.

Descriptions are references, not a claim that repeated descriptions are one person.
The LLM can link a reference to a named candidate using the surrounding text.
"""
from __future__ import annotations

import re

from .book_speakers import _entity, _key, _narration
from .dialogue import NAME, ROLE_SPEECH_VERB

VERSION = "compact-source-subjects-v1"
SUFFIX = """
source_subject é uma referência literal do narrador imediatamente após a fala.
Seu candidate é uma opção disponível, não uma identidade obrigatória: uma descrição
pode designar um personagem já nomeado. Resolva esse vínculo pelo contexto.
Referências descritivas distintas não provam pessoas distintas, e descrições iguais
não provam a mesma pessoa. Um nome dentro de 'filhas de X' é o parente, não quem fala.
Prefira uma identidade já existente quando o texto sustenta o vínculo; não recrie
essa pessoa em entities. Entidades apenas mencionadas continuam sendo candidatos,
mas uma menção dentro de uma fala não demonstra que estejam presentes."""

# Only material immediately following an attribution verb is considered. No
# search across actions, quoted speech or objects addressed by the speaker.
MODIFIER = r"(?:[a-zà-ÿ]+mente|baixinho|alto|em coro|de repente|de volta|por ele|por ela)"
START = re.compile(rf"^[\s—–-]*(?:{ROLE_SPEECH_VERB}|disseram|perguntaram|responderam|gritaram)"
                   rf"(?:-(?:lhe|lhes|[oa]s?|se|me|na|nas|no|nos))?\s+"
                   rf"(?:{MODIFIER}\s+){{0,2}}", re.I)
ARTICLE = re.compile(r"^(?:o|a|os|as|um|uma|uns|umas)\s+", re.I)
TITLE_NAME = re.compile(rf"(?P<title>[a-zà-ÿ][\wà-ÿ'-]*(?:\s+[a-zà-ÿ][\wà-ÿ'-]*){{0,2}})\s+(?P<name>{NAME})$")


def seed_subjects(model):
    parts = {}
    for turn in model['turns']:
        for fragment in turn['fragments']:
            parts.setdefault(fragment['paragraph'], []).append(fragment)
    audit = {'version': VERSION, 'scope': 'whole_book', 'references': 0, 'named_title_subjects': 0}
    for turn in model['turns']:
        references = []
        for fragment in turn['fragments']:
            p = fragment['paragraph']
            block = model['blocks'][p]
            for start, end in _narration(block, parts[p]):
                if start != fragment['char_end']:
                    continue
                match = START.match(block[start:end])
                if not match:
                    continue
                left = start + match.end()
                tail = block[left:end]
                phrase = re.split(r'[,.;!?—–“”"\n]', tail, maxsplit=1)[0].strip()
                # A candidate must be a short, overt noun phrase with an article.
                # Bare pronouns and clauses ("disse para ...") are not subjects.
                article = ARTICLE.match(phrase)
                if not article or not 1 <= len(phrase) <= 100:
                    continue
                body = phrase[article.end():]
                if not body or not re.fullmatch(r"[\wÀ-ÿ'’ -]+", body):
                    continue
                # Reject clause continuations; do not silently cut them into names.
                if re.search(r'\b(?:que|enquanto|porque|quando)\b', body, re.I):
                    continue
                span = {'paragraph': p, 'start': left, 'end': left + len(phrase), 'quote': phrase}
                named = TITLE_NAME.fullmatch(body)
                if named and any(w in {'de', 'do', 'da', 'dos', 'das', 'e'} for w in _key(named['title']).split()):
                    named = None
                if named and re.search(r'\be\b', named['name']):
                    named = None
                if named:
                    identity = _entity(model, named['name'], 'named', turn['scene_id'], p)
                    audit['named_title_subjects'] += 1
                elif turn['status'] == 'explicit':
                    # A prior explicit self-introduction can already identify
                    # the person designated by a descriptive speech tag.
                    identity = turn['speaker_entity_id']
                else:
                    identity = _entity(model, phrase, 'anonymous', turn['scene_id'], p,
                                       fresh=True, origin=left)
                entity = model['entities'][identity]
                if span not in entity['mentions']:
                    entity['mentions'].append(span)
                references.append({'entity_id': identity, **span, 'named': bool(named)})
        if references:
            turn['source_subjects'] = references
            audit['references'] += len(references)
            identities = {r['entity_id'] for r in references if r['named']}
            if turn['status'] == 'unresolved' and len(identities) == 1 and all(r['named'] for r in references):
                turn.update(speaker_entity_id=next(iter(identities)), status='explicit',
                            confidence=.99, kind='speech',
                            evidence=[{k: r[k] for k in ('paragraph', 'start', 'end', 'quote')} for r in references],
                            anchor_origin='titled_named_subject')
    model['source_subject_audit'] = audit


def attach_payload(payload, targets, reverse):
    for row in payload['turns']:
        references = targets[row['id']].get('source_subjects', [])
        row['source_subject'] = [{
            'candidate': reverse.get(r['entity_id']), 'paragraph': r['paragraph'], 'text': r['quote']}
            for r in references]
