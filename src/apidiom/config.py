import os
from typing import Literal, cast

ProviderName = Literal["gemini", "ollama", "null"]

GEMINI_PRIVACY_WARNING = (
    "Warning: Gemini free-tier data may be used for training; "
    "only use it for public docs."
)


def get_default_provider_name() -> ProviderName:
    return _provider_name(os.getenv("APIDIOM_PROVIDER", "null"))


def get_gemini_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY")


def get_gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def get_ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", "llama3.1:8b")


def get_ollama_base_url() -> str:
    return os.getenv("OLLAMA_HOST", "http://localhost:11434")


def readiness_reason(provider_name: str) -> str:
    if provider_name == "gemini":
        return "Set GEMINI_API_KEY to use Gemini."
    if provider_name == "ollama":
        return f"Start Ollama and pull the configured model ({get_ollama_model()})."
    return "Provider is unavailable."


def _provider_name(value: str) -> ProviderName:
    if value in {"gemini", "ollama", "null"}:
        return cast(ProviderName, value)
    raise ValueError(
        f"Unknown LLM provider: {value}. Expected one of: gemini, ollama, null."
    )
