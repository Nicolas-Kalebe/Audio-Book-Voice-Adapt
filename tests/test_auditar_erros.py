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
