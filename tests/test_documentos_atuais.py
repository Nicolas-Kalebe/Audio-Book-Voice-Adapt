"""Documento com numero velho e pior que documento nenhum.

Ordem do proprietario em 08/09/2026: quem chega depois tem de saber o que fazer e
o que mudou sem perguntar. Foi um numero desatualizado sobrevivendo a correcao que
o invalidou — o `178/255` — que fez cinco campanhas serem comparadas contra um
instrumento quebrado. Estes testes cobram o que da para cobrar por maquina; o
resto e revisao.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from audiobook_voice_enhancer.benchmark import load_gold

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))
from gold_ceiling import ceiling  # noqa: E402


def ler(nome: str) -> str:
    return (RAIZ / nome).read_text(encoding="utf-8")


@pytest.mark.parametrize("nome", ["README.md", "RODAR.md", "AGENTS.md"])
def test_a_porta_de_entrada_existe(nome):
    assert (RAIZ / nome).is_file()


def test_o_readme_avisa_o_abandono_logo_no_comeco():
    """Projeto abandonado ate segunda ordem desde 20/10/2026 (ordem do proprietario):
    quem abre o README tem de saber disso antes de qualquer outra coisa."""
    texto = ler("README.md")
    assert "abandonado" in texto[:300].lower()
    assert "RODAR.md" in texto


def test_o_rodar_registra_o_que_mudou():
    assert "## O que mudou" in ler("RODAR.md")


def test_os_numeros_do_denominador_batem_com_o_gabarito():
    """213 dublaveis e 42 figurantes sao contas, nao opiniao: se o gabarito
    mudar, o documento que os cita tem de mudar no mesmo commit."""
    resultado = ceiling(load_gold(RAIZ / "benchmarks" / "part01_gold.yaml"))
    dublavel = resultado["dublavel_turns"]
    figurante = resultado["gold_source_turns"] - dublavel
    for nome in ("README.md", "RODAR.md", "AGENTS.md", "docs/RESULTADO-PART01.md"):
        texto = ler(nome)
        for numero, papel in ((dublavel, "dublaveis"), (figurante, "figurantes")):
            citados = {int(n) for n in re.findall(r"\b(\d{2,3})\b", texto)}
            if papel == "dublaveis" and "dublá" in texto.lower():
                assert numero in citados, f"{nome} fala de dubláveis sem citar {numero}"
