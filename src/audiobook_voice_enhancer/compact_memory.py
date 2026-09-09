"""Small, auditable state carried between compact attribution windows."""
from __future__ import annotations

import re
from collections import defaultdict


class CompactMemory:
    """Keep identities stable without copying the whole scene into every prompt.

    Literal anchors persist for the scene. Model decisions are explicitly marked
    as hypotheses and only the most recent ones are exposed to the next window.
    """

    def __init__(self, model, recent_limit=6, anchor_limit=8):
        if recent_limit < 0 or anchor_limit < 0:
            raise ValueError("Compact memory limits cannot be negative")
        self.model = model
        self.recent_limit = recent_limit
        self.anchor_limit = anchor_limit
        self.entity_ids = {identity: f"E{i}" for i, identity in enumerate(model["entities"])}
        self.turn_ids = {turn["id"]: f"T{i}" for i, turn in enumerate(model["turns"])}
        self.records = defaultdict(list)
        self.recorded_turns = defaultdict(set)
        self.audit = {
            "version": "compact-memory-v1",
            "literal_records": 0,
            "hypothesis_records": 0,
            "history_turns_emitted": 0,
            "max_catalog_entities": 0,
        }

    def entity_id(self, identity):
        if identity not in self.entity_ids:
            self.entity_ids[identity] = f"E{len(self.entity_ids)}"
        return self.entity_ids[identity]

    def targets(self, batch):
        return {self.turn_ids[turn["id"]]: turn for turn in batch["turns"]}

    def entities(self, batch, text):
        scene_id = batch["scene_id"]
        remembered = {item["identity"] for item in self.records[scene_id]}
        anchored = {turn["speaker_entity_id"] for turn in batch["turns"]
                    if turn.get("speaker_entity_id")}
        entities = []
        for entity in self.model["entities"].values():
            identity = entity["id"]
            if entity["kind"] != "named" and entity["scene_id"] != scene_id:
                continue
            mentioned = any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text, re.I)
                            for alias in entity["aliases"] if alias)
            if identity in remembered or identity in anchored or mentioned:
                self.entity_id(identity)
                entities.append(entity)
        self.audit["max_catalog_entities"] = max(self.audit["max_catalog_entities"], len(entities))
        return entities

    def payload(self, scene_id):
        records = self.records[scene_id]
        literal = [item for item in records if item["source"] == "literal"][-self.anchor_limit:]
        hypotheses = [item for item in records if item["source"] == "model_hypothesis"][-self.recent_limit:]
        selected = sorted([*literal, *hypotheses], key=lambda item: item["paragraph"])
        self.audit["history_turns_emitted"] += len(selected)
        return {
            "literal_anchors_before_window": [self._public(item) for item in selected
                                               if item["source"] == "literal"],
            "recent_hypotheses": [self._public(item) for item in selected
                                  if item["source"] == "model_hypothesis"],
        }

    def observe(self, batch, literal_before):
        scene_id = batch["scene_id"]
        for turn in batch["turns"]:
            identity = literal_before.get(turn["id"])
            source = "literal" if identity else None
            confidence = 1.0
            if not identity and turn.get("status") == "contextual" and turn.get("speaker_entity_id"):
                identity = turn["speaker_entity_id"]
                source = "model_hypothesis"
                confidence = float(turn.get("confidence", 0))
            if not identity or turn["id"] in self.recorded_turns[scene_id]:
                continue
            record = {
                "turn": self.turn_ids[turn["id"]],
                "identity": identity,
                "speaker": self.entity_id(identity),
                "paragraph": min(fragment["paragraph"] for fragment in turn["fragments"]),
                "source": source,
                "confidence": confidence,
            }
            self.records[scene_id].append(record)
            self.recorded_turns[scene_id].add(turn["id"])
            key = "literal_records" if source == "literal" else "hypothesis_records"
            self.audit[key] += 1

    @staticmethod
    def _public(record):
        return {key: record[key] for key in ("turn", "speaker", "paragraph", "source", "confidence")}
