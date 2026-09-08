"""Coerencia da sequencia de turnos, depois que o modelo ja respondeu.

Pos-processamento deterministico: nao chama o modelo, nao muda prompt nem schema
e nao invalida o cache de respostas. Propriedades verificaveis do texto corrigem
o que o modelo erra em sequencias de dialogo:

- **Vocativo:** quem e chamado dentro da fala e o destinatario, nunca o falante.
- **Vocativos reciprocos:** se A chama B e B chama A em seguida, os dois lados
  ficam identificados.
- **Sanduiche e fase:** corrigem colapsos locais apenas com contexto dos dois lados;
  turnos compostos longos sao preservados como monologos.
- **Terceira pessoa:** uma proposta contextual nao pode falar de si como sujeito
  gramatical sem evidencia adicional.

Nenhuma regra conhece nomes ou respostas deste livro. Ancoras textuais explicitas
nunca sao sobrescritas. As metricas de desenvolvimento e os limites de validade
ficam registrados no README e no RODAR.
"""
from __future__ import annotations

import re

VERSION = "turn-consistency-v2"
# Saudacoes que abrem um chamamento: "Salve, Lobo", "Escute, Jaskier".
OPENERS = r"salve|ol[aá]|adeus|parab[eé]ns|obrigad[oa]|escute|escuta|diga|veja|ou[cç]a|espere"


def is_addressed(text: str, name: str) -> bool:
    """O nome aparece como vocativo no proprio texto da fala.

    Exige pontuacao junto ao nome para nao confundir chamamento com assunto: em
    "quem, alem de Vasemir, esta invernando aqui" o Vasemir e mencionado, nao
    chamado, e trocar as duas coisas custaria um acerto.
    """
    tokens = name.split()
    forms = sorted({name, tokens[0], tokens[-1]}, key=len, reverse=True)
    escaped = "|".join(re.escape(form) for form in forms if form)
    if not escaped:
        return False
    body = text.strip()
    # A pontuacao final entra no fecho ("Salve, Eskel." / "Conclua, Eskel."), mas
    # NUNCA na abertura: e a virgula ANTES do nome que separa chamamento de
    # mencao, e sem ela "Eskel me contou" viraria vocativo.
    return bool(
        re.search(rf"^(?:{OPENERS})\s*,?\s*(?:{escaped})\s*[,.!?…]", body, re.I)
        or re.search(rf"^(?:{escaped})\s*,", body, re.I)
        or re.search(rf"[,!?]\s*(?:{escaped})\s*(?:[,.!?…]|$)", text, re.I)
        or re.fullmatch(rf"\s*(?:{escaped})\s*[.!?…]?\s*", body, re.I))


def _addressed_entity(model: dict, turn: dict, identity: str | None) -> bool:
    if not identity:
        return False
    return any(is_addressed(fragment["text"], alias)
               for fragment in turn["fragments"]
               for alias in model["entities"][identity]["aliases"])


def _addressed_identities(model: dict, turn: dict) -> set[str]:
    return {identity for identity in model["entities"]
            if _addressed_entity(model, turn, identity)}


def _paragraph(turn: dict) -> int:
    return int(turn["fragments"][0]["paragraph"])


def _text_length(turn: dict) -> int:
    return sum(len(fragment["text"]) for fragment in turn["fragments"])


THIRD_PERSON_VERBS = (
    r"est[aá]|[eé]|era|foi|ser[aá]|tem|tinha|teve|vai|iria|pode|podia|deve|devia|"
    r"quer|queria|sabe|sabia|disse|falou|trouxe|levou|fez|viu|ouviu|chegou|"
    r"is|was|has|had|will|would|can|could|said|brought|went|did|saw|arrived"
)


def _third_person_reference(model: dict, turn: dict, identity: str | None) -> bool:
    """True when the proposed speaker is named as a third person in the line."""
    if not identity:
        return False
    for fragment in turn["fragments"]:
        for alias in model["entities"][identity]["aliases"]:
            for form in {alias, alias.split()[0], alias.split()[-1]}:
                if re.search(rf"(?<!\w){re.escape(form)}\s+(?:(?:o|a|os|as|lhe)\s+)?"
                             rf"(?:{THIRD_PERSON_VERBS})\b", fragment["text"], re.I):
                    return True
    return False


