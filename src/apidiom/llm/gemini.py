import time
from collections.abc import Callable
from typing import Any, Protocol, cast

import httpx

from apidiom.config import get_gemini_api_key, get_gemini_model
from apidiom.llm.provider import LLMProvider, LLMResponse

_BACKOFF_SECONDS = [1, 2, 4, 8]
_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"


class _GeminiResponse(Protocol):
    status_code: int

    def json(self) -> dict[str, Any]: ...


class _GeminiClient(Protocol):
    def post(
        self,
        url: str,
        *,
        params: dict[str, str],
        json: dict[str, Any],
    ) -> _GeminiResponse: ...


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client_factory: Callable[[], _GeminiClient] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key if api_key is not None else get_gemini_api_key()
        self._model = model if model is not None else get_gemini_model()
        self._client_factory = client_factory or (lambda: httpx.Client(timeout=60))
        self._sleeper = sleeper

    def is_available(self) -> bool:
        return bool(self._api_key)

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
        if not self._api_key:
            raise RuntimeError("Gemini is not configured. Set GEMINI_API_KEY.")

        client = self._client_factory()
        payload = self._request_payload(
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            response_schema=response_schema,
        )
        url = f"{_GEMINI_ENDPOINT}/{self._model}:generateContent"

        for attempt in range(len(_BACKOFF_SECONDS) + 1):
            response = client.post(url, params={"key": self._api_key}, json=payload)
            if response.status_code == 429:
                if attempt == len(_BACKOFF_SECONDS):
                    raise RuntimeError(
                        "Gemini rate limit was hit after retries. "
                        "Try again later or use --provider ollama."
                    )
                self._sleeper(_BACKOFF_SECONDS[attempt])
                continue
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Gemini request failed with HTTP {response.status_code}."
                )
            raw = response.json()
            return LLMResponse(
                text=_extract_text(raw),
                model=self._model,
                raw=raw,
            )

        raise RuntimeError("Gemini request failed unexpectedly.")

    def _request_payload(
        self,
        prompt: str,
        *,
        system: str | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        response_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system is not None:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        if response_schema is not None:
            payload["generationConfig"]["responseSchema"] = response_schema
        return payload


def _extract_text(raw: dict[str, Any]) -> str:
    candidates = raw.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("Gemini response did not include any candidates.")

    candidate = candidates[0]
    if not isinstance(candidate, dict):
        raise RuntimeError("Gemini response candidate was malformed.")
    content = candidate.get("content")
    if not isinstance(content, dict):
        raise RuntimeError("Gemini response content was malformed.")
    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        raise RuntimeError("Gemini response did not include text parts.")
    first_part = parts[0]
    if not isinstance(first_part, dict) or not isinstance(first_part.get("text"), str):
        raise RuntimeError("Gemini response text was malformed.")
    return cast(str, first_part["text"])
