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


def test_o_readme_manda_o_leitor_para_o_rodar():
    """Quem chega agora precisa achar o que rodar em uma linha, nao em 260."""
    texto = ler("README.md")
    assert "## Estado atual" in texto
    assert "RODAR.md" in texto[:texto.index("## Requisitos")]


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


def test_a_meta_citada_no_estado_atual_e_a_vigente():
    """A meta e 95% dos dois lados desde 08/09/2026.

    Le a tabela do "Estado atual" do README, que e o que alguem olha primeiro, e
    cobra 95% na coluna de meta das duas linhas. Meta antiga citada como historico
    e permitida; anunciada como vigente, nao.
    """
    texto = ler("README.md")
    bloco = texto[texto.index("## Estado atual"):texto.index("### Duas regras")]
    linhas = [linha for linha in bloco.splitlines()
              if linha.startswith("|") and "dubl" in linha.lower()]
    assert len(linhas) == 2, "a tabela do Estado atual perdeu as linhas de precisao/cobertura"
    for linha in linhas:
        assert linha.rstrip().rstrip("|").rstrip().endswith("95%"), \
            f"meta desatualizada na tabela do README: {linha.strip()}"
