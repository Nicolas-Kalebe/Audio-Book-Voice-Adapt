from __future__ import annotations

import json
import math
import os
import re
import time
from collections import defaultdict
from typing import Any, Callable

import requests

from .cache import Cache
from .dialogue import _addressed_roles, turn_representatives


SYSTEM = """Você atribui falas de um romance aos personagens. Resolva a conversa como uma sequência,
nunca como frases isoladas. Primeiro identifique quem está fisicamente presente; depois marque âncoras
textuais; por fim resolva pronomes, perguntas e respostas mantendo o estado da cena.
Prioridade das evidências: (1) atribuição explícita como 'disse X'; (2) sujeito da ação narrativa
imediatamente anterior; (3) pergunta e resposta adjacentes; (4) continuidade dos participantes.
Um nome chamado dentro da fala é o destinatário, nunca o falante. Se uma resposta chama alguém
pelo nome, use isso para identificar também a pergunta anterior. Não atribua ao ponto de vista de
quem apenas ouviu a fala. Não use alternância cega em cenas com mais de duas pessoas e nunca use
timbre de voz. Um verbo sem sujeito como 'disse', 'indagou' ou 'repetiu' exige resolver o sujeito
pela narração ao redor; ele não significa automaticamente troca de falante. Confiança 0.98 apenas
com atribuição textual explícita, 0.85–0.95 para encadeamento inequívoco e no máximo 0.74 para um
palpite. Escolha apenas allowed_speakers; use null se o texto
não sustentar uma conclusão. Retorne somente JSON no formato solicitado."""

SCENE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "speaker": {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string"},
                },
                "required": ["id", "speaker", "confidence", "reason"],
            },
        }
    },
    "required": ["assignments"],
}


class LLMProvider:
    model: str
    system_prompt = SYSTEM
    response_schema = SCENE_SCHEMA

    def infer(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, timeout: int = 90, reasoning: bool = False):
        self.url, self.model, self.timeout = base_url.rstrip("/"), model, timeout
        self.reasoning = reasoning

    def infer(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            f"{self.url}/api/chat", timeout=self.timeout,
            json={
                "model": self.model, "stream": False, "think": self.reasoning,
                "format": self.response_schema, "keep_alive": "10m",
                "options": {"temperature": 0, "seed": 42, "num_ctx": 32768, "num_predict": 4096},
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
        )
        response.raise_for_status()
        body = response.json()
        self.last_diagnostics = {key: body.get(key) for key in (
            "done", "done_reason", "total_duration", "load_duration", "prompt_eval_count",
            "prompt_eval_duration", "eval_count", "eval_duration")}
        self.last_diagnostics["raw_content"] = body["message"]["content"]
        try:
            result = json.loads(body["message"]["content"])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON; done_reason={body.get('done_reason')}; "
                             f"eval_count={body.get('eval_count')}: {exc}") from exc
        if not isinstance(result, dict):
            raise ValueError("O LLM não devolveu um objeto JSON")
        return result


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, api_key_env: str, timeout: int = 300):
        self.url, self.model, self.key, self.timeout = base_url.rstrip("/"), model, os.getenv(api_key_env, ""), timeout

    def infer(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            f"{self.url}/chat/completions", timeout=self.timeout,
            headers={"Authorization": f"Bearer {self.key}"} if self.key else {},
            json={
                "model": self.model, "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                "temperature": 0,
            },
        )
        response.raise_for_status()
        result = json.loads(response.json()["choices"][0]["message"]["content"])
        if not isinstance(result, dict):
            raise ValueError("O LLM não devolveu um objeto JSON")
        return result


