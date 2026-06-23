import builtins
from typing import Any

import httpx
import pytest

from apidiom.llm.gemini import GeminiProvider
from apidiom.llm.null import NullProvider
from apidiom.llm.ollama_provider import OllamaProvider
from apidiom.llm.provider import LLMResponse, get_provider


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeGeminiClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.prompts: list[dict[str, Any]] = []

    def post(
        self,
        url: str,
        *,
        params: dict[str, str],
        json: dict[str, Any],
    ) -> FakeResponse:
        self.prompts.append({"url": url, "params": params, "json": json})
        return self.responses.pop(0)


class FakeOllamaClient:
    def __init__(
        self,
        *,
        tags_payload: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.tags_payload = tags_payload or {"models": []}
        self.error = error

    def get(self, url: str) -> FakeResponse:
        if self.error is not None:
            raise self.error
        assert url == "/api/tags"
        return FakeResponse(200, self.tags_payload)


def test_factory_returns_correct_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    assert isinstance(get_provider("null"), NullProvider)
    assert isinstance(get_provider("gemini"), GeminiProvider)
    assert isinstance(get_provider("ollama"), OllamaProvider)


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_provider("unknown")


@pytest.mark.parametrize("provider_name", ["gemini", "ollama"])
def test_factory_reports_missing_optional_provider_dependency(
    monkeypatch: pytest.MonkeyPatch,
    provider_name: str,
) -> None:
    real_import = builtins.__import__
    provider_module = {
        "gemini": "apidiom.llm.gemini",
        "ollama": "apidiom.llm.ollama_provider",
    }[provider_name]

    def missing_httpx(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == provider_module:
            raise ModuleNotFoundError("No module named 'httpx'", name="httpx")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", missing_httpx)

    with pytest.raises(
        RuntimeError,
        match=rf"pip install apidiom\[{provider_name}\]",
    ):
        get_provider(provider_name)


def test_null_provider_complete_raises_actionable_error() -> None:
    provider = NullProvider()

    with pytest.raises(RuntimeError, match="--provider gemini or --provider ollama"):
        provider.complete("extract this")


def test_gemini_is_available_checks_only_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert GeminiProvider().is_available() is False

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert GeminiProvider().is_available() is True


def test_gemini_complete_retries_429_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    responses = [
        FakeResponse(429, {"error": {"message": "rate limit"}}),
        FakeResponse(429, {"error": {"message": "rate limit"}}),
        FakeResponse(
            200,
            {"candidates": [{"content": {"parts": [{"text": "generated spec"}]}}]},
        ),
    ]
    fake_client = FakeGeminiClient(responses)
    sleeps: list[float] = []
    provider = GeminiProvider(
        client_factory=lambda: fake_client,
        sleeper=sleeps.append,
    )

    response = provider.complete("prompt", system="system")

    assert response == LLMResponse(
        text="generated spec",
        model="gemini-2.5-flash",
        raw={"candidates": [{"content": {"parts": [{"text": "generated spec"}]}}]},
    )
    assert sleeps == [1, 2]
    assert len(fake_client.prompts) == 3


def test_gemini_complete_gives_up_after_retry_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    fake_client = FakeGeminiClient(
        [
            FakeResponse(429, {"error": {"message": "rate limit"}}),
            FakeResponse(429, {"error": {"message": "rate limit"}}),
            FakeResponse(429, {"error": {"message": "rate limit"}}),
            FakeResponse(429, {"error": {"message": "rate limit"}}),
            FakeResponse(429, {"error": {"message": "rate limit"}}),
        ]
    )
    sleeps: list[float] = []
    provider = GeminiProvider(
        client_factory=lambda: fake_client,
        sleeper=sleeps.append,
    )

    with pytest.raises(RuntimeError, match="Gemini rate limit"):
        provider.complete("prompt")

    assert sleeps == [1, 2, 4, 8]


def test_ollama_is_available_when_daemon_up_and_model_present() -> None:
    provider = OllamaProvider(
        model="llama3.1:8b",
        client_factory=lambda: FakeOllamaClient(
            tags_payload={"models": [{"name": "llama3.1:8b"}]}
        ),
    )

    assert provider.is_available() is True


def test_ollama_is_unavailable_when_daemon_down() -> None:
    provider = OllamaProvider(
        client_factory=lambda: FakeOllamaClient(
            error=httpx.ConnectError("connection refused")
        ),
    )

    assert provider.is_available() is False
