"""Propriedades de dialogo que corrigem a sequencia depois do modelo.

Vocativo: quem e chamado dentro da fala e o destinatario, nunca o falante.
Sanduiche: tres turnos seguidos da mesma pessoa nao e dialogo.

Nenhuma conhece livro nenhum. As duas foram medidas em `scripts/simulate_rules.py`
antes de entrar; o veto de vocativo existe porque, sem ele, o sanduiche invertia
pares inteiros em falas como "Lembrancas de Dijkstra, Jaskier".
"""
from __future__ import annotations

import pytest

from audiobook_voice_enhancer.book_speakers import build_book, merge_partial_names
from audiobook_voice_enhancer.turn_consistency import apply_consistency, is_addressed


@pytest.mark.parametrize("text", [
    "Sim, Eskel, sou eu.",
    "Conclua seu raciocinio, Eskel.",
    "Salve, Eskel. Estavamos aguardando voce.",
    "Eskel",
    "Eskel?",
])
def test_a_name_called_inside_the_line_is_the_addressee(text):
    assert is_addressed(text, "Eskel")


@pytest.mark.parametrize("text", [
    "Quem, alem de Vasemir, esta invernando aqui?",   # mencao, nao chamamento
    "Eskel me contou que a estrada estava fechada.",  # sujeito de uma frase
    "Procuramos Eskel desde ontem.",
])
def test_a_name_merely_mentioned_is_not_a_vocative(text):
    """Confundir mencao com chamamento troca acerto por recuo."""
    assert not is_addressed(text, "Eskel")


def test_a_name_that_opens_a_statement_is_a_topic_not_a_vocative():
    assert not is_addressed("Rience. Ele fugiu pela janela.", "Rience")


def test_a_surname_can_be_used_as_a_vocative():
    assert is_addressed("Pare com isso, Merigold!", "Triss Merigold")


def _two_person_scene(speakers):
    """Cena sintetica: uma fala por paragrafo, ja atribuida."""
    blocks = [f"— Fala {i} — comentou alguem." for i in range(len(speakers))]
    model = build_book(blocks)
    model["entities"] = {name: {"id": name, "name": name, "display_name": name, "kind": "named",
                                "scene_id": None, "aliases": [name], "mentions": []}
                         for name in set(speakers)}
    for turn, name in zip(sorted(model["turns"], key=lambda t: t["fragments"][0]["paragraph"]), speakers):
        turn.update(speaker_entity_id=name, kind="speech", status="contextual", confidence=.95)
    return model


def test_three_turns_in_a_row_become_an_alternation():
    model = _two_person_scene(["Ana", "Bia", "Bia", "Bia", "Ana"])
    apply_consistency(model)
    got = [t["speaker_entity_id"] for t in sorted(model["turns"], key=lambda t: t["fragments"][0]["paragraph"])]
    assert got == ["Ana", "Bia", "Ana", "Bia", "Ana"]
    assert model["review"]["turn_consistency"]["sandwich_rewrites"] == 1


def test_an_explicit_anchor_is_never_overwritten():
    model = _two_person_scene(["Ana", "Bia", "Bia", "Bia", "Ana"])
    middle = sorted(model["turns"], key=lambda t: t["fragments"][0]["paragraph"])[2]
    middle["status"] = "explicit"
    apply_consistency(model)
    assert middle["speaker_entity_id"] == "Bia"


def test_the_vocative_vetoes_the_alternation():
    """Sem este veto o par inteiro se inverte: foi o que quebrou 4 turnos."""
    model = _two_person_scene(["Ana", "Bia", "Bia", "Bia", "Ana"])
    middle = sorted(model["turns"], key=lambda t: t["fragments"][0]["paragraph"])[2]
    middle["fragments"][0]["text"] = "Nao esqueci, Ana, que nao temos amigos comuns."
    apply_consistency(model)
    assert middle["speaker_entity_id"] == "Bia"
    assert model["review"]["turn_consistency"]["sandwich_blocked_by_vocative"] == 1


def test_without_a_supported_alternative_the_turn_abstains():
    """Decisao do proprietario: sem certeza, mantem a voz do narrador."""
    model = _two_person_scene(["Ana", "Bia", "Cid", "Dan"])
    turn = sorted(model["turns"], key=lambda t: t["fragments"][0]["paragraph"])[3]
    turn["fragments"][0]["text"] = "Chega, Dan."
    apply_consistency(model)
    assert turn["speaker_entity_id"] is None
    assert turn["status"] == "unresolved"


def test_reciprocal_vocatives_resolve_both_sides_of_a_reply():
    model = _two_person_scene(["Bia", "Ana"])
    turns = sorted(model["turns"], key=lambda t: t["fragments"][0]["paragraph"])
    turns[0]["fragments"][0]["text"] = "Bia!"
    turns[1]["fragments"][0]["text"] = "Ana?"
    apply_consistency(model)
    assert [turn["speaker_entity_id"] for turn in turns] == ["Ana", "Bia"]


def test_a_long_compound_monologue_is_not_broken_by_the_sandwich_rule():
    model = _two_person_scene(["Ana", "Bia", "Bia", "Bia", "Ana"])
    middle = sorted(model["turns"], key=lambda t: t["fragments"][0]["paragraph"])[2]
    middle["fragments"] = [
        {**middle["fragments"][0], "text": "a" * 140},
        {**middle["fragments"][0], "text": "b" * 140},
    ]
    apply_consistency(model)
    assert middle["speaker_entity_id"] == "Bia"


def test_a_two_turn_phase_slip_is_repaired_only_with_context_on_both_sides():
    model = _two_person_scene(["Ana", "Bia", "Bia", "Ana", "Ana", "Bia"])
    apply_consistency(model)
    got = [turn["speaker_entity_id"] for turn in model["turns"]]
    assert got == ["Ana", "Bia", "Ana", "Bia", "Ana", "Bia"]


def test_a_third_person_reference_cannot_be_the_contextual_speaker():
    model = _two_person_scene(["Ana", "Bia", "Cid"])
    turns = model["turns"]
    turns[1]["status"] = "explicit"
    turns[2]["fragments"][0]["text"] = "Cid trouxe a chave."
    apply_consistency(model)
    assert turns[2]["speaker_entity_id"] == "Bia"
    assert turns[2]["consistency_rule"] == "referencia_em_terceira_pessoa"


def test_short_name_links_to_a_single_full_name():
    model = build_book(["— Vamos — disse Radcliffe de Oxenfurt.", "— Certo — disse Radcliffe."])
    assert len(merge_partial_names(model)) == 1
    assert {e["name"] for e in model["entities"].values()} == {"Radcliffe de Oxenfurt"}
    assert all(t["speaker_entity_id"] for t in model["turns"])
    assert len({t["speaker_entity_id"] for t in model["turns"]}) == 1


def test_a_shared_first_name_between_two_people_merges_nobody():
    """A doutrina que protege duas pessoas de virarem uma continua valendo."""
    model = build_book(["— A — disse Iara Silva.", "— B — disse Iara Costa.", "— C — disse Iara."])
    assert merge_partial_names(model) == {}
    assert len([e for e in model["entities"].values() if e["kind"] == "named"]) == 3