class AnthropicProvider(LLMProvider):
    """Claude via SDK oficial. Só o texto do livro sai da máquina; áudio e vozes ficam locais.

    Um payload {"prompt": str} vai como texto puro; qualquer outro, como JSON.
    """

    def __init__(self, model: str, api_key_env: str = "ANTHROPIC_API_KEY", timeout: int = 900,
                 effort: str = "high", max_tokens: int = 64000):
        import anthropic

        key = os.getenv(api_key_env) or None
        self.client = anthropic.Anthropic(api_key=key, timeout=timeout) if key else anthropic.Anthropic(timeout=timeout)
        self.model, self.timeout, self.effort, self.max_tokens = model, timeout, effort, max_tokens
        self.url = "anthropic"

    def infer(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = payload["prompt"] if set(payload) == {"prompt"} else json.dumps(payload, ensure_ascii=False)
        # O system prompt é fixo e vai em cache; o livro varia a cada janela.
        with self.client.beta.messages.stream(
            model=self.model, max_tokens=self.max_tokens,
            system=[{"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
            output_config={"effort": self.effort,
                           "format": {"type": "json_schema", "schema": self.response_schema}},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        ) as stream:
            message = stream.get_final_message()
        usage = message.usage
        self.last_diagnostics = {
            "model": message.model, "stop_reason": message.stop_reason, "request_id": message._request_id,
            "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None)}
        if message.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            raise ValueError(f"Recusa do modelo: {getattr(details, 'category', None)}")
        if message.stop_reason == "max_tokens":
            raise ValueError(f"Resposta cortada em max_tokens={self.max_tokens}")
        text = next((block.text for block in message.content if block.type == "text"), "")
        self.last_diagnostics["raw_content"] = text
        result = json.loads(text)
        if not isinstance(result, dict):
            raise ValueError("O LLM não devolveu um objeto JSON")
        return result


class PendingExchange(RuntimeError):
    """Pedido gravado para um agente externo; o pipeline para antes de converter."""


class ExchangeProvider(LLMProvider):
    """Ponte por arquivos: o app grava o pedido, um agente externo (o Claude Code com
    o login do usuário) escreve a resposta, e a próxima execução a consome.

    Sem resposta, levanta PendingExchange em vez de seguir com turnos sem voz: um
    lote não respondido não pode virar áudio convertido pela metade.
    """

    def __init__(self, exchange_dir: str | os.PathLike, model: str):
        from pathlib import Path

        self.directory, self.model, self.url = Path(exchange_dir), model, "exchange"

    def infer(self, payload: dict[str, Any]) -> dict[str, Any]:
        import hashlib

        content = payload["prompt"] if set(payload) == {"prompt"} else json.dumps(payload, ensure_ascii=False)
        schema = json.dumps(self.response_schema, ensure_ascii=False, indent=1)
        digest = hashlib.sha256("\n".join((self.system_prompt, schema, content)).encode("utf-8")).hexdigest()[:16]
        response = self.directory / f"response-{digest}.json"
        if response.is_file():
            result = json.loads(response.read_text(encoding="utf-8"))
            if not isinstance(result, dict):
                raise ValueError(f"{response.name} não é um objeto JSON")
            return result
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"request-{digest}.md").write_text(
            "# SYSTEM\n\n" + self.system_prompt + "\n\n# USER\n\n" + content
            + "\n# FORMATO DE SAÍDA (JSON Schema)\n\n" + schema + "\n", encoding="utf-8")
        raise PendingExchange(f"Aguardando {response}")


def build_provider(config: dict[str, Any]) -> LLMProvider | None:
    if not config.get("enabled") or not config.get("model"):
        return None
    timeout = int(config.get("timeout_seconds", 300))
    if config.get("provider") == "exchange":
        return ExchangeProvider(config.get("exchange_dir", "output/exchange"), config["model"])
    if config.get("provider") == "anthropic":
        return AnthropicProvider(config["model"], config.get("api_key_env", "ANTHROPIC_API_KEY"),
                                 max(timeout, 900), config.get("effort", "high"),
                                 int(config.get("max_tokens", 64000)))
    if config.get("provider") == "ollama":
        return OllamaProvider(config.get("base_url", "http://localhost:11434"), config["model"], timeout,
                              bool(config.get("reasoning", False)))
    return OpenAICompatibleProvider(config["base_url"], config["model"],
                                    config.get("api_key_env", "OPENAI_API_KEY"), timeout)


def review_cache_identity(provider: LLMProvider | None) -> tuple[Any, ...]:
    return ("scene-speaker-review-v5-blind", type(provider).__name__,
            getattr(provider, "url", None), getattr(provider, "model", None),
            getattr(provider, "reasoning", None), SYSTEM, SCENE_SCHEMA)


def cached_infer(provider: LLMProvider, cache: Cache, payload: dict[str, Any]) -> dict[str, Any]:
    key = cache.digest(review_cache_identity(provider), provider.system_prompt, provider.response_schema, payload)
    def invoke():
        provider.last_diagnostics = {}
        started = time.monotonic()
        error = None
        try:
            return provider.infer(payload)
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            diagnostics = {**provider.last_diagnostics, "error": error,
                           "elapsed_seconds": time.monotonic() - started}
            cache.path("llm_diagnostics", key).write_text(
                json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache.json("llm", key, invoke)


def _confidence(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return score if not isinstance(value, bool) and math.isfinite(score) and 0 <= score <= 1 else 0.0


def _decisions(assignments: list[Any]) -> dict[str, dict[str, Any]]:
    """Conflicting/duplicate IDs and malformed speakers cannot become anchors."""
    result: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for item in assignments:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        identifier = item["id"]
        if identifier in result:
            duplicates.add(identifier)
        result[identifier] = item
    return {key: item for key, item in result.items() if key not in duplicates
            and (item.get("speaker") is None or isinstance(item.get("speaker"), str))}


def _speaker_is_directly_addressed(text: str, speaker: str) -> bool:
    name = re.escape(speaker)
    return bool(
        re.search(rf"^(?:salve|olá|adeus|parabéns)?\s*,?\s*{name}\s*[,!?]", text.strip(), re.I)
        or re.search(rf"[,!?]\s*{name}\s*(?:[,!?]|$)", text, re.I)
        or re.fullmatch(rf"\s*{name}\s*[.!?]??\s*", text, re.I)
    )


def review_scenes(provider: LLMProvider, cache: Cache, dialogues: list[dict[str, Any]],
                  book_blocks: list[str], known_characters: set[str], threshold: float,
                  progress: Callable[[int, int], None] | None = None,
                  automatic_threshold: float = 0.98, critic_enabled: bool = True,
                  consensus_threshold: float = 0.9) -> dict[str, Any]:
    """Review unresolved dialogue in one request per scene, using book text only."""
    started = time.monotonic()
    turns = turn_representatives(dialogues)
    pending_by_scene: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for dialogue in turns:
        if (not dialogue.get("manually_confirmed") and dialogue.get("dialogue_style") != "quote"
                and (not dialogue.get("speaker") or float(dialogue.get("speaker_confidence", 0)) < threshold)):
            pending_by_scene[int(dialogue.get("scene_id", -1))].append(dialogue)

    known = {name for name in known_characters if name and not name.startswith("__")}
    known.update(str(item["speaker"]) for item in dialogues if item.get("speaker"))
    batches: list[tuple[int, list[dict[str, Any]]]] = []
    for scene_id, pending in sorted(pending_by_scene.items()):
        current: list[dict[str, Any]] = []
        previous_paragraph: int | None = None
        for item in pending:
            paragraph = int(item.get("book_paragraph_id", -1))
            if current and previous_paragraph is not None and paragraph >= 0 and paragraph - previous_paragraph >= 8:
                batches.append((scene_id, current))
                current = []
            current.append(item)
            previous_paragraph = paragraph
        if current:
            batches.append((scene_id, current))

    stats: dict[str, Any] = {
        "provider": provider.__class__.__name__, "model": provider.model,
        "scenes_reviewed": len(pending_by_scene), "batches_reviewed": 0,
        "dialogues_reviewed": 0, "assigned": 0,
        "suggested_for_review": 0, "unresolved": 0, "critic_batches": 0,
        "critic_agreements": 0, "critic_disagreements": 0, "errors": [],
        "review_method": "blind_second_reading" if critic_enabled else "single_reading",
        "confidence_is_calibrated": False,
    }
    for position, (scene_id, pending) in enumerate(batches, 1):
        if progress:
            progress(position, len(batches))
        ids = [int(item.get("book_paragraph_id", -1)) for item in pending
               if int(item.get("book_paragraph_id", -1)) >= 0]
        if ids and book_blocks:
            first, last = max(0, min(ids) - 8), min(len(book_blocks), max(ids) + 9)
            context = [{"paragraph": index, "text": book_blocks[index]} for index in range(first, last)]
        else:
            unique: list[str] = []
            for item in pending:
                for text in item.get("book_context", []):
                    if text and text not in unique:
                        unique.append(text)
            context = [{"paragraph": index, "text": text} for index, text in enumerate(unique)]
        first_context = int(context[0]["paragraph"]) if context else -1
        last_context = int(context[-1]["paragraph"]) if context else -1
        scene_dialogues = [item for item in turns if int(item.get("scene_id", -1)) == scene_id
                           and (first_context < 0 or first_context <= int(item.get("book_paragraph_id", -1)) <= last_context)]
        whole_scene = [item for item in turns if int(item.get("scene_id", -1)) == scene_id]
        local_speakers = {str(item["speaker"]) for item in whole_scene
                          if item.get("speaker") and float(item.get("speaker_confidence", 0)) >= .9}
        local_speakers.update(role for item in whole_scene for role in _addressed_roles(item.get("text", "")))
        for name in known:
            if any(_speaker_is_directly_addressed(item.get("text", ""), name) for item in whole_scene):
                local_speakers.add(name)
        allowed = local_speakers if len(local_speakers) >= 2 else known
        payload = {
            "task": ("Atribua cada target_dialogue usando somente este trecho local. "
                     "Personagens apenas mencionados como ausentes não estão presentes e não podem falar."),
            "allowed_speakers": sorted(allowed, key=str.casefold),
            "scene_participants_from_text": sorted(local_speakers, key=str.casefold),
            "scene_id": scene_id,
            "scene_text": context,
            "known_dialogues": [
                {"id": str(item["id"]), "text": item.get("text", ""),
                 "speaker": item.get("speaker"), "confidence": item.get("speaker_confidence", 0)}
                for item in scene_dialogues if item.get("speaker") and item not in pending
            ],
            "target_dialogues": [
                {"id": str(item["id"]), "paragraph": item.get("book_paragraph_id"),
                 "text": item.get("text", "")}
                for item in pending
            ],
            "chronological_dialogues": [
                {"id": str(item["id"]), "paragraph": item.get("book_paragraph_id"),
                 "text": item.get("text", ""), "speaker_if_anchored": item.get("speaker") if item not in pending else None,
                 "anchor_reason": item.get("reason", "") if item.get("speaker") and item not in pending else "",
                 "is_target": item in pending}
                for item in scene_dialogues
            ],
        }
        stats["batches_reviewed"] += 1
        stats["dialogues_reviewed"] += len(pending)
        try:
            answer = cached_infer(provider, cache, payload)
            assignments = answer.get("assignments", [])
            if not isinstance(assignments, list):
                raise ValueError("campo assignments ausente na resposta")
            by_id = _decisions(assignments)
            critic_by_id: dict[str, dict[str, Any]] = {}
            if critic_enabled:
                critic_payload = dict(payload)
                critic_payload["task"] = (
                    "Faça uma segunda leitura do texto, sem acesso a propostas anteriores. "
                    "Para cada target_dialogue procure evidências contra cada candidato: "
                    "ausência na cena, nome usado como destinatário e sujeito de outro verbo. "
                    "Atribua somente quando o texto sustentar a identidade; caso contrário, use null."
                )
                critic_payload["review_pass"] = "blind_second_reading"
                critic_answer = cached_infer(provider, cache, critic_payload)
                critic_assignments = critic_answer.get("assignments", [])
                if not isinstance(critic_assignments, list):
                    raise ValueError("campo assignments ausente na crítica")
                critic_by_id = _decisions(critic_assignments)
                stats["critic_batches"] += 1
            for dialogue in pending:
                decision = by_id.get(str(dialogue["id"]), {})
                speaker = decision.get("speaker")
                confidence = _confidence(decision.get("confidence", 0))
                reason = str(decision.get("reason", "")).strip()
                agreed = False
                if critic_enabled:
                    critique = critic_by_id.get(str(dialogue["id"]), {})
                    critic_speaker = critique.get("speaker")
                    critic_confidence = _confidence(critique.get("confidence", 0))
                    agreed = bool(speaker and critic_speaker == speaker)
                    if agreed:
                        confidence = min(confidence, critic_confidence)
                        stats["critic_agreements"] += 1
                    elif speaker or critic_speaker:
                        stats["critic_disagreements"] += 1
                        dialogue["llm_alternative"] = critic_speaker
                        dialogue["llm_alternative_confidence"] = round(critic_confidence, 4)
                if speaker not in allowed:
                    speaker = None
                    confidence = 0.0
                elif _speaker_is_directly_addressed(dialogue.get("text", ""), speaker):
                    dialogue["llm_rejected_reason"] = "a IA escolheu o personagem chamado dentro da fala"
                    speaker = None
                    confidence = 0.0
                if speaker:
                    dialogue["llm_suggestion"] = speaker
                    dialogue["llm_confidence"] = round(confidence, 4)
                    dialogue["llm_reason"] = reason
                # Agreement from the same model is not calibrated correctness.
                acceptance_threshold = max(automatic_threshold, consensus_threshold) if agreed else automatic_threshold
                if speaker and confidence > 0 and confidence >= acceptance_threshold and (agreed or not critic_enabled):
                    dialogue["speaker"] = speaker
                    dialogue["speaker_confidence"] = round(confidence, 4)
                    dialogue["reason"] = f"IA contextual do livro: {reason}"
                    stats["assigned"] += 1
                elif speaker:
                    stats["suggested_for_review"] += 1
                else:
                    stats["unresolved"] += 1
        except Exception as exc:
            stats["errors"].append({"scene_id": scene_id, "error": str(exc)})
            stats["unresolved"] += len(pending)
    stats["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return stats
