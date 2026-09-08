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


@pytest.mark.parametrize("texto, esperado", [
    ("— Ciri — respondeu por ela Geralt, emergindo das sombras.", "Geralt"),
    ("— Sim — falou por ele Iara, sem levantar os olhos.", "Iara"),
])
def test_preposicao_com_pronome_nao_esconde_o_sujeito(texto, esperado):
    """"respondeu por ela Geralt": o objeto da preposicao e um PRONOME, entao o
    nome depois so pode ser o sujeito. A lista de palavras funcionais existe para
    barrar "disse para Ana", e sem esta excecao barrava tambem este caso.
    """
    assert falante(texto) == esperado


def test_o_livro_ensina_o_nome_atras_do_cargo():
    """"o feiticeiro Radcliffe" num paragrafo resolve "o feiticeiro" no outro."""
    model = build_book([
        "— Muito bem dito — intrometeu-se o feiticeiro Radcliffe.",
        "— Se a balada diz que se amaram — sorriu o feiticeiro —, então assim foi.",
    ])
    nomes = [model["entities"][t["speaker_entity_id"]]["name"] if t["speaker_entity_id"] else None
             for t in sorted(model["turns"], key=lambda t: t["fragments"][0]["paragraph"])]
    assert nomes == ["Radcliffe", "Radcliffe"]


def test_dois_com_a_mesma_profissao_nao_resolvem_o_cargo_sozinho():
    """A doutrina continua: profissao compartilhada nao identifica ninguem."""
    model = build_book([
        "— Muito bem dito — disse o feiticeiro Radcliffe.",
        "— Discordo por completo — disse o feiticeiro Vilgeforz.",
        "— Então assim foi — sorriu o feiticeiro.",
    ])
    ultimo = sorted(model["turns"], key=lambda t: t["fragments"][0]["paragraph"])[2]
    assert ultimo["speaker_entity_id"] is None


def test_cargo_sem_nome_em_lugar_nenhum_nao_vira_ancora():
    model = build_book(["— Tome cuidado — retrucou o anão, passando a mão pelo machado."])
    assert falante("— Tome cuidado — retrucou o anão, passando a mão pelo machado.") is None
