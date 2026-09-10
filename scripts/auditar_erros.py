"""Lista os erros de atribuição com contexto, para uma pessoa auditar o gabarito.

Os números dizem QUANTOS erros existem. Esta ferramenta diz QUAIS são, onde caem e
o que estava escrito ao redor — que é o que decide se o motor errou ou se o rótulo
está errado. O gabarito da Parte 03 declara
`annotation_review: assistant_authored_not_independently_audited`, e nenhuma pessoa
conferiu esses turnos contra o livro até hoje.

Não consulta o motor nem propõe correção: só organiza o que já foi medido.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from audiobook_voice_enhancer.benchmark import evaluate, load_gold
from audiobook_voice_enhancer.speaker_differential import turn_outcomes


def _texto(turno):
    return " ".join(part.get("text", "") for part in turno.get("fragments", [])).strip()


def _turnos_do_analysis(analysis):
    """Todos os turnos da camada textual, em ordem de parágrafo."""
    turnos = []
    for chapter in analysis.get("files", []):
        textual = chapter.get("book_speaker_analysis") or {}
        turnos.extend(textual.get("turns", []))
    return sorted(turnos, key=lambda turno: min(
        (part["paragraph"] for part in turno.get("fragments", [])), default=0))


def coletar(gold, analysis, contexto=2):
    """Um registro por erro: o que se esperava, o que saiu e o que havia em volta."""
    resultado = evaluate(gold, analysis)
    saidas = turn_outcomes(gold, analysis)
    turnos = _turnos_do_analysis(analysis)
    nomes = {}
    for chapter in analysis.get("files", []):
        for entity in (chapter.get("book_speaker_analysis") or {}).get("entities", []):
            nomes[entity["id"]] = entity["name"]
    por_paragrafo = {min((p["paragraph"] for p in t.get("fragments", [])), default=-1): i
                     for i, t in enumerate(turnos)}

    linhas = []
    for item in resultado.get("wrong_or_unassigned", []):
        saida = saidas.get(item["id"], {})
        # Figurante sai por decisão do proprietário (08/09/2026): não entra na
        # conta que decide o produto, então também não entra na fila de auditoria.
        if saida.get("class") == "figurante":
            continue
        indice = por_paragrafo.get(item["paragraph"])
        vizinhos = []
        if indice is not None:
            comeco = max(0, indice - contexto)
            for outro in turnos[comeco:indice + contexto + 1]:
                paragrafo = min((p["paragraph"] for p in outro.get("fragments", [])), default=-1)
                vizinhos.append({
                    "paragrafo": paragrafo,
                    "alvo": paragrafo == item["paragraph"],
                    "falante": nomes.get(outro.get("speaker_entity_id"), outro.get("speaker_entity_id")),
                    "status": outro.get("status"),
                    "regra": outro.get("consistency_rule"),
                    "texto": _texto(outro),
                })
        linhas.append({
            "id": item["id"],
            "paragrafo": item["paragraph"],
            "cena": saida.get("scene"),
            "esperado": item["expected"],
            "predito": item["predicted"],
            # Sem predito é ABSTENÇÃO: o turno ficou com a voz do narrador. É outro
            # desfecho, não um erro — e some no mesmo balde se ninguém separar.
            "desfecho": "erro" if item["predicted"] else "abstencao",
            "confianca": saida.get("confidence"),
            "status": saida.get("status"),
            "regra_consistencia": saida.get("consistency_rule"),
            "review_issue": saida.get("review_issue"),
            "texto": item.get("text", ""),
            "contexto": vizinhos,
        })
    linhas.sort(key=lambda linha: linha["paragrafo"])
    return {"gold": resultado.get("gold"), "linhas": linhas,
            "metricas": {chave: resultado.get(chave) for chave in (
                "speaker_correct_turns", "speaker_wrong_turns", "speaker_abstained_turns",
                "speaker_assigned_turns", "speaker_accuracy_when_assigned")}}


def render_markdown(relatorio, contexto=2):
    erros = [linha for linha in relatorio["linhas"] if linha["desfecho"] == "erro"]
    abstencoes = [linha for linha in relatorio["linhas"] if linha["desfecho"] == "abstencao"]
    linhas = [
        f"# Auditoria dos erros — {relatorio['gold']}", "",
        "Cada bloco traz o turno errado e os vizinhos, com o falante que o motor "
        "atribuiu a cada um. A pergunta a responder em cada caso é uma só: **o motor "
        "errou, ou o rótulo do gabarito está errado?**", "",
        f"- Erros (voz trocada): **{len(erros)}**",
        f"- Abstenções (ficou sem voz): **{len(abstencoes)}**", "",
    ]

    por_cena = Counter(str(linha["cena"]) for linha in erros)
    if por_cena:
        linhas.extend(["## Erros por cena", "", "| Cena | Erros |", "|---|---:|"])
        linhas.extend(f"| {cena} | {total} |" for cena, total in
                      sorted(por_cena.items(), key=lambda item: -item[1]))
        linhas.append("")

    por_regra = Counter(linha["regra_consistencia"] or "sem_regra" for linha in erros)
    if por_regra:
        linhas.extend([
            "## Erros por regra que escreveu a voz", "",
            "`sem_regra` veio da primeira leitura. O resto passou por uma regra de "
            "consistência que teve a chance de decidir e decidiu errado.", "",
            "| Regra | Erros |", "|---|---:|"])
        linhas.extend(f"| {regra} | {total} |" for regra, total in
                      sorted(por_regra.items(), key=lambda item: -item[1]))
        linhas.append("")

    confusoes = Counter((linha["esperado"], linha["predito"]) for linha in erros)
    if confusoes:
        linhas.extend(["## Trocas mais frequentes", "",
                       "| Esperado | Saiu | Vezes |", "|---|---|---:|"])
        linhas.extend(f"| {esperado} | {predito} | {total} |"
                      for (esperado, predito), total in confusoes.most_common(10))
        linhas.append("")

    linhas.extend(["## Um a um", ""])
    for linha in erros:
        linhas.extend([
            f"### {linha['id']} — parágrafo {linha['paragrafo']} (cena {linha['cena']})", "",
            f"- Gabarito diz: **{linha['esperado']}**",
            f"- Motor disse: **{linha['predito']}**"
            + (f" (confiança {linha['confianca']})" if linha["confianca"] is not None else ""),
            f"- Regra que escreveu: `{linha['regra_consistencia'] or 'sem_regra'}`"
            + (f" · `{linha['review_issue']}`" if linha["review_issue"] else ""),
            "", "| | Parágrafo | Falante atribuído | Texto |", "|---|---:|---|---|",
        ])
        for vizinho in linha["contexto"]:
            marca = "**→**" if vizinho["alvo"] else ""
            texto = (vizinho["texto"] or "").replace("|", "\\|")
            if len(texto) > 160:
                texto = texto[:157] + "…"
            linhas.append(
                f"| {marca} | {vizinho['paragrafo']} | {vizinho['falante'] or '—'} | {texto} |")
        linhas.extend(["", "Veredito ( ) motor errou ( ) gabarito errado ( ) em dúvida", ""])
    return "\n".join(linhas)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--contexto", type=int, default=2,
                        help="quantos turnos antes e depois mostrar (padrão 2)")
    args = parser.parse_args()

    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    relatorio = coletar(load_gold(args.gold), analysis, contexto=args.contexto)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "auditoria-erros.md").write_text(
        render_markdown(relatorio, args.contexto), encoding="utf-8")
    (args.output / "auditoria-erros.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    colunas = ["id", "paragrafo", "cena", "desfecho", "esperado", "predito",
               "confianca", "status", "regra_consistencia", "review_issue", "texto"]
    with (args.output / "auditoria-erros.csv").open(
            "w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=colunas, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(relatorio["linhas"])
    print(render_markdown(relatorio, args.contexto))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
