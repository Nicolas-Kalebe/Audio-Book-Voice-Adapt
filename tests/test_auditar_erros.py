import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from auditar_erros import coletar, render_markdown

# ============================================================
# A fila de auditoria: QUAIS turnos erraram, com o que havia em volta.
#
# Os números dizem quantos erros existem; esta ferramenta diz quais são. A
# pergunta que ela serve — "o motor errou ou o rótulo está errado?" — nunca foi
# feita turno a turno neste projeto, e o gabarito da P3 declara que nenhuma
# pessoa o auditou.
# ============================================================


def analysis(atribuicoes, *, regras=None, textos=None):
    regras = regras or {}
    textos = textos or {}
    dialogues, turns = [], []
    for paragrafo, falante in enumerate(atribuicoes, 1):
        texto = textos.get(paragrafo, f"Fala do paragrafo {paragrafo}.")
        dialogues.append({"id": f"{paragrafo}-0", "turn_id": f"book-{paragrafo}",
                          "fragment_index": 0, "book_paragraph_id": paragrafo,
                          "scene_id": 7, "speaker": falante,
                          "speaker_confidence": .96, "text": texto})
        turns.append({"id": f"book-{paragrafo}",
                      "fragments": [{"paragraph": paragrafo, "text": texto}],
                      "speaker_entity_id": falante, "status": "contextual",
                      "consistency_rule": regras.get(paragrafo)})
    return {"files": [{"dialogues": dialogues, "book_speaker_analysis": {
        "turns": turns,
        "entities": [{"id": "Ana", "name": "Ana"}, {"id": "Bia", "name": "Bia"}]}}]}


GOLD = {"version": 1, "name": "fixture", "spoken_by": {
    "Ana": ["1-0", "3-0"], "Bia": ["2-0", "4-0"]},
    "ambiguous_spoken": {}, "non_spoken": {}, "anonymous_role_labels": []}


def test_separa_erro_de_abstencao():
    """Abster e trocar a voz sao desfechos diferentes — e so um e defeito."""
    relatorio = coletar(GOLD, analysis(["Ana", "Ana", "Ana", None]))
    desfechos = {linha["id"]: linha["desfecho"] for linha in relatorio["linhas"]}
    assert desfechos["2-0"] == "erro"        # esperava Bia, saiu Ana
    assert desfechos["4-0"] == "abstencao"   # esperava Bia, ficou sem voz
    assert "1-0" not in desfechos            # acertou, nao entra na fila


def test_traz_o_contexto_em_volta_do_erro():
    """Sem os vizinhos nao da para julgar quem falava — e era isso que obrigava
    a abrir o EPUB para cada turno."""
    relatorio = coletar(GOLD, analysis(["Ana", "Ana", "Ana", "Bia"]), contexto=1)
    erro = next(linha for linha in relatorio["linhas"] if linha["id"] == "2-0")
    paragrafos = [vizinho["paragrafo"] for vizinho in erro["contexto"]]
    assert paragrafos == [1, 2, 3]
    alvo = [vizinho for vizinho in erro["contexto"] if vizinho["alvo"]]
    assert len(alvo) == 1 and alvo[0]["paragrafo"] == 2
    assert alvo[0]["falante"] == "Ana"


def test_carrega_a_regra_que_escreveu_a_voz():
    relatorio = coletar(GOLD, analysis(["Ana", "Ana", "Ana", "Bia"],
                                       regras={2: "sanduiche_de_tres_turnos"}))
    erro = next(linha for linha in relatorio["linhas"] if linha["id"] == "2-0")
    assert erro["regra_consistencia"] == "sanduiche_de_tres_turnos"


def test_figurante_fica_fora_da_fila():
    """Figurante nao entra na conta que decide o produto (08/09/2026), entao
    tambem nao ocupa tempo de quem audita."""
    gold = {"version": 1, "name": "fixture",
            "spoken_by": {"Ana": ["1-0"], "Voz ao longe": ["2-0"]},
            "ambiguous_spoken": {}, "non_spoken": {},
            "anonymous_role_labels": ["Voz ao longe"]}
    relatorio = coletar(gold, analysis(["Ana", "Ana"]))
    assert [linha["id"] for linha in relatorio["linhas"]] == []


