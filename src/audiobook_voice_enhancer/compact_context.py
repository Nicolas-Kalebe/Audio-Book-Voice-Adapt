"""Bounded source context and stable identifiers for compact attribution."""
from __future__ import annotations

import copy
import re


class CompactContext:
    def __init__(self, model, max_chars):
        self.model = model
        self.max_chars = max_chars
        self.scenes = {scene['id']: scene for scene in model['scenes']}
        self.entity_ids = {}
        self.turn_ids = {turn['id']: f'T{i}' for i, turn in enumerate(model['turns'])}
        self.scene_text = {
            scene['id']: '\n'.join(model['blocks'][scene['first_paragraph']:scene['last_paragraph'] + 1])
            for scene in model['scenes']
        }

    def expand(self, batch):
        """Keep target ownership; expand literal context without exceeding budget."""
        scene = self.scenes[batch['scene_id']]
        first, last = batch['first'], batch['last']
        blocks = self.model['blocks']
        size = sum(len(block) for block in blocks[first:last + 1])
        # Prioritize preceding source: it introduces participants for later batches.
        # Whole short scenes fit, so their participants and replies remain visible.
        while first > scene['first_paragraph'] and size + len(blocks[first - 1]) <= self.max_chars:
            first -= 1
            size += len(blocks[first])
        while last < scene['last_paragraph'] and size + len(blocks[last + 1]) <= self.max_chars:
            last += 1
            size += len(blocks[last])
        return {**batch, 'first': first, 'last': last}

    def catalog(self, batch):
        """Scene mentions establish available identities, never speaker assignments."""
        source = self.scene_text[batch['scene_id']]
        anchors = {turn['speaker_entity_id'] for turn in batch['turns']}
        entities = []
        for entity in self.model['entities'].values():
            identity = entity['id']
            self.entity_ids.setdefault(identity, f'E{len(self.entity_ids)}')
            if entity['kind'] != 'named' and entity['scene_id'] != batch['scene_id']:
                continue
            if identity in anchors or any(re.search(rf'(?<!\w){re.escape(alias)}(?!\w)', source, re.I)
                                          for alias in entity['aliases'] if alias):
                entities.append(entity)
        return entities


def bounded_schema(schema, allowed, targets):
    """Constrain identifiers at decoding; semantic validation remains mandatory."""
    result = copy.deepcopy(schema)
    new_ids = [f'N{i}' for i in range(len(targets))]
    result['properties']['entities']['items']['properties']['id'] = {'enum': new_ids}
    assignment = result['properties']['assignments']['items']['properties']
    assignment['id'] = {'enum': list(targets)}
    assignment['speaker'] = {'enum': [None, *allowed, *new_ids]}
    return result