def apply_consistency(model: dict, *, max_speakers: int = 2, window: int = 6) -> dict:
    """Reescreve turnos incoerentes e registra o motivo em cada um."""
    stats = {"version": VERSION, "sandwich_rewrites": 0, "vocative_rewrites": 0,
             "vocative_abstentions": 0, "sandwich_blocked_by_vocative": 0,
             "reciprocal_vocative_rewrites": 0,
             "phase_slip_rewrites": 0, "third_person_rewrites": 0,
             "third_person_abstentions": 0}
    by_scene: dict[int, list] = {}
    for turn in sorted(model["turns"], key=lambda t: (t["scene_id"], t["fragments"][0]["paragraph"])):
        by_scene.setdefault(turn["scene_id"], []).append(turn)
    for sequence in by_scene.values():
        spoken = [t for t in sequence if t["speaker_entity_id"] and t["kind"] == "speech"]

        # A chama B; B chama A. Esse par fornece os dois lados da conversa sem
        # depender de alternancia ou de o modelo ter acertado qualquer um deles.
        # E uma relacao textual simetrica e funciona tambem em cenas com elenco
        # grande, desde que os turnos sejam adjacentes e os nomes sejam univocos.
        for before, after in zip(spoken, spoken[1:]):
            if _paragraph(after) - _paragraph(before) > 2:
                continue
            # Uma resposta longa pode citar ou chamar varias pessoas ao expor um
            # argumento; isso nao constitui um par de saudacoes reciprocas.
            if _text_length(before) > 120 or _text_length(after) > 120:
                continue
            before_addresses = _addressed_identities(model, before)
            after_addresses = _addressed_identities(model, after)
            if len(before_addresses) != 1 or len(after_addresses) != 1:
                continue
            addressee_before = next(iter(before_addresses))
            addressee_after = next(iter(after_addresses))
            if addressee_before == addressee_after:
                continue
            if ((before["status"] == "explicit" and before["speaker_entity_id"] != addressee_after)
                    or (after["status"] == "explicit" and after["speaker_entity_id"] != addressee_before)):
                continue
            for turn, identity in ((before, addressee_after), (after, addressee_before)):
                if turn["status"] != "explicit" and turn["speaker_entity_id"] != identity:
                    turn.update(speaker_entity_id=identity, status="contextual",
                                consistency_rule="vocativos_reciprocos")
                    stats["reciprocal_vocative_rewrites"] += 1

        for index, turn in enumerate(spoken):
            if turn["status"] == "explicit":
                continue
            local = spoken[max(0, index - window):index + window]
            few = len({t["speaker_entity_id"] for t in local}) <= max_speakers
            # Um turno composto e longo costuma ser monologo retomado depois de
            # uma insercao narrativa, nao uma resposta curta de outro falante.
            # Turnos compostos curtos continuam elegiveis: o narrador tambem pode
            # inserir uma atribuicao breve no meio de uma resposta real.
            text_length = _text_length(turn)
            compound_monologue = len(turn["fragments"]) > 1 and text_length >= 250
            sandwich = (not compound_monologue and 0 < index < len(spoken) - 1
                        and spoken[index - 1]["speaker_entity_id"] == turn["speaker_entity_id"]
                        == spoken[index + 1]["speaker_entity_id"])
            other = next((t["speaker_entity_id"] for t in reversed(spoken[max(0, index - window):index])
                          if t["speaker_entity_id"] != turn["speaker_entity_id"]), None)
            previous = spoken[index - 1] if index else None
            previous_addresses = _addressed_identities(model, previous) if previous else set()
            reply_candidate = next(iter(previous_addresses)) if len(previous_addresses) == 1 else None
            recent_explicit = next((candidate["speaker_entity_id"]
                                    for candidate in reversed(spoken[max(0, index - 12):index])
                                    if candidate["status"] == "explicit"
                                    and candidate["speaker_entity_id"] != turn["speaker_entity_id"]), None)
            if sandwich and few and other:
                if _addressed_entity(model, turn, other):
                    # Trocar por quem esta sendo chamado inverteria o par inteiro.
                    stats["sandwich_blocked_by_vocative"] += 1
                    continue
                turn.update(speaker_entity_id=other, status="contextual",
                            consistency_rule="sanduiche_de_tres_turnos")
                stats["sandwich_rewrites"] += 1
                continue
            recent_speakers = {candidate["speaker_entity_id"]
                               for candidate in spoken[max(0, index - 4):index]}
            third_person = (_third_person_reference(model, turn, turn["speaker_entity_id"])
                            and turn["speaker_entity_id"] not in recent_speakers)
            if third_person:
                replacement = (reply_candidate
                               if reply_candidate != turn["speaker_entity_id"] else recent_explicit)
                replacement = replacement or recent_explicit
                if replacement and not _addressed_entity(model, turn, replacement):
                    turn.update(speaker_entity_id=replacement, status="contextual",
                                consistency_rule="referencia_em_terceira_pessoa")
                    stats["third_person_rewrites"] += 1
                else:
                    turn.update(speaker_entity_id=None, confidence=0.0, status="unresolved",
                                consistency_rule="terceira_pessoa_sem_alternativa")
                    stats["third_person_abstentions"] += 1
            elif _addressed_entity(model, turn, turn["speaker_entity_id"]):
                replacement = other if other and few else None
                if replacement and not _addressed_entity(model, turn, replacement):
                    turn.update(speaker_entity_id=replacement, status="contextual",
                                consistency_rule="resposta_ao_vocativo")
                    stats["vocative_rewrites"] += 1
                else:
                    # Sem um substituto sustentado pelo texto, abster e a saida
                    # segura: o turno mantem a voz do narrador.
                    turn.update(speaker_entity_id=None, confidence=0.0, status="unresolved",
                                consistency_rule="vocativo_sem_alternativa")
                    stats["vocative_abstentions"] += 1

        # Em uma troca longa entre duas pessoas, A B | B A | A B e uma inversao
        # local de exatamente dois turnos, cercada pela mesma fase dos dois
        # lados. Corrigir apenas o par central evita impor alternancia a uma cena
        # inteira e exige seis observacoes consecutivas para agir.
        for index in range(len(spoken) - 5):
            group = spoken[index:index + 6]
            identities = [turn["speaker_entity_id"] for turn in group]
            first, second = identities[0], identities[1]
            if not first or not second or first == second:
                continue
            if identities != [first, second, second, first, first, second]:
                continue
            if any(_paragraph(right) - _paragraph(left) > 2 for left, right in zip(group, group[1:])):
                continue
            middle_left, middle_right = group[2], group[3]
            if middle_left["status"] == "explicit" or middle_right["status"] == "explicit":
                continue
            if (_addressed_entity(model, middle_left, first)
                    or _addressed_entity(model, middle_right, second)):
                continue
            middle_left.update(speaker_entity_id=first, status="contextual",
                               consistency_rule="deslocamento_de_fase")
            middle_right.update(speaker_entity_id=second, status="contextual",
                                consistency_rule="deslocamento_de_fase")
            stats["phase_slip_rewrites"] += 2
    model.setdefault("review", {})["turn_consistency"] = stats
    return stats
