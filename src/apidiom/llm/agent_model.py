from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from apidiom.llm.provider import LLMProvider


def build_llm_provider_model(
    provider: LLMProvider,
    *,
    response_schema: dict[str, Any] | None,
) -> FunctionModel:
    """Adapt an apidiom LLMProvider into a Pydantic AI FunctionModel.

    Every call still goes through provider.complete() -- Pydantic AI never
    talks to Gemini/Ollama directly, so retry/backoff/availability logic
    isn't duplicated.
    """

    def _call(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        system_text, prompt_text = _flatten_messages(messages)
        response = provider.complete(
            prompt_text,
            system=system_text,
            temperature=0.0,
            json_mode=True,
            response_schema=response_schema,
        )
        return ModelResponse(parts=[TextPart(content=response.text)])

    return FunctionModel(_call)


def _flatten_messages(messages: list[ModelMessage]) -> tuple[str | None, str]:
    system_parts: list[str] = []
    prompt_parts: list[str] = []
    for message in messages:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if isinstance(part, SystemPromptPart):
                system_parts.append(part.content)
            elif isinstance(part, UserPromptPart) and isinstance(part.content, str):
                prompt_parts.append(part.content)
            elif isinstance(part, RetryPromptPart):
                prompt_parts.append(str(part.content))
    system_text = "\n".join(system_parts) if system_parts else None
    prompt_text = "\n\n".join(prompt_parts)
    return system_text, prompt_text
