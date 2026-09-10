from audiobook_voice_enhancer.book_speakers import build_book, review_book
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.llm import LLMProvider


class Provider(LLMProvider):
    model = "hybrid-fixture"

    def __init__(self, repair_confidence=.97):
        self.calls = []
        self.repair_schemas = []
        self.repair_confidence = repair_confidence

    def infer(self, payload):
        self.calls.append(payload)
        if payload.get("task") == "repair_unresolved_continuation":
            self.repair_schemas.append(self.response_schema)
            return {"entities": [], "assignments": [
                {"id": turn["id"], "speaker": "R0", "kind": "speech",
                 "confidence": self.repair_confidence}
                for turn in payload["turns"]
            ]}
        ids = {entity["name"]: entity["id"] for entity in payload["entities"]}
        if payload["turns"][0]["fragments"][0]["paragraph"] < 2:
            speakers = [ids["Iara"], ids["Nilo"]]
        else:
            speakers = [None] * len(payload["turns"])
        return {"entities": [], "assignments": [
            {"id": turn["id"], "speaker": speaker,
             "kind": "speech" if speaker else "unknown", "confidence": .98}
            for turn, speaker in zip(payload["turns"], speakers)
        ]}


def model_with_split_scene():
    return build_book([
        "— Primeiro — disse Iara.",
        "— Segundo — disse Nilo.",
        "— Terceiro.",
        "— Quarto.",
    ])


def test_hybrid_repairs_only_unresolved_continuation_window(tmp_path):
    provider = Provider()
    result = review_book(model_with_split_scene(), provider, Cache(tmp_path),
                         protocol="hybrid", max_turns=2)

    repair = [call for call in provider.calls
              if call.get("task") == "repair_unresolved_continuation"]
    assert len(provider.calls) == 3
    assert len(repair) == 1
    assert {row["name"] for row in repair[0]["established_speakers"]} == {"Iara", "Nilo"}
    assert len(repair[0]["literal_anchors"]) == 2
    schema = provider.repair_schemas[0]
    assert "entities" not in schema["properties"]
    assert schema["properties"]["assignments"]["maxItems"] == 2
    assert set(schema["properties"]["assignments"]["items"]["properties"]["speaker"]["enum"]) == {
        "R0", "R1", None}
    assert result["turns"][2]["status"] == "contextual"
    assert result["turns"][2]["review_issue"] == "repaired_by_hybrid_continuity"
    assert result["hybrid_router"]["accepted_repairs"] == 2
    assert result["review"]["total_llm_calls"] == 3
    assert result["hybrid_router"]["repair_token_budgets"] == [256]


def test_hybrid_rejects_repair_below_stricter_floor(tmp_path):
    provider = Provider(repair_confidence=.94)
    result = review_book(model_with_split_scene(), provider, Cache(tmp_path),
                         protocol="hybrid", max_turns=2, threshold=.90)

    assert result["turns"][2]["speaker_entity_id"] is None
    assert result["hybrid_router"]["accepted_repairs"] == 0
    assert result["hybrid_router"]["rejected_repairs"] == 2


def test_compact_baseline_does_not_invoke_hybrid_router(tmp_path):
    provider = Provider()
    result = review_book(model_with_split_scene(), provider, Cache(tmp_path),
                         protocol="compact", max_turns=2)

    assert len(provider.calls) == 2
    assert "hybrid_router" not in result


def test_hybrid_never_overwrites_literal_anchor_on_model_disagreement(tmp_path):
    model = build_book(["— Primeiro — disse Iara."])

    class Disagreeing(LLMProvider):
        model = "fixture"

        def infer(self, payload):
            return {"entities": [], "assignments": [
                {"id": payload["turns"][0]["id"], "speaker": None,
                 "kind": "unknown", "confidence": .99}
            ]}

    result = review_book(model, Disagreeing(), Cache(tmp_path), protocol="hybrid")
    turn = result["turns"][0]
    assert turn["status"] == "explicit"
    assert turn["speaker_entity_id"] is not None


def test_hybrid_ignores_proposed_entities_but_never_accepts_their_ids(tmp_path):
    provider = Provider()

    original_infer = provider.infer

    def infer(payload):
        if payload.get("task") != "repair_unresolved_continuation":
            return original_infer(payload)
        provider.calls.append(payload)
        return {"entities": [{"id": "N0", "mention": "Intruso"}], "assignments": [
            {"id": payload["turns"][0]["id"], "speaker": "R0",
             "kind": "speech", "confidence": .97},
            {"id": payload["turns"][1]["id"], "speaker": "N0",
             "kind": "speech", "confidence": .99},
        ]}

    provider.infer = infer
    result = review_book(model_with_split_scene(), provider, Cache(tmp_path),
                         protocol="hybrid", max_turns=2)

    assert result["turns"][2]["speaker_entity_id"] is not None
    assert result["turns"][3]["speaker_entity_id"] is None
    assert result["hybrid_router"]["ignored_entity_proposals"] == 1
    assert result["hybrid_router"]["accepted_repairs"] == 1
    assert result["hybrid_router"]["rejected_repairs"] == 1
    assert all(entity["name"] != "Intruso" for entity in result["entities"].values())


