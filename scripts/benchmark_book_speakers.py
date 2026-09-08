"""Replay the text-first engine against cached ASR; use a fresh output directory."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

from audiobook_voice_enhancer.benchmark import evaluate, load_gold, render_markdown
from audiobook_voice_enhancer.book import load_book, paragraphs
from audiobook_voice_enhancer.book_speakers import build_book, review_book, project_to_audio, scoped_report, VERSION
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.config import load_config
from audiobook_voice_enhancer.dialogue import detect
from audiobook_voice_enhancer.llm import build_provider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("book", "transcription", "alignment", "config", "gold", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--without-llm", action="store_true")
    parser.add_argument("--protocol", choices=("compact", "evidence", "scene", "lightweight"), default=None)
    parser.add_argument("--no-scene-repair", action="store_true", help="Isola cadastro/contexto da segunda leitura seletiva")
    parser.add_argument('--source-subjects', action='store_true', help='Testa referências literais do narrador no compacto')
    args = parser.parse_args()
    if args.source_subjects and args.protocol != 'compact':
        parser.error('--source-subjects exige --protocol compact')
    if args.output.exists():
        parser.error("Escolha uma pasta de saída nova para garantir cache de respostas vazio")
    # Reserve before warmup: two launches cannot both start into the same output.
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error("A pasta já foi reservada por outra execução")
    config = load_config(args.config)
    if not args.without_llm and (config["llm"].get("provider") != "ollama" or
                                urlsplit(config["llm"]["base_url"]).hostname not in {"localhost", "127.0.0.1", "::1"}):
        parser.error("Este teste usa somente Ollama local")
    started = time.perf_counter()
    blocks = paragraphs(load_book(args.book))
    model = build_book(blocks, {})
    build_seconds = time.perf_counter() - started
    transcript = json.loads(args.transcription.read_text(encoding="utf-8"))
    alignments = json.loads(args.alignment.read_text(encoding="utf-8"))
    anchors = [int(item["book_paragraph_id"]) for item in alignments if item.get("alignment_confidence", 0) >= .5]
    if not anchors:
        parser.error("Cache de alinhamento sem âncoras confiáveis")
    scope = (min(anchors), max(anchors))
    gold = load_gold(args.gold)
    provider = None if args.without_llm else build_provider(config["llm"])
    if not args.without_llm and provider is None:
        parser.error("Ative o LLM na configuração ou use --without-llm")
    warm_seconds = 0.0
    model_metadata = None
    if provider:
        response = requests.get(provider.url.rstrip("/") + "/api/tags", timeout=10)
        response.raise_for_status()
        model_metadata = response.json()
        print("Carregando Qwen antes da medição do capítulo", flush=True)
        warm = copy.copy(provider)
        warm.timeout = max(300, warm.timeout)
        warm_started = time.perf_counter()
        warm.infer({"task": "Atribua a fala ao nome explícito.", "allowed_speakers": ["Iara"],
                    "scene_text": [{"paragraph": 0, "text": "— Abra a porta — disse Iara."}],
                    "target_dialogues": [{"id": "warmup", "text": "Abra a porta", "paragraph": 0}]})
        warm_seconds = time.perf_counter() - warm_started
    cache = Cache(args.output / "cache")
    options = dict(config.get("book_first", {}))
    if args.protocol:
        options["protocol"] = args.protocol
    if args.no_scene_repair:
        options["scene_repair"] = False
    if args.source_subjects:
        options['source_subjects'] = True
    reviewed = review_book(model, provider, cache, scope,
                           threshold=float(options.get("automatic_confidence", .90)),
                           max_turns=int(options.get("max_turns_per_window", 24)),
                           max_chars=int(options.get("max_context_characters", 14000)),
                           protocol=options.get("protocol", "evidence"),
                           source_subjects=bool(options.get('source_subjects', False)),
                           scene_max_chars=int(options.get("scene_context_characters", 36000)),
                           scene_repair=bool(options.get("scene_repair", True)),
                           progress=lambda index, total: print(f"Livro: bloco {index}/{total}", flush=True))
    found = detect(transcript, alignments, {}, blocks)
    project_to_audio(reviewed, found)
    report = {"files": [{"dialogues": found, "book_speaker_analysis": scoped_report(reviewed, scope)}]}
    metrics = evaluate(gold, report)
    # Score structurally readable proposals separately, before confidence/anchor
    # policy. Keep the same frozen labels; no opportunistic alias reconciliation.
    raw_model = copy.deepcopy(reviewed)
    for turn in raw_model["turns"]:
        proposal = turn.get("proposal", {})
        valid = proposal.get("structurally_valid", proposal.get("speaker_entity_id") in raw_model["entities"])
        identity = proposal.get("speaker_entity_id") if valid and proposal.get("kind") == "speech" else None
        turn.update(speaker_entity_id=identity, confidence=proposal.get("confidence", 0) if identity else 0,
                    status="raw_proposal", evidence=[])
    raw_found = copy.deepcopy(found)
    project_to_audio(raw_model, raw_found)
    raw_metrics = evaluate(gold, {"files": [{"dialogues": raw_found}]})
    report.update(benchmark=metrics, raw_proposal_benchmark=raw_metrics, version=VERSION, protocol="development_regression_no_aliases_or_overrides",
                  model_metadata=model_metadata, configuration=options,
                  review=reviewed["review"], model_load_seconds=round(warm_seconds, 3),
                  book_build_seconds=round(build_seconds, 3), cache={"hits": cache.hits, "misses": cache.misses},
                  asr_and_conversion_executed=False,
                  cold_response_cache_valid=cache.hits == 0,
                  input_sha256={name: hashlib.sha256(getattr(args, name).read_bytes()).hexdigest()
                                for name in ("book", "transcription", "alignment", "config", "gold")},
                  scoring_note="Comparação literal com gabarito congelado; rótulos anônimos não são reconciliados automaticamente.")
    (args.output / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "report.md").write_text(render_markdown(metrics), encoding="utf-8")
    print(json.dumps({"correct": metrics["speaker_correct_turns"], "total": metrics["gold_source_turns"],
                      "assigned": metrics["speaker_assigned_turns"], "review": reviewed["review"],
                      "cache": report["cache"]}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
