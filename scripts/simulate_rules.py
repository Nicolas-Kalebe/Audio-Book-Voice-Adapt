"""Bancada de regras offline: mede ganho E perda de cada regra sem GPU.

Reaproveita o analysis.json de uma rodada fria, aplica regras deterministicas de
pos-processamento sobre as decisoes ja tomadas e reavalia. Nao chama o modelo,
nao invalida cache e nao precisa do Ollama, entao da para iterar dezenas de vezes
sem depender da agenda de quem tem a GPU.

Cada regra reporta disparos, ganhos e PERDAS separados. Delta liquido esconde
troca de dez por oito; uma regra que conserta 13 e quebra 9 nao presta.

Uso:
    python scripts/simulate_rules.py --analysis output/<pasta>/analysis.json
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path

from audiobook_voice_enhancer.benchmark import _fold, _role_key, evaluate, load_gold
from audiobook_voice_enhancer.dialogue import NAME

VOCATIVE_OPENERS = r"salve|ola|olá|adeus|parabens|parabéns|obrigad[oa]|escute|escuta|diga|veja|ouca|ouça"


def is_addressed(text: str, name: str) -> bool:
    """O nome aparece como VOCATIVO no proprio texto da fala.

    Quem e chamado dentro da fala e o destinatario, nunca o falante. Exige
    pontuacao antes do nome para nao confundir com mencao: em "alem de Vasemir,
    esta invernando" o nome e assunto, nao chamamento.
    """
    escaped = "|".join(re.escape(part) for part in sorted({name, name.split()[0]}, key=len, reverse=True))
    return bool(
        re.search(rf"^(?:{VOCATIVE_OPENERS})?\s*,?\s*(?:{escaped})\s*[,!?]", text.strip(), re.I)
        or re.search(rf"[,!?]\s*(?:{escaped})\s*(?:[,!?]|$)", text, re.I)
        or re.fullmatch(rf"\s*(?:{escaped})\s*[.!?]?\s*", text.strip(), re.I))


def rule_sandwich(turns, entities, max_speakers=2, window=6):
    """T-1 == T == T+1 num trecho de dois falantes: o do meio e do outro.

    Tres turnos seguidos da mesma pessoa nao e dialogo. A regra nao inventa
    ninguem: reusa o falante diferente mais recente da propria cena. Ancora
    textual explicita nunca e sobrescrita, e fora de um trecho de dois falantes
    a regra nao age — foi medindo isso que as perdas cairam de 9 para 4.
    """
    changes = {}
    by_scene: dict[int, list] = {}
    for turn in turns:
        by_scene.setdefault(turn["scene_id"], []).append(turn)
    for sequence in by_scene.values():
        spoken = [t for t in sequence if t["speaker_entity_id"] and t["kind"] == "speech"]
        for index in range(1, len(spoken) - 1):
            before, target, after = spoken[index - 1], spoken[index], spoken[index + 1]
            if before["speaker_entity_id"] != target["speaker_entity_id"]:
                continue
            if after["speaker_entity_id"] != target["speaker_entity_id"]:
                continue
            if target["status"] == "explicit":
                continue
            local = spoken[max(0, index - window):index + window]
            if len({t["speaker_entity_id"] for t in local}) > max_speakers:
                continue
            other = next((t["speaker_entity_id"] for t in reversed(spoken[max(0, index - window):index - 1])
                          if t["speaker_entity_id"] != target["speaker_entity_id"]), None)
            if other:
                changes[target["id"]] = other
    return changes


def rule_vocative(turns, entities, max_speakers=2, window=6):
    """Quem e chamado dentro da fala nao e quem fala.

    Rejeitar so troca erro por abstencao, e abstencao custa cobertura; por isso
    a regra so age quando o trecho tem dois falantes e existe outro a quem
    atribuir. Fora disso deixa como esta, para nao trocar acerto por recuo.
    """
    changes = {}
    by_scene: dict[int, list] = {}
    for turn in turns:
        by_scene.setdefault(turn["scene_id"], []).append(turn)
    for sequence in by_scene.values():
        spoken = [t for t in sequence if t["speaker_entity_id"] and t["kind"] == "speech"]
        for index, target in enumerate(spoken):
            if target["status"] == "explicit":
                continue
            entity = entities[target["speaker_entity_id"]]
            text = " ".join(f["text"] for f in target["fragments"])
            if not any(is_addressed(text, alias) for alias in entity["aliases"]):
                continue
            local = spoken[max(0, index - window):index + window]
            if len({t["speaker_entity_id"] for t in local}) > max_speakers:
                continue
            other = next((t["speaker_entity_id"] for t in reversed(spoken[max(0, index - window):index])
                          if t["speaker_entity_id"] != target["speaker_entity_id"]), None)
            if other:
                changes[target["id"]] = other
    return changes


def partial_name_links(entities):
    """Nome curto que e prefixo de exatamente UM nome completo e a mesma pessoa.

    "Radcliffe" e "Radcliffe de Oxenfurt" sao duas entidades no catalogo e uma
    pessoa no livro. Exigir candidato UNICO preserva a doutrina: primeiro nome
    compartilhado entre duas pessoas ("Iara Silva" e "Iara Costa") nao funde
    ninguem, porque ali ha dois candidatos.
    """
    named = [e for e in entities.values() if e["kind"] == "named"]
    links = {}
    for short in named:
        tokens = _fold(short["name"]).split()
        longer = [e for e in named
                  if e["id"] != short["id"] and _fold(e["name"]).split()[:len(tokens)] == tokens
                  and len(_fold(e["name"]).split()) > len(tokens)]
        if len(longer) == 1:
            links[short["id"]] = longer[0]["id"]
    return links


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--gold", type=Path, default=Path("benchmarks/part01_gold.yaml"))
    args = parser.parse_args()

    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    gold = load_gold(args.gold)
    chapter = analysis["files"][0]
    model = chapter["book_speaker_analysis"]
    entities = {e["id"]: e for e in model["entities"]}
    turns = sorted(model["turns"], key=lambda t: (t["scene_id"], t["fragments"][0]["paragraph"]))
    by_candidate = {f["candidate_id"]: t["id"] for t in turns for f in t["fragments"]}
    current = {t["id"]: t["speaker_entity_id"] for t in turns}

    spoken = {str(i): s for s, ids in gold["spoken_by"].items() for i in ids}
    for label, detail in (gold.get("ambiguous_spoken") or {}).items():
        for item in detail.get("ids", []):
            spoken[str(item)] = label
    expected = {}
    for turn in turns:
        for fragment in turn["fragments"]:
            if fragment["candidate_id"] in spoken:
                expected[turn["id"]] = spoken[fragment["candidate_id"]]
                break

    def report(changes: dict[str, str]) -> tuple[int, int]:
        gained = lost = 0
        for turn_id, new in changes.items():
            want = expected.get(turn_id)
            if not want:
                continue
            was = entities.get(current[turn_id], {}).get("display_name")
            before = bool(was) and _role_key(was) == _role_key(want)
            after = _role_key(entities[new]["display_name"]) == _role_key(want)
            gained += after and not before
            lost += before and not after
        return gained, lost

    def rescore(changes: dict[str, str], links: dict[str, str], label: str):
        report_copy = copy.deepcopy({"files": [{"dialogues": chapter["dialogues"]}]})
        for dialogue in report_copy["files"][0]["dialogues"]:
            turn_id = by_candidate.get(str(dialogue["id"]))
            identity = changes.get(turn_id, current.get(turn_id))
            identity = links.get(identity, identity)
            if identity:
                dialogue["speaker"] = entities[identity]["display_name"]
        metrics = evaluate(gold, report_copy)
        row = next(c for c in metrics["by_class"] if c["class"] == "dublavel")
        target_ok = row["precision_by_identity"] >= .95 and row["coverage"] >= .95
        print(f"{label:38s} certos {row['correct_by_identity']:3d}  errados {row['wrong_by_identity']:3d}"
              f"  precisao {row['precision_by_identity'] * 100:6.2f}%"
              f"  cobertura {row['coverage'] * 100:6.2f}%  {'META OK' if target_ok else ''}")
        return row

    print("Alvo: precisao >= 95% e cobertura >= 95% sobre os dublaveis.\n")
    rescore({}, {}, "base (rodada original)")
    links = partial_name_links(entities)
    print(f"\nnomes curtos ligados ao completo: "
          f"{[(entities[a]['name'], entities[b]['name']) for a, b in links.items()] or 'nenhum'}")
    rescore({}, links, "so nome curto -> completo")

    for name, rule in (("vocativo", rule_vocative), ("sanduiche", rule_sandwich)):
        changes = rule(turns, entities)
        gained, lost = report(changes)
        print(f"\n{name}: {len(changes)} disparos, GANHOS {gained}, PERDAS {lost}")
        rescore(changes, links, f"nome + {name}")

    combined = {**rule_vocative(turns, entities), **rule_sandwich(turns, entities)}
    gained, lost = report(combined)
    print(f"\ncombinado: {len(combined)} disparos, GANHOS {gained}, PERDAS {lost}")
    rescore(combined, links, "nome + vocativo + sanduiche")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
