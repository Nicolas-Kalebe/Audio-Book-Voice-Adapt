"""Trava do teto: a meta tem de continuar alcancavel pelo gabarito.

O motor passou semanas medindo 69,8% contra um gabarito cujo teto era 81,6%,
porque todo papel anonimo saia rotulado com um sufixo de cena que nunca casava.
Este teste garante que a diferenca entre o resultado e a meta seja identificacao,
nunca nomenclatura.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from audiobook_voice_enhancer.benchmark import _role_key, load_gold

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from gold_ceiling import ceiling  # noqa: E402

BENCH = Path(__file__).resolve().parents[1] / "benchmarks"
GOLD = BENCH / "part01_gold.yaml"
GABARITOS = [BENCH / "part01_gold.yaml", BENCH / "part02_gold.yaml"]


def test_the_ninety_five_percent_target_still_fits_in_the_gold():
    """Meta de 95% em tudo, sobre os dublaveis. Cobertura e a trava apertada:
    turno sem audio nunca sera atribuido, entao a folga vem do teto de deteccao."""
    result = ceiling(load_gold(GOLD))
    dublavel, detected = result["dublavel_turns"], result["dublavel_detected"]
    need_coverage = -(-dublavel * 95 // 100)
    assert detected >= need_coverage, (
        f"Cobertura de 95% exige {need_coverage} atribuidos, mas so {detected} dos "
        f"{dublavel} dublaveis tem audio: a meta nao cabe no gabarito.")
    assert result["dublavel_ceiling"] >= -(-need_coverage * 95 // 100)


def test_only_undetected_turns_are_out_of_reach():
    """Toda perda do oraculo tem de ser fala nao localizada no audio."""
    result = ceiling(load_gold(GOLD))
    assert all(item["predicted"] == "NAO DETECTADA" for item in result["unreachable_labels"])


@pytest.mark.parametrize("first, second", [
    ("o elfo alto e louro", "Elfo alto e louro"),
    ("Gnomo dos artigos metálicos", "Gnomo dos artigos metalicos"),
    ("Taberneiro [cena 3, P12:40]", "taberneiro"),
])
def test_identity_key_ignores_article_accent_order_and_disambiguator(first, second):
    assert _role_key(first) == _role_key(second)


@pytest.mark.parametrize("first, second", [
    ("guarda alto", "guarda gordo"),
    ("elfo alto e louro", "elfo alto e moreno"),
    ("sacerdote gordo", "sacerdote"),
])
def test_identity_key_keeps_different_descriptions_apart(first, second):
    assert _role_key(first) != _role_key(second)


@pytest.mark.parametrize("caminho", GABARITOS, ids=lambda p: p.stem)
def test_todo_gabarito_carrega_e_cabe_na_meta(caminho):
    """Vale para os dois: um gabarito so serve se a meta couber dentro dele."""
    resultado = ceiling(load_gold(caminho))
    dublavel, detectados = resultado["dublavel_turns"], resultado["dublavel_detected"]
    assert dublavel > 0
    assert detectados >= -(-dublavel * 95 // 100)


def test_o_holdout_da_parte_02_nao_foi_usado_para_ajustar_o_motor():
    """A Parte 02 so vale como validacao externa enquanto isto for verdade.

    Se alguem ajustar regra contra ela, tem de trocar o protocolo aqui — e ai o
    projeto volta a nao ter holdout nenhum, o que precisa ficar visivel.
    """
    gold = load_gold(BENCH / "part02_gold.yaml")
    assert gold["evaluation_protocol"]["independent_holdout"] is True
    assert gold["evaluation_protocol"]["status"] == "holdout_congelado_antes_de_medir"


def test_os_dois_gabaritos_nao_se_sobrepoem():
    """Intervalos disjuntos: senao a Parte 02 herdaria o ajuste feito na Parte 01."""
    um, dois = (load_gold(c)["scope"] for c in GABARITOS)
    assert um["last_book_paragraph"] < dois["first_book_paragraph"]
