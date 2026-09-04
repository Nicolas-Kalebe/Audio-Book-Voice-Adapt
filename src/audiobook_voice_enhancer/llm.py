from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from typing import Any, Callable

import requests

from .cache import Cache


SYSTEM = """Você atribui falas de um romance aos personagens. Analise a cena cronologicamente.
Prioridade das evidências: (1) atribuição explícita como 'disse X'; (2) sujeito da ação narrativa
imediatamente anterior; (3) pergunta e resposta adjacentes; (4) continuidade dos participantes.
Um nome chamado dentro da fala é o destinatário, nunca o falante. Se uma resposta chama alguém
pelo nome, use isso para identificar também a pergunta anterior. Não atribua ao ponto de vista de
quem apenas ouviu a fala. Não use alternância cega em cenas com mais de duas pessoas e nunca use
timbre de voz. Confiança 0.98 apenas com atribuição textual explícita, 0.85–0.95 para encadeamento
inequívoco e no máximo 0.74 para um palpite. Escolha apenas allowed_speakers; use null se o texto
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
                "format": SCENE_SCHEMA, "keep_alive": "10m",
                "options": {"temperature": 0, "seed": 42, "num_ctx": 32768, "num_predict": 4096},
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
        )
        response.raise_for_status()
        result = json.loads(response.json()["message"]["content"])
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
                    {"role": "system", "content": SYSTEM},
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


def build_provider(config: dict[str, Any]) -> LLMProvider | None:
    if not config.get("enabled") or not config.get("model"):
        return None
    timeout = int(config.get("timeout_seconds", 300))
    if config.get("provider") == "ollama":
        return OllamaProvider(config.get("base_url", "http://localhost:11434"), config["model"], timeout,
                              bool(config.get("reasoning", False)))
    return OpenAICompatibleProvider(config["base_url"], config["model"],
                                    config.get("api_key_env", "OPENAI_API_KEY"), timeout)


def cached_infer(provider: LLMProvider, cache: Cache, payload: dict[str, Any]) -> dict[str, Any]:
    key = cache.digest("scene-speaker-review-v3", provider.model, getattr(provider, "reasoning", None), payload)
    return cache.json("llm", key, lambda: provider.infer(payload))


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
                  automatic_threshold: float = 0.98) -> dict[str, Any]:
    """Review unresolved dialogue in one request per scene, using book text only."""
    started = time.monotonic()
    pending_by_scene: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for dialogue in dialogues:
        if (dialogue.get("dialogue_style") != "quote"
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
            if current and previous_paragraph is not None and paragraph >= 0 and paragraph - previous_paragraph >= 3:
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
        "suggested_for_review": 0, "unresolved": 0, "errors": [],
    }
    for position, (scene_id, pending) in enumerate(batches, 1):
        if progress:
            progress(position, len(batches))
        ids = [int(item.get("book_paragraph_id", -1)) for item in pending
               if int(item.get("book_paragraph_id", -1)) >= 0]
        if ids and book_blocks:
            first, last = max(0, min(ids) - 3), min(len(book_blocks), max(ids) + 4)
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
        scene_dialogues = [item for item in dialogues if int(item.get("scene_id", -1)) == scene_id
                           and (first_context < 0 or first_context <= int(item.get("book_paragraph_id", -1)) <= last_context)]
        payload = {
            "task": ("Atribua cada target_dialogue usando somente este trecho local. "
                     "Personagens apenas mencionados como ausentes não estão presentes e não podem falar."),
            "allowed_speakers": sorted(known, key=str.casefold),
            "scene_id": scene_id,
            "scene_text": context,
            "known_dialogues": [
                {"id": str(item["id"]), "text": item.get("text", ""),
                 "speaker": item.get("speaker"), "confidence": item.get("speaker_confidence", 0)}
                for item in scene_dialogues if item.get("speaker") and item not in pending
            ],
            "target_dialogues": [
                {"id": str(item["id"]), "paragraph": item.get("book_paragraph_id"),
                 "text": item.get("text", ""), "current_speaker": item.get("speaker")}
                for item in pending
            ],
        }
        stats["batches_reviewed"] += 1
        stats["dialogues_reviewed"] += len(pending)
        try:
            answer = cached_infer(provider, cache, payload)
            assignments = answer.get("assignments", [])
            if not isinstance(assignments, list):
                raise ValueError("campo assignments ausente na resposta")
            by_id = {str(item.get("id")): item for item in assignments if isinstance(item, dict)}
            for dialogue in pending:
                decision = by_id.get(str(dialogue["id"]), {})
                speaker = decision.get("speaker")
                confidence = min(1.0, max(0.0, float(decision.get("confidence", 0) or 0)))
                reason = str(decision.get("reason", "")).strip()
                if speaker not in known:
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
                if speaker and confidence >= automatic_threshold:
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
