from apidiom.llm.provider import LLMProvider, LLMResponse


class NullProvider(LLMProvider):
    name = "null"

    def is_available(self) -> bool:
        return True

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        raise RuntimeError(
            "This input needs an LLM. Re-run with --provider gemini or "
            "--provider ollama. Use Gemini only for public docs; use Ollama "
            "for local/private docs."
        )
