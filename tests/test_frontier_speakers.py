"""Protocolo frontier: o modelo propõe, o código decide.

A voz só troca quando o modelo diz que é fala, aponta alguém do catálogo, cita um
trecho que existe no texto e passa da confiança mínima. Qualquer falha nisso vira
abstenção — o turno fica com a voz do narrador, que é a saída segura.
"""
from __future__ import annotations

from audiobook_voice_enhancer.book_speakers import build_book, review_book
from audiobook_voice_enhancer.frontier_speakers import apply_answer, batches, build_prompt, new_stats

BLOCOS = [
    "Iara entrou na sala e encarou Bento.",
    "— Abra a porta — disse Iara.",
    "— Não tenho a chave.",
    "Bento deu de ombros.",
    "— Então arrombe.",
]


def preparar():
    model = build_book(BLOCOS)
    batch = batches(model, (0, len(BLOCOS) - 1))[0]
    prompt, local = build_prompt(model, batch)
    ids = {model["entities"][identity]["name"]: key for key, identity in local.items()}
    return model, batch, prompt, local, ids


def decisao(turn_id, speaker, *, quote="Bento deu de ombros", paragraph=3, confidence=.9,
            kind="speech", evidence="action", anchor_suspect=False):
    return {"id": turn_id, "speaker": speaker, "kind": kind, "evidence": evidence, "quote": quote,
            "paragraph": paragraph, "confidence": confidence, "alternative": None,
            "anchor_suspect": anchor_suspect}


def aplicar(model, batch, local, turns, new_entities=(), threshold=.8):
    stats = new_stats()
    apply_answer(model, batch, local, {"new_entities": list(new_entities), "turns": turns},
                 threshold=threshold, stats=stats)
    return {turn["id"]: turn for turn in batch["turns"]}, stats


def nome(model, turn):
    entity = model["entities"].get(turn["speaker_entity_id"])
    return entity["name"] if entity else None


def test_o_pedido_leva_catalogo_texto_e_pista_explicita():
    model, batch, prompt, local, ids = preparar()
    assert "Iara" in ids
    assert "[1] — Abra a porta — disse Iara." in prompt
    assert f"book-1 | 1 | Abra a porta | pista: {ids['Iara']} («disse Iara»)" in prompt


def test_atribui_quando_fala_catalogo_citacao_e_confianca_batem():
    model, batch, _, local, ids = preparar()
    turns, stats = aplicar(model, batch, local, [
        decisao("book-1", ids["Iara"], quote="disse Iara", paragraph=1, evidence="explicit"),
        decisao("book-2", "N1", quote="Bento deu de ombros", paragraph=3),
        decisao("book-4", ids["Iara"], quote="encarou Bento", paragraph=0, evidence="alternation"),
    ], new_entities=[{"id": "N1", "kind": "named", "mention": "Bento", "paragraph": 3}])
    assert nome(model, turns["book-2"]) == "Bento"
    assert nome(model, turns["book-4"]) == "Iara"
    assert turns["book-1"]["status"] == "explicit"
    assert stats["assigned"] == 2


def test_citacao_inventada_vira_abstencao():
    model, batch, _, local, ids = preparar()
    turns, stats = aplicar(model, batch, local, [decisao("book-4", ids["Iara"], quote="Iara gritou furiosa")])
    assert turns["book-4"]["speaker_entity_id"] is None
    assert turns["book-4"]["review_issue"] == "unverified_quote"


def test_confianca_baixa_vira_abstencao():
    model, batch, _, local, ids = preparar()
    turns, stats = aplicar(model, batch, local, [decisao("book-4", ids["Iara"], confidence=.6)])
    assert turns["book-4"]["speaker_entity_id"] is None
    assert stats["suggested_for_review"] == 1


def test_discordar_da_ancora_tira_a_voz_em_vez_de_trocar():
    model, batch, _, local, ids = preparar()
    turns, stats = aplicar(model, batch, local, [
        decisao("book-1", "N1", anchor_suspect=True)],
        new_entities=[{"id": "N1", "kind": "named", "mention": "Bento", "paragraph": 3}])
    assert turns["book-1"]["status"] == "conflict"
    assert turns["book-1"]["speaker_entity_id"] is None
    assert stats["anchor_conflicts"] == 1


