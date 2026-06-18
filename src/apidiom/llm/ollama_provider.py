from collections.abc import Callable
from typing import Any, Protocol

import httpx

from apidiom.config import get_ollama_base_url, get_ollama_model
from apidiom.llm.provider import LLMProvider, LLMResponse


class _OllamaResponse(Protocol):
    status_code: int

    def json(self) -> dict[str, Any]: ...


class _OllamaClient(Protocol):
    def get(self, url: str) -> _OllamaResponse: ...

    def post(self, url: str, *, json: dict[str, Any]) -> _OllamaResponse: ...


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        client_factory: Callable[[], _OllamaClient] | None = None,
    ) -> None:
        self._model = model if model is not None else get_ollama_model()
        self._base_url = base_url if base_url is not None else get_ollama_base_url()
        self._client_factory = client_factory or (
            lambda: httpx.Client(base_url=self._base_url, timeout=30)
        )

    def is_available(self) -> bool:
        try:
            response = self._client_factory().get("/api/tags")
        except httpx.HTTPError:
            return False

        if response.status_code >= 400:
            return False
        models = response.json().get("models")
        if not isinstance(models, list):
            return False
        return any(_model_name(model) == self._model for model in models)

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
        response_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system is not None:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        try:
            response = self._client_factory().post("/api/generate", json=payload)
        except httpx.HTTPError as exc:
            raise RuntimeError(
                "Could not reach Ollama. Start the local daemon and try again."
            ) from exc

        if response.status_code >= 400:
            raise RuntimeError(
                f"Ollama request failed with HTTP {response.status_code}."
            )
        raw = response.json()
        text = raw.get("response")
        if not isinstance(text, str):
            raise RuntimeError("Ollama response did not include generated text.")
        return LLMResponse(text=text, model=self._model, raw=raw)


def _model_name(model: object) -> str | None:
    if not isinstance(model, dict):
        return None
    name = model.get("name", model.get("model"))
    if isinstance(name, str):
        return name
    return None
