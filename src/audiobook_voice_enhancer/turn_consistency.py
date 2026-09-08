"""Coerencia da sequencia de turnos, depois que o modelo ja respondeu.

Pos-processamento deterministico: nao chama o modelo, nao muda prompt nem schema
e nao invalida o cache de respostas. Duas propriedades de dialogo, verificadas no
texto, corrigem o que o modelo erra em conversa longa de duas pessoas:

- **Vocativo:** quem e chamado dentro da fala e o destinatario, nunca o falante.
- **Sanduiche:** tres turnos seguidos da mesma pessoa nao e dialogo; o do meio e
  resposta de outro.

Nenhuma das duas conhece este livro: valem para qualquer narrativa em portugues.
Medidas na Parte 01 com `scripts/simulate_rules.py`, elas consertam 11 turnos e
quebram 3. O veto de vocativo existe justamente porque, sem ele, o sanduiche
quebrava 4 — em "Lembranças de Dijkstra, Jaskier" ele trocava a Yennefer pelo
Jaskier, que e quem esta sendo chamado.

Cuidado ao mexer: ancora textual explicita nunca e sobrescrita, e as regras so
agem em trecho de ATE DOIS falantes. Com tres ou mais, o ganho se manteve e as
perdas dobraram — foi medido.
"""
from __future__ import annotations

import re

VERSION = "turn-consistency-v1"
# Saudacoes que abrem um chamamento: "Salve, Lobo", "Escute, Jaskier".
OPENERS = r"salve|ol[aá]|adeus|parab[eé]ns|obrigad[oa]|escute|escuta|diga|veja|ou[cç]a|espere"


def is_addressed(text: str, name: str) -> bool:
    """O nome aparece como vocativo no proprio texto da fala.

    Exige pontuacao junto ao nome para nao confundir chamamento com assunto: em
    "quem, alem de Vasemir, esta invernando aqui" o Vasemir e mencionado, nao
    chamado, e trocar as duas coisas custaria um acerto.
    """
    forms = sorted({name, name.split()[0]}, key=len, reverse=True)
    escaped = "|".join(re.escape(form) for form in forms if form)
    if not escaped:
        return False
    body = text.strip()
    # A pontuacao final entra no fecho ("Salve, Eskel." / "Conclua, Eskel."), mas
    # NUNCA na abertura: e a virgula ANTES do nome que separa chamamento de
    # mencao, e sem ela "Eskel me contou" viraria vocativo.
    return bool(
        re.search(rf"^(?:{OPENERS})?\s*,?\s*(?:{escaped})\s*[,.!?…]", body, re.I)
        or re.search(rf"[,!?]\s*(?:{escaped})\s*(?:[,.!?…]|$)", text, re.I)
        or re.fullmatch(rf"\s*(?:{escaped})\s*[.!?…]?\s*", body, re.I))


def _addressed_entity(model: dict, turn: dict, identity: str | None) -> bool:
    if not identity:
        return False
    text = " ".join(fragment["text"] for fragment in turn["fragments"])
    return any(is_addressed(text, alias) for alias in model["entities"][identity]["aliases"])


def apply_consistency(model: dict, *, max_speakers: int = 2, window: int = 6) -> dict:
    """Reescreve turnos incoerentes e registra o motivo em cada um."""
    stats = {"version": VERSION, "sandwich_rewrites": 0, "vocative_rewrites": 0,
             "vocative_abstentions": 0, "sandwich_blocked_by_vocative": 0}
    by_scene: dict[int, list] = {}
    for turn in sorted(model["turns"], key=lambda t: (t["scene_id"], t["fragments"][0]["paragraph"])):
        by_scene.setdefault(turn["scene_id"], []).append(turn)
    for sequence in by_scene.values():
        spoken = [t for t in sequence if t["speaker_entity_id"] and t["kind"] == "speech"]
        for index, turn in enumerate(spoken):
            if turn["status"] == "explicit":
                continue
            local = spoken[max(0, index - window):index + window]
            few = len({t["speaker_entity_id"] for t in local}) <= max_speakers
            sandwich = (0 < index < len(spoken) - 1
                        and spoken[index - 1]["speaker_entity_id"] == turn["speaker_entity_id"]
                        == spoken[index + 1]["speaker_entity_id"])
            other = next((t["speaker_entity_id"] for t in reversed(spoken[max(0, index - window):index])
                          if t["speaker_entity_id"] != turn["speaker_entity_id"]), None)
            if sandwich and few and other:
                if _addressed_entity(model, turn, other):
                    # Trocar por quem esta sendo chamado inverteria o par inteiro.
                    stats["sandwich_blocked_by_vocative"] += 1
                    continue
                turn.update(speaker_entity_id=other, status="contextual",
                            consistency_rule="sanduiche_de_tres_turnos")
                stats["sandwich_rewrites"] += 1
            elif _addressed_entity(model, turn, turn["speaker_entity_id"]):
                if other and few and not _addressed_entity(model, turn, other):
                    turn.update(speaker_entity_id=other, status="contextual",
                                consistency_rule="vocativo_e_destinatario")
                    stats["vocative_rewrites"] += 1
                else:
                    # Sem um substituto sustentado pelo texto, abster e a saida
                    # segura: o turno mantem a voz do narrador.
                    turn.update(speaker_entity_id=None, confidence=0.0, status="unresolved",
                                consistency_rule="vocativo_sem_alternativa")
                    stats["vocative_abstentions"] += 1
    model.setdefault("review", {})["turn_consistency"] = stats
    return stats
