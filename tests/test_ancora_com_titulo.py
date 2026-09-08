"""Cargo entre o artigo e o nome: "observou o chanceler Vilibert".

E construcao comum em portugues e o parser nao a enxergava, entao o falante ficava
sem ancora nenhuma e o modelo entregava as falas dele a quem tinha. Na Parte 01
eram 11 ancoras perdidas — seis so do Vilibert, que nao recebia UMA atribuicao
explicita no livro inteiro.

O risco do conserto e o oposto: aceitar palavra demais entre o verbo e o nome faz
"disse que Ana estava certa" ancorar na Ana, que so e assunto. Por isso a lista de
palavras funcionais, e por isso estes testes.
"""
from __future__ import annotations

import pytest

from audiobook_voice_enhancer.book_speakers import build_book


def falante(texto: str) -> str | None:
    model = build_book([texto])
    turn = model["turns"][0]
    if turn["status"] != "explicit" or not turn["speaker_entity_id"]:
        return None
    return model["entities"][turn["speaker_entity_id"]]["name"]


@pytest.mark.parametrize("texto, esperado", [
    ("— Comenta-se — observou o chanceler Vilibert — que ela tombou.", "Vilibert"),
    ("— Querem nosso sangue! — urrou o chanceler Vilibert.", "Vilibert"),
    ("— Muito bem dito — intrometeu-se o feiticeiro Radcliffe.", "Radcliffe"),
    ("— Abra — disse a capitã Luma.", "Luma"),
    ("— Vamos — respondeu o velho mestre Bento.", "Bento"),
    ("— Certo — disse Iara.", "Iara"),
])
def test_a_ancora_atravessa_o_cargo_ate_o_nome(texto, esperado):
    assert falante(texto) == esperado


@pytest.mark.parametrize("texto", [
    "— Sim — disse que Ana estava certa.",
    "— Sim — disse para Ana com calma.",
    "— Sim — disse depois de Ana sair.",
    "— Sim — comentou com Radcliffe o chanceler Vilibert.",
])
def test_palavra_funcional_entre_o_verbo_e_o_nome_nao_ancora(texto):
    """Mencao nao e atribuicao. Ancorar errado e pior que nao ancorar: a fala
    vira voz trocada errada em vez de continuar com o narrador.

    O ultimo caso e real (P114 da Parte 01): "comentou COM Radcliffe o chanceler
    Vilibert" e do Vilibert, e ancorar no Radcliffe seria um erro novo.
    """
    assert falante(texto) != "Ana"
    assert falante(texto) != "Radcliffe"


@pytest.mark.parametrize("verbo", ["esbravejou", "bradou", "indagou", "vociferou"])
def test_verbos_de_fala_que_faltavam(verbo):
    assert falante(f"— Chega — {verbo} o chanceler Vilibert.") == "Vilibert"


def test_duas_atribuicoes_conflitantes_continuam_sem_ancora():
    """A regra nova nao pode afrouxar a protecao contra atribuicao ambigua."""
    model = build_book(["— Sim — disse o chanceler Vilibert, e Iara concordou."])
    assert model["turns"][0]["status"] != "explicit" or \
        model["entities"][model["turns"][0]["speaker_entity_id"]]["name"] == "Vilibert"
