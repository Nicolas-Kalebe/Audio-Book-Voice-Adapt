"""Conservative cross-window repair for the compact speaker protocol.

The normal compact answer remains authoritative. This router only gets a
second opinion for turns that the normal pass left unresolved, and it can only
choose identities established earlier in the same scene. Gold labels are
deliberately absent from this module.
"""
from __future__ import annotations

from collections import Counter, defaultdict


VERSION = "hybrid-speaker-router-v1.1"
SYSTEM_SUFFIX = """

Esta e uma revisao conservadora de continuidade. O primeiro passe nao conseguiu
atribuir os turnos enviados. Use somente IDs R do catalogo established_speakers;
nao crie entidades. A resposta contem somente assignments. literal_anchors sao fatos extraidos
da narracao. recent_assignments sao hipoteses do primeiro passe e podem estar
erradas. Preserve a abstencao (speaker null) se a continuidade nao bastar.
"""


class HybridRepairRouter:
    """Route only unresolved continuation windows to bounded scene memory."""

    def __init__(self, model, *, history_limit=12, max_speakers=4):
        if history_limit < 1 or max_speakers < 2:
            raise ValueError("Hybrid router limits are invalid")
        self.model = model
        self.history_limit = history_limit
        self.max_speakers = max_speakers
        self.records = defaultdict(list)
        self.recorded_turns = defaultdict(set)
        self.windows_seen = Counter()
        self.audit = {
            "version": VERSION,
            "base_windows": 0,
            "routed_windows": 0,
            "repair_calls": 0,
            "repair_targets": 0,
            "accepted_repairs": 0,
            "rejected_repairs": 0,
            "ignored_entity_proposals": 0,
            "repair_token_budgets": [],
            "skipped": Counter(),
        }

    def plan(self, batch, targets):
        """Return a repair plan, or None when the observable gate is unsafe."""
        scene_id = batch["scene_id"]
        self.audit["base_windows"] += 1
        if not self.windows_seen[scene_id]:
            self.audit["skipped"]["first_window_in_scene"] += 1
            return None

        unresolved = {
            key: turn for key, turn in targets.items()
            if not turn.get("speaker_entity_id")
            and turn.get("status") not in {"explicit", "non_speech"}
        }
        if not unresolved:
            self.audit["skipped"]["nothing_unresolved"] += 1
            return None

        recent = self.records[scene_id][-self.history_limit:]
        literal = {row["identity"] for row in recent if row["source"] == "literal"}
        hypothesis_counts = Counter(
            row["identity"] for row in recent if row["source"] == "base_hypothesis")
        # A model-only identity must recur. One isolated guess is not enough to
        # become a cross-window fact. Literal identities need no such vote.
        active = literal | {identity for identity, count in hypothesis_counts.items() if count >= 2}
        if len(active) < 2:
            self.audit["skipped"]["fewer_than_two_established_speakers"] += 1
            return None
        if len(active) > self.max_speakers:
            self.audit["skipped"]["cast_too_large"] += 1
            return None

        ordered = []
        for row in recent:
            if row["identity"] in active and row["identity"] not in ordered:
                ordered.append(row["identity"])
        ids = {identity: f"R{index}" for index, identity in enumerate(ordered)}
        self.audit["routed_windows"] += 1
        self.audit["repair_targets"] += len(unresolved)
        return {"targets": unresolved, "identifiers": ids, "history": recent}

    @staticmethod
    def response_schema(plan):
        """Constrain Ollama to the exact repair IDs and the established cast."""
        target_ids = list(plan["targets"])
        speaker_ids = [*plan["identifiers"].values(), None]
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "assignments": {
                    "type": "array",
                    "minItems": len(target_ids),
                    "maxItems": len(target_ids),
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "id": {"type": "string", "enum": target_ids},
                            "speaker": {"enum": speaker_ids},
                            "kind": {"enum": ["speech", "thought", "citation", "unknown"]},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                        "required": ["id", "speaker", "kind", "confidence"],
                    },
                },
            },
            "required": ["assignments"],
        }

    def token_budget(self, plan):
        """Bound repair output without reducing the input context used to decide."""
        budget = min(2048, max(256, 72 * len(plan["targets"])))
        self.audit["repair_token_budgets"].append(budget)
        return budget

    def payload(self, batch, plan, scene_text):
        ids = plan["identifiers"]
        return {
            "version": VERSION,
            "task": "repair_unresolved_continuation",
            "book_id": self.model["book_id"],
            "scene_id": batch["scene_id"],
            "scene_text": scene_text,
            "established_speakers": [
                {"id": local, "name": self.model["entities"][identity]["name"],
                 "kind": self.model["entities"][identity]["kind"],
                 "aliases": self.model["entities"][identity]["aliases"]}
                for identity, local in ids.items()
            ],
            "literal_anchors": [self._public(row, ids) for row in plan["history"]
                                if row["source"] == "literal" and row["identity"] in ids],
            "recent_assignments": [self._public(row, ids) for row in plan["history"]
                                   if row["source"] == "base_hypothesis" and row["identity"] in ids],
            "turns": [
                {"id": key, "fragments": [{"paragraph": fragment["paragraph"],
                                              "text": fragment["text"]}
                                             for fragment in turn["fragments"]]}
                for key, turn in plan["targets"].items()
            ],
        }

    def replacements(self, answer, plan, threshold):
        """Validate repair rows and translate their local IDs to model IDs."""
        if not isinstance(answer, dict):
            raise ValueError("Invalid hybrid repair response")
        # Some models ignore the instruction and echo/propose entities. They are
        # harmless here: assignments still have to use an existing R identifier.
        # Ignore and count them instead of discarding otherwise valid repairs.
        entities = answer.get("entities")
        if isinstance(entities, list):
            self.audit["ignored_entity_proposals"] += len(entities)
        assignments = answer.get("assignments")
        if not isinstance(assignments, list):
            raise ValueError("Invalid hybrid repair response")
        reverse = {local: identity for identity, local in plan["identifiers"].items()}
        accepted = {}
        for key in plan["targets"]:
            rows = [row for row in assignments
                    if isinstance(row, dict) and row.get("id") == key]
            if len(rows) != 1:
                self.audit["rejected_repairs"] += 1
                continue
            row = rows[0]
            confidence = row.get("confidence")
            valid = (
                row.get("kind") == "speech"
                and isinstance(row.get("speaker"), str)
                and row["speaker"] in reverse
                and type(confidence) in {int, float}
                and max(float(threshold), .95) <= confidence <= 1
            )
            if valid:
                accepted[key] = {"identity": reverse[row["speaker"]],
                                 "confidence": float(confidence), "raw": row}
                self.audit["accepted_repairs"] += 1
            else:
                self.audit["rejected_repairs"] += 1
        return accepted

    def observe(self, batch, literal_before):
        """Store only literal facts and recurring candidates from the base pass."""
        scene_id = batch["scene_id"]
        for turn in batch["turns"]:
            identity = literal_before.get(turn["id"])
            source = "literal" if identity else None
            confidence = 1.0
            if (not identity and turn.get("status") == "contextual"
                    and turn.get("speaker_entity_id") and not turn.get("hybrid_repair")):
                identity = turn["speaker_entity_id"]
                source = "base_hypothesis"
                confidence = float(turn.get("confidence", 0))
            if not identity or turn["id"] in self.recorded_turns[scene_id]:
                continue
            self.records[scene_id].append({
                "turn": turn["id"], "identity": identity, "source": source,
                "confidence": confidence,
                "paragraph": min(fragment["paragraph"] for fragment in turn["fragments"]),
            })
            self.recorded_turns[scene_id].add(turn["id"])
        self.windows_seen[scene_id] += 1

    def finish(self):
        audit = dict(self.audit)
        audit["skipped"] = dict(audit["skipped"])
        return audit

    @staticmethod
    def _public(row, ids):
        return {"turn": row["turn"], "speaker": ids[row["identity"]],
                "paragraph": row["paragraph"], "source": row["source"],
                "confidence": row["confidence"]}
