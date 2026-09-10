"""Conservative cross-window repair for the compact speaker protocol.

The normal compact answer remains authoritative. This router only gets a
second opinion for turns that the normal pass left unresolved, and it can only
choose identities established earlier in the same scene. Gold labels are
deliberately absent from this module.
"""
from __future__ import annotations

from collections import Counter, defaultdict


VERSION = "hybrid-speaker-router-v1.1"
VERSION_REVISAO = "hybrid-speaker-router-v1.2"
SYSTEM_SUFFIX = """

Esta e uma revisao conservadora de continuidade. O primeiro passe nao conseguiu
atribuir os turnos enviados. Use somente IDs R do catalogo established_speakers;
nao crie entidades. A resposta contem somente assignments. literal_anchors sao fatos extraidos
da narracao. recent_assignments sao hipoteses do primeiro passe e podem estar
erradas. Preserve a abstencao (speaker null) se a continuidade nao bastar.
"""
# O texto muda quando a janela leva turnos JA atribuidos: dizer que o primeiro
# passe "nao conseguiu atribuir" seria falso, e instrucao falsa e a forma mais
# barata de ensinar o modelo a ignorar a instrucao inteira.
SYSTEM_SUFFIX_REVISAO = """

Esta e uma leitura independente de continuidade. Alguns turnos enviados nao foram
atribuidos pelo primeiro passe; outros foram, e voce nao sabe quais. Decida cada um
apenas pelo texto e pelo catalogo. Use somente IDs R do catalogo
established_speakers; nao crie entidades. A resposta contem somente assignments.
literal_anchors sao fatos extraidos da narracao. recent_assignments sao hipoteses do
primeiro passe e podem estar erradas. Responda speaker null quando o texto e a
continuidade nao bastarem — null e a resposta correta para o turno que voce nao
consegue decidir sozinho.
"""


class HybridRepairRouter:
    """Route only unresolved continuation windows to bounded scene memory."""

    def __init__(self, model, *, history_limit=12, max_speakers=4, revisar_fora_do_elenco=False):
        if history_limit < 1 or max_speakers < 2:
            raise ValueError("Hybrid router limits are invalid")
        self.model = model
        self.history_limit = history_limit
        self.max_speakers = max_speakers
        # ── A REVISAO DE QUEM ESTA FORA DO ELENCO (v1.2) ──────────────────
        #
        # A v1.1 so olha LACUNA. O turno que o primeiro passe atribuiu errado
        # nunca e revisto, por decisao explicita: sobrescrever atribuicao
        # contextual foi o que a memoria completa fez, e ela destruiu acertos.
        #
        # Esta opcao amplia o alvo por um criterio observavel e estreito: turno
        # cujo falante NAO aparece no elenco estabelecido da propria cena. Nao e
        # "revisar o que parece errado" — e "revisar quem escolheu alguem que
        # ninguem viu falando aqui, e sem ancora literal que o sustente".
        #
        # Desligada por padrao para permitir A/B contra a v1.1 ja medida.
        self.revisar_fora_do_elenco = revisar_fora_do_elenco
        self.records = defaultdict(list)
        self.recorded_turns = defaultdict(set)
        self.windows_seen = Counter()
        self.audit = {
            "version": VERSION_REVISAO if revisar_fora_do_elenco else VERSION,
            "base_windows": 0,
            "routed_windows": 0,
            "repair_calls": 0,
            "repair_targets": 0,
            "accepted_repairs": 0,
            "rejected_repairs": 0,
            "ignored_entity_proposals": 0,
            "repair_token_budgets": [],
            # A revisao e contada em separado da reparacao de lacuna: sao riscos
            # diferentes, e somar as duas esconderia justamente o que se quer
            # medir — quantas vozes ja atribuidas foram trocadas.
            "revisao_targets": 0,
            "revisao_trocada": 0,
            "revisao_mantida": 0,
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
        # Sem revisao, janela sem lacuna nao tem o que fazer aqui — e sai antes
        # de gastar a conta do elenco. Com revisao, ainda pode haver alvo.
        if not unresolved and not self.revisar_fora_do_elenco:
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

        # ── OS ALVOS DE REVISAO ────────────────────────────────────────────
        # Turno JA atribuido, contextual, cujo falante nao aparece no elenco
        # estabelecido desta cena. Duas exclusoes que nao se negociam:
        #   · `explicit` fica de fora — ancora literal e fato do narrador, e a
        #     assimetria que protege P1/P2 comeca aqui;
        #   · o que este roteador ja reparou fica de fora, senao ele revisa a si
        #     mesmo e entra em laco entre janelas.
        revisao = {}
        if self.revisar_fora_do_elenco:
            revisao = {
                key: turn for key, turn in targets.items()
                if key not in unresolved
                and turn.get("status") == "contextual"
                and turn.get("speaker_entity_id")
                and turn["speaker_entity_id"] not in active
                and not turn.get("hybrid_repair")
            }
        if not unresolved and not revisao:
            self.audit["skipped"]["nothing_unresolved"] += 1
            return None

        ordered = []
        for row in recent:
            if row["identity"] in active and row["identity"] not in ordered:
                ordered.append(row["identity"])
        ids = {identity: f"R{index}" for index, identity in enumerate(ordered)}
        self.audit["routed_windows"] += 1
        self.audit["repair_targets"] += len(unresolved)
        self.audit["revisao_targets"] += len(revisao)
        # A janela vai numa chamada so. O modelo nao sabe qual alvo e lacuna e
        # qual e revisao: se soubesse, teria como tratar a revisao com o vies de
        # confirmar o que ja estava la, que e o oposto de uma leitura independente.
        alvos = {**unresolved, **revisao}
        return {"targets": alvos, "identifiers": ids, "history": recent,
                "kinds": {key: ("revisao" if key in revisao else "lacuna") for key in alvos}}

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
        kinds = plan.get("kinds", {})
        accepted = {}
        for key in plan["targets"]:
            eh_revisao = kinds.get(key) == "revisao"
            rows = [row for row in assignments
                    if isinstance(row, dict) and row.get("id") == key]
            if len(rows) != 1:
                self._recusar(eh_revisao)
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
                                 "confidence": float(confidence), "raw": row,
                                 "kind": kinds.get(key, "lacuna")}
                if eh_revisao:
                    self.audit["revisao_trocada"] += 1
                else:
                    self.audit["accepted_repairs"] += 1
            else:
                self._recusar(eh_revisao)
        return accepted

    def _recusar(self, eh_revisao):
        """Nao trocar e o desfecho NORMAL da revisao, nao uma falha.

        Na lacuna, resposta invalida ou insegura significa que o turno continua
        sem voz — e isso conta como reparo rejeitado. Na revisao significa que a
        atribuicao do primeiro passe FICA, que e exatamente o que se quer quando a
        segunda leitura nao tem certeza. Somar os dois no mesmo contador faria uma
        revisao saudavel parecer um motor quebrado.
        """
        if eh_revisao:
            self.audit["revisao_mantida"] += 1
        else:
            self.audit["rejected_repairs"] += 1

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
