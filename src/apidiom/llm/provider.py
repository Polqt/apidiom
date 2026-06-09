from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    raw: dict[str, Any] | None = None


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def is_available(self) -> bool:
        """Verify config/connectivity without a billable or slow call."""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Single completion. Implementations own their retry/backoff."""


def get_provider(name: str) -> LLMProvider:
    if name == "gemini":
        try:
            from apidiom.llm.gemini import GeminiProvider
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Gemini provider dependencies are not installed. "
                "Run: pip install apidiom[gemini]"
            ) from exc

        return GeminiProvider()
    if name == "ollama":
        try:
            from apidiom.llm.ollama_provider import OllamaProvider
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Ollama provider dependencies are not installed. "
                "Run: pip install apidiom[ollama]"
            ) from exc

        return OllamaProvider()
    if name == "null":
        from apidiom.llm.null import NullProvider

        return NullProvider()
    raise ValueError(
        f"Unknown LLM provider: {name}. Expected one of: gemini, ollama, null."
    )
