"""Bounded scene-local state for the compact speaker protocol."""
from __future__ import annotations

import re
from collections import defaultdict


class SceneLocalMemory:
    """Carry literal anchors and a short hypothesis tail between scene windows."""

    def __init__(self, model, recent_limit=6, anchor_limit=8):
        if recent_limit < 0 or anchor_limit < 0:
            raise ValueError("Compact memory limits cannot be negative")
        self.model = model
        self.recent_limit = recent_limit
        self.anchor_limit = anchor_limit
        self.entity_ids = defaultdict(dict)
        self.records = defaultdict(list)
        self.recorded_turns = defaultdict(set)
        self.turn_ids = {}
        counters = defaultdict(int)
        for turn in model["turns"]:
            scene_id = turn["scene_id"]
            self.turn_ids[turn["id"]] = f"T{counters[scene_id]}"
            counters[scene_id] += 1
        self.audit = {
            "version": "scene-local-memory-v1",
            "literal_records": 0,
            "hypothesis_records": 0,
            "history_turns_emitted": 0,
            "max_catalog_entities": 0,
            "max_scene_entity_ids": 0,
        }

    def entity_id(self, scene_id, identity):
        identifiers = self.entity_ids[scene_id]
        if identity not in identifiers:
            identifiers[identity] = f"E{len(identifiers)}"
            self.audit["max_scene_entity_ids"] = max(
                self.audit["max_scene_entity_ids"], len(identifiers))
        return identifiers[identity]

    def targets(self, batch):
        return {self.turn_ids[turn["id"]]: turn for turn in batch["turns"]}

    def entities(self, batch, text):
        scene_id = batch["scene_id"]
        records = self.records[scene_id]
        literal = {item["identity"] for item in records if item["source"] == "literal"}
        recent = {item["identity"] for item in self._recent_hypotheses(scene_id)}
        anchored = {turn["speaker_entity_id"] for turn in batch["turns"]
                    if turn.get("speaker_entity_id")}
        active = literal | recent | anchored
        entities = []
        for entity in self.model["entities"].values():
            identity = entity["id"]
            if entity["kind"] != "named" and entity["scene_id"] != scene_id:
                continue
            mentioned = any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text, re.I)
                            for alias in entity["aliases"] if alias)
            if identity in active or mentioned:
                self.entity_id(scene_id, identity)
                entities.append(entity)
        entities.sort(key=lambda entity: int(self.entity_ids[scene_id][entity["id"]][1:]))
        self.audit["max_catalog_entities"] = max(self.audit["max_catalog_entities"], len(entities))
        return entities

    def payload(self, scene_id):
        records = self.records[scene_id]
        anchors = [item for item in records if item["source"] == "literal"][-self.anchor_limit:]
        hypotheses = self._recent_hypotheses(scene_id)
        self.audit["history_turns_emitted"] += len(anchors) + len(hypotheses)
        return {
            "literal_anchors_before_window": [self._public(item) for item in anchors],
            "recent_hypotheses": [self._public(item) for item in hypotheses],
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
                "speaker": self.entity_id(scene_id, identity),
                "paragraph": min(fragment["paragraph"] for fragment in turn["fragments"]),
                "source": source,
                "confidence": confidence,
            }
            self.records[scene_id].append(record)
            self.recorded_turns[scene_id].add(turn["id"])
            key = "literal_records" if source == "literal" else "hypothesis_records"
            self.audit[key] += 1

    def _recent_hypotheses(self, scene_id):
        if not self.recent_limit:
            return []
        return [item for item in self.records[scene_id]
                if item["source"] == "model_hypothesis"][-self.recent_limit:]

    @staticmethod
    def _public(record):
        return {key: record[key] for key in
                ("turn", "speaker", "paragraph", "source", "confidence")}