# ── A REVISAO DE QUEM ESTA FORA DO ELENCO (v1.2) ──────────────────────────────
#
# A v1.1 so repara LACUNA: turno que o primeiro passe deixou sem voz. O turno
# atribuido ERRADO nunca era revisto, e e nele que moram os erros que sobram.
#
# O alvo novo e estreito e observavel: turno contextual cujo falante NAO aparece
# no elenco estabelecido da propria cena. Os testes abaixo exercitam o gate
# diretamente, com o historico montado a mao — pelo `review_book` seria preciso
# um livro de mais de doze turnos so para empurrar uma identidade para fora da
# janela, e o que se quer provar aqui e a regra, nao o tamanho do fixture.

from audiobook_voice_enhancer.hybrid_speakers import HybridRepairRouter


def router_com_historico(*, revisar):
    """Cena onde Iara e Nilo estao estabelecidos e Zoe nao."""
    modelo = {"book_id": "b", "entities": {
        "iara": {"name": "Iara", "kind": "named", "aliases": ["Iara"]},
        "nilo": {"name": "Nilo", "kind": "named", "aliases": ["Nilo"]},
        "zoe": {"name": "Zoe", "kind": "named", "aliases": ["Zoe"]},
    }}
    router = HybridRepairRouter(modelo, revisar_fora_do_elenco=revisar)
    router.windows_seen[1] = 1
    router.records[1] = [
        {"turn": "t0", "identity": "iara", "source": "literal", "confidence": 1.0, "paragraph": 0},
        {"turn": "t1", "identity": "nilo", "source": "literal", "confidence": 1.0, "paragraph": 1},
    ]
    return router


def turno(status, identity, **extra):
    return {"id": "x", "status": status, "speaker_entity_id": identity,
            "fragments": [{"paragraph": 9, "text": "— Fala."}], **extra}


def test_revisao_pega_turno_atribuido_a_quem_nao_esta_no_elenco():
    router = router_com_historico(revisar=True)
    plano = router.plan({"scene_id": 1, "turns": []}, {"T0": turno("contextual", "zoe")})
    assert plano is not None
    assert plano["kinds"]["T0"] == "revisao"
    assert router.audit["revisao_targets"] == 1
    # O catalogo oferecido e so o elenco estabelecido — Zoe nao esta nele.
    assert set(plano["identifiers"]) == {"iara", "nilo"}


def test_sem_a_opcao_o_turno_atribuido_nao_vira_alvo():
    router = router_com_historico(revisar=False)
    assert router.plan({"scene_id": 1, "turns": []}, {"T0": turno("contextual", "zoe")}) is None
    assert router.audit["revisao_targets"] == 0


def test_revisao_nunca_toca_ancora_literal():
    """A assimetria que protege P1/P2 comeca aqui: `explicit` e fato do narrador."""
    router = router_com_historico(revisar=True)
    assert router.plan({"scene_id": 1, "turns": []}, {"T0": turno("explicit", "zoe")}) is None


def test_revisao_nao_revisa_o_que_ela_mesma_reparou():
    """Sem isto o roteador revisa a propria decisao a cada janela seguinte."""
    router = router_com_historico(revisar=True)
    alvo = {"T0": turno("contextual", "zoe", hybrid_repair={"id": "T0"})}
    assert router.plan({"scene_id": 1, "turns": []}, alvo) is None


def test_quem_esta_no_elenco_nao_e_revisado():
    """A regra e "fora do elenco", nao "parece errado"."""
    router = router_com_historico(revisar=True)
    assert router.plan({"scene_id": 1, "turns": []}, {"T0": turno("contextual", "iara")}) is None


def test_revisao_troca_quando_a_segunda_leitura_decide_com_confianca():
    router = router_com_historico(revisar=True)
    plano = router.plan({"scene_id": 1, "turns": []}, {"T0": turno("contextual", "zoe")})
    aceitos = router.replacements(
        {"assignments": [{"id": "T0", "speaker": "R0", "kind": "speech", "confidence": .97}]},
        plano, .9)
    assert aceitos["T0"]["identity"] == "iara"
    assert aceitos["T0"]["kind"] == "revisao"
    assert router.audit["revisao_trocada"] == 1
    assert router.audit["accepted_repairs"] == 0


def test_null_na_revisao_mantem_o_primeiro_passe_e_nao_conta_como_falha():
    """`null` e a resposta CORRETA para o turno que a segunda leitura nao decide.

    Contar isso como reparo rejeitado faria uma revisao saudavel — a que quase
    sempre mantem — parecer um motor quebrado no audit.
    """
    router = router_com_historico(revisar=True)
    plano = router.plan({"scene_id": 1, "turns": []}, {"T0": turno("contextual", "zoe")})
    aceitos = router.replacements(
        {"assignments": [{"id": "T0", "speaker": None, "kind": "speech", "confidence": .99}]},
        plano, .9)
    assert aceitos == {}
    assert router.audit["revisao_mantida"] == 1
    assert router.audit["rejected_repairs"] == 0


def test_revisao_respeita_o_piso_de_confianca():
    router = router_com_historico(revisar=True)
    plano = router.plan({"scene_id": 1, "turns": []}, {"T0": turno("contextual", "zoe")})
    aceitos = router.replacements(
        {"assignments": [{"id": "T0", "speaker": "R0", "kind": "speech", "confidence": .94}]},
        plano, .9)
    assert aceitos == {}
    assert router.audit["revisao_trocada"] == 0
    assert router.audit["revisao_mantida"] == 1


def test_versao_do_audit_diz_qual_comportamento_rodou():
    assert router_com_historico(revisar=True).audit["version"] == "hybrid-speaker-router-v1.2"
    assert router_com_historico(revisar=False).audit["version"] == "hybrid-speaker-router-v1.1"
