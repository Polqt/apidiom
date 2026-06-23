import asyncio

from pydantic_ai import Agent

from apidiom.llm.agent_model import build_llm_provider_model
from apidiom.llm.provider import LLMProvider, LLMResponse


class RecordingProvider(LLMProvider):
    name = "recording"

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

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
        response_schema: dict | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "json_mode": json_mode,
                "response_schema": response_schema,
            }
        )
        return LLMResponse(text=self.responses.pop(0), model="recording")


def test_adapter_forwards_prompt_and_system_to_provider() -> None:
    provider = RecordingProvider(['{"hello": "world"}'])
    model = build_llm_provider_model(provider, response_schema=None)
    agent: Agent[None, str] = Agent(
        model, output_type=str, system_prompt="extract things"
    )

    result = asyncio.run(agent.run("the user prompt text"))

    assert provider.calls[0]["system"] == "extract things"
    assert "the user prompt text" in provider.calls[0]["prompt"]
    assert provider.calls[0]["json_mode"] is True
    assert result.output == '{"hello": "world"}'


def test_adapter_includes_retry_feedback_in_next_prompt() -> None:
    provider = RecordingProvider(['{"bad": true}', '{"good": true}'])
    model = build_llm_provider_model(provider, response_schema=None)
    agent: Agent[None, str] = Agent(
        model, output_type=str, system_prompt="extract things"
    )

    import json

    from pydantic_ai import ModelRetry

    @agent.output_validator
    def _validate(data: str) -> str:
        parsed = json.loads(data)
        if parsed.get("bad"):
            raise ModelRetry("that was bad, try again")
        return data

    asyncio.run(agent.run("the user prompt text"))

    assert len(provider.calls) == 2
    assert "that was bad, try again" in provider.calls[1]["prompt"]