def test_markdown_pergunta_o_veredito_de_cada_erro():
    relatorio = coletar(GOLD, analysis(["Ana", "Ana", "Ana", "Bia"],
                                       regras={2: "sanduiche_de_tres_turnos"}))
    texto = render_markdown(relatorio)
    assert "Erros por regra que escreveu a voz" in texto
    assert "sanduiche_de_tres_turnos" in texto
    assert "Trocas mais frequentes" in texto
    # O veredito humano e o ponto da ferramenta: ela nao decide nada sozinha.
    assert texto.count("Veredito") == 1


# ── SINAIS OBSERVAVEIS ────────────────────────────────────────────────────────
#
# Pre-classificacao dos erros, para a auditoria virar conferencia em vez de
# trabalho do zero. Nenhum sinal depende do livro: saem do texto do turno e da
# vizinhanca. Eles NAO decidem nada — a tabela deles diz qual categoria domina, e
# e isso que aponta o que a proxima mudanca deve atacar.

from auditar_erros import sinais_do_erro


def analysis_com_alias(atribuicoes, textos):
    base = analysis(atribuicoes, textos=textos)
    base["files"][0]["book_speaker_analysis"]["entities"] = [
        {"id": "Ana", "name": "Ana", "aliases": ["Ana"]},
        {"id": "Bia", "name": "Bia", "aliases": ["Bia"]},
    ]
    return base


def test_sinal_marca_a_regra_de_coerencia_que_escreveu_a_voz():
    relatorio = coletar(GOLD, analysis(["Ana", "Ana", "Ana", "Bia"],
                                       regras={2: "sanduiche_de_tres_turnos"}))
    erro = next(linha for linha in relatorio["linhas"] if linha["id"] == "2-0")
    assert "reescrita_de_coerencia" in erro["sinais"]


def test_sinal_aponta_nome_citado_dentro_da_propria_fala():
    """Vocativo e mencao sao a armadilha classica: quem e chamado nao e quem fala."""
    relatorio = coletar(GOLD, analysis_com_alias(
        ["Ana", "Ana", "Ana", "Bia"],
        {2: "— Voce esta certa, Ana, mas eu discordo."}))
    erro = next(linha for linha in relatorio["linhas"] if linha["id"] == "2-0")
    assert "entidade_citada_no_proprio_turno" in erro["sinais"]


def test_sinal_aponta_fala_sem_verbo_de_narracao():
    relatorio = coletar(GOLD, analysis_com_alias(
        ["Ana", "Ana", "Ana", "Bia"], {2: "— Nao mesmo."}))
    erro = next(linha for linha in relatorio["linhas"] if linha["id"] == "2-0")
    assert "sem_verbo_de_fala_no_turno" in erro["sinais"]


def test_sinal_nao_aparece_quando_ha_verbo_de_narracao():
    relatorio = coletar(GOLD, analysis_com_alias(
        ["Ana", "Ana", "Ana", "Bia"], {2: "— Nao mesmo — respondeu ela."}))
    erro = next(linha for linha in relatorio["linhas"] if linha["id"] == "2-0")
    assert "sem_verbo_de_fala_no_turno" not in erro["sinais"]


def test_sinal_separa_quem_estava_por_perto_de_quem_nao_estava():
    """Distingue "o motor chutou alguem de fora" de "a resposta certa nao estava la"
    — sao dificuldades diferentes e pedem mudancas diferentes."""
    relatorio = coletar(GOLD, analysis(["Ana", "Ana", "Ana", "Bia"]), contexto=1)
    erro = next(linha for linha in relatorio["linhas"] if linha["id"] == "2-0")
    # Ana falava em volta; Bia (a certa) nao.
    assert "predito_nao_aparece_por_perto" not in erro["sinais"]
    assert "esperado_nao_aparece_por_perto" in erro["sinais"]


def test_markdown_traz_a_tabela_que_decide_o_proximo_passo():
    relatorio = coletar(GOLD, analysis(["Ana", "Ana", "Ana", "Bia"],
                                       regras={2: "sanduiche_de_tres_turnos"}))
    texto = render_markdown(relatorio)
    assert "Sinais observáveis nos erros" in texto
    assert "reescrita_de_coerencia" in texto
    assert "Pré-classificação, não veredito" in texto
