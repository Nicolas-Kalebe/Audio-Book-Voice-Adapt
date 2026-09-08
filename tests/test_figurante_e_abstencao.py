"""As duas decisoes de produto de 08/09/2026.

1. E melhor nao trocar uma voz do que trocar errado: sem certeza, o turno fica
   sem atribuicao e mantem a voz do narrador. Abstencao nao e erro.
2. Figurante de uma cena so nao precisa de voz.

As duas mudam o que o placar mede, entao ficam travadas por teste.
"""
from __future__ import annotations

from pathlib import Path

from audiobook_voice_enhancer.benchmark import evaluate, load_gold
from audiobook_voice_enhancer.book_speakers import build_book, classify_anonymous, _entity

GOLD = Path(__file__).resolve().parents[1] / "benchmarks" / "part01_gold.yaml"


def test_anonymous_seen_in_one_scene_is_a_figurante():
    model = build_book(["— Sai — disse o guarda alto.", "***", "— Entra — disse a taberneira."])
    _entity(model, "guarda alto", "anonymous", 0, 0)
    _entity(model, "taberneira", "anonymous", 1, 2)
    classify_anonymous(model)
    assert {e["name"]: e["role"] for e in model["entities"].values()} == {
        "guarda alto": "figurante", "taberneira": "figurante"}


def test_anonymous_seen_in_two_scenes_is_not_a_figurante():
    """Anonimo que volta noutra cena e personagem recorrente, nao figurante."""
    model = build_book(["— Sai — disse o guarda alto.", "***", "— Volte — disse o guarda alto."])
    _entity(model, "guarda alto", "anonymous", 0, 0)
    _entity(model, "guarda alto", "anonymous", 1, 2)
    classify_anonymous(model)
    roles = {e["role"] for e in model["entities"].values() if e["kind"] == "anonymous"}
    assert roles == {"anonimo_recorrente"}


def test_named_entities_are_never_figurantes():
    model = build_book(["— Vamos — disse Iara."])
    classify_anonymous(model)
    assert all(e["role"] == "nomeado" for e in model["entities"].values() if e["kind"] == "named")


def _report(gold, decide):
    """Relatorio sintetico: `decide(papel)` devolve o falante emitido, ou None."""
    spoken = {str(i): s for s, ids in gold["spoken_by"].items() for i in ids}
    for label, detail in (gold.get("ambiguous_spoken") or {}).items():
        for item in detail.get("ids", []):
            spoken[str(item)] = label
    standalone = {str(v) for v in gold.get("standalone_quote_turn_ids", [])}
    missing = {str(m["id"]) for m in gold.get("missing_spoken", [])}
    dialogues = []
    for candidate, role in spoken.items():
        if candidate in missing:
            continue
        paragraph = int(candidate.split("-")[0])
        dialogues.append({"id": candidate, "source": "book", "book_paragraph_id": paragraph,
                          "turn_id": None if candidate in standalone else f"book-{paragraph}",
                          "fragment_index": 0, "start": 0.0, "text": "", "speaker": decide(role)})
    for candidate in (str(i) for ids in gold["non_spoken"].values() for i in ids):
        paragraph = int(candidate.split("-")[0])
        dialogues.append({"id": candidate, "source": "book", "book_paragraph_id": paragraph,
                          "turn_id": f"book-{paragraph}-x", "fragment_index": 0,
                          "start": 0.0, "text": "", "speaker": None})
    return {"files": [{"dialogues": dialogues}]}


def test_abstaining_is_not_counted_as_a_wrong_voice():
    """Abster e trocar errado nao podem cair no mesmo contador."""
    gold = load_gold(GOLD)
    calado = evaluate(gold, _report(gold, lambda role: None))
    errado = evaluate(gold, _report(gold, lambda role: "Ninguem Desse Livro"))
    assert calado["speaker_wrong_turns_by_identity"] == 0
    assert calado["speaker_abstained_turns"] == 250
    assert errado["speaker_abstained_turns"] == 0
    assert errado["speaker_wrong_turns_by_identity"] == 250


def test_figurante_turns_leave_the_count_that_decides_the_product():
    gold = load_gold(GOLD)
    metrics = evaluate(gold, _report(gold, lambda role: role))
    classes = {item["class"]: item for item in metrics["by_class"]}
    assert classes["dublavel"]["total"] + classes["figurante"]["total"] == metrics["gold_source_turns"]
    # Sem figurante, o denominador que decide o produto e menor que os 255.
    assert classes["dublavel"]["total"] < metrics["gold_source_turns"]
    assert classes["figurante"]["total"] == 42
