from __future__ import annotations

import json
import os
from typing import Any

import requests

from .cache import Cache


class LLMProvider:
    def infer(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, timeout: int = 60):
        self.url, self.model, self.timeout = base_url.rstrip("/"), model, timeout

    def infer(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(f"{self.url}/api/chat", timeout=self.timeout, json={"model": self.model, "stream": False,
            "format": "json", "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]})
        response.raise_for_status()
        return json.loads(response.json()["message"]["content"])


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, api_key_env: str, timeout: int = 60):
        self.url, self.model, self.key, self.timeout = base_url.rstrip("/"), model, os.getenv(api_key_env, ""), timeout

    def infer(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(f"{self.url}/chat/completions", timeout=self.timeout,
            headers={"Authorization": f"Bearer {self.key}"} if self.key else {}, json={"model": self.model,
            "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], "temperature": 0})
        response.raise_for_status()
        return json.loads(response.json()["choices"][0]["message"]["content"])


SYSTEM = "Return only JSON with speaker, gender, age_group, confidence (0..1), reason. Never invent a speaker not in known_characters."


def build_provider(config: dict[str, Any]) -> LLMProvider | None:
    if not config.get("enabled") or not config.get("model"):
        return None
    if config.get("provider") == "ollama":
        return OllamaProvider(config.get("base_url", "http://localhost:11434"), config["model"], int(config.get("timeout_seconds", 60)))
    return OpenAICompatibleProvider(config["base_url"], config["model"], config.get("api_key_env", "OPENAI_API_KEY"), int(config.get("timeout_seconds", 60)))


def cached_infer(provider: LLMProvider, cache: Cache, payload: dict[str, Any]) -> dict[str, Any]:
    key = cache.digest(payload)
    return cache.json("llm", key, lambda: provider.infer(payload))