def test_personagem_novo_precisa_aparecer_literalmente_no_texto():
    model, batch, _, local, _ = preparar()
    turns, stats = aplicar(model, batch, local, [decisao("book-2", "N1")],
                           new_entities=[{"id": "N1", "kind": "named", "mention": "Carlos", "paragraph": 3}])
    assert turns["book-2"]["speaker_entity_id"] is None
    assert stats["structural_rejections"] == 1


def test_pensamento_nao_ganha_voz_e_turno_ausente_fica_sem_voz():
    model, batch, _, local, ids = preparar()
    turns, stats = aplicar(model, batch, local, [decisao("book-2", None, kind="thought", evidence="none", quote="")])
    assert turns["book-2"]["status"] == "non_speech"
    assert turns["book-4"]["review_issue"] == "missing_or_duplicate_assignment"


def test_review_book_despacha_para_frontier_com_provedor_falso():
    class Falso:
        model = "falso"
        system_prompt = response_schema = None

        def __init__(self):
            self.payloads = []

        def infer(self, payload):
            self.payloads.append(payload)
            return {"new_entities": [{"id": "N1", "kind": "named", "mention": "Bento", "paragraph": 3}],
                    "turns": [decisao("book-2", "N1")]}

    class SemCache:
        def digest(self, *parts):
            return "x"

        def path(self, *parts):
            class Nada:
                def write_text(self, *a, **k):
                    pass
            return Nada()

        def json(self, kind, key, fn):
            return fn()

    provider = Falso()
    result = review_book(build_book(BLOCOS), provider, SemCache(), (0, 4), protocol="frontier", threshold=.8)
    assert set(provider.payloads[0]) == {"prompt"}
    turn = next(turn for turn in result["turns"] if turn["id"] == "book-2")
    assert result["entities"][turn["speaker_entity_id"]]["name"] == "Bento"
    assert result["review"]["method"] == "frontier-speakers-v1"


def test_mencao_com_frase_inteira_vira_so_o_nome():
    model, batch, _, local, _ = preparar()
    turns, _ = aplicar(model, batch, local, [decisao("book-2", "N1")],
                       new_entities=[{"id": "N1", "kind": "named", "mention": "Bento deu de ombros", "paragraph": 3}])
    assert nome(model, turns["book-2"]) == "Bento"


def test_evidencia_de_estilo_pode_citar_fala_distante():
    model, batch, _, local, ids = preparar()
    turns, _ = aplicar(model, batch, local, [decisao("book-4", ids["Iara"], quote="Abra a porta", paragraph=1,
                                                     evidence="style")])
    assert nome(model, turns["book-4"]) == "Iara"


def test_ponte_por_arquivo_grava_pedido_para_e_depois_consome_a_resposta(tmp_path):
    import json

    import pytest

    from audiobook_voice_enhancer.llm import ExchangeProvider, PendingExchange

    class SemCache:
        def digest(self, *parts):
            return "x"

        def path(self, *parts):
            class Nada:
                def write_text(self, *a, **k):
                    pass
            return Nada()

        def json(self, kind, key, fn):
            return fn()

    provider = ExchangeProvider(tmp_path, "claude-fable-5-1")
    with pytest.raises(PendingExchange):
        review_book(build_book(BLOCOS), provider, SemCache(), (0, 4), protocol="frontier")
    pedido = next(tmp_path.glob("request-*.md"))
    assert "# SYSTEM" in pedido.read_text(encoding="utf-8")
    resposta = tmp_path / pedido.name.replace("request-", "response-").replace(".md", ".json")
    resposta.write_text(json.dumps({"new_entities": [{"id": "N1", "kind": "named", "mention": "Bento",
                                                      "paragraph": 3}],
                                    "turns": [decisao("book-2", "N1")]}), encoding="utf-8")
    result = review_book(build_book(BLOCOS), provider, SemCache(), (0, 4), protocol="frontier")
    turn = next(turn for turn in result["turns"] if turn["id"] == "book-2")
    assert result["entities"][turn["speaker_entity_id"]]["name"] == "Bento"
