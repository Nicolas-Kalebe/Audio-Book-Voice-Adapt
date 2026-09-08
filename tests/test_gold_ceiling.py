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

GOLD = Path(__file__).resolve().parents[1] / "benchmarks" / "part01_gold.yaml"


def test_a_perfect_engine_can_reach_the_ninety_percent_target():
    result = ceiling(load_gold(GOLD))
    required = -(-result["gold_source_turns"] * 90 // 100)
    assert result["identity_ceiling"] >= required, (
        f"Teto {result['identity_ceiling']}/{result['gold_source_turns']} abaixo da meta "
        f"de {required}: nenhuma melhoria de modelo alcanca a meta neste gabarito.")


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
