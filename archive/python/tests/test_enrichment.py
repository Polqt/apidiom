from typing import Any

from apidiom.generate.enrichment import enrich_description
from apidiom.llm.provider import LLMProvider, LLMResponse
from apidiom.models import APIEndpoint


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self) -> None:
        self.prompts: list[str] = []

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
        response_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.prompts.append(prompt)
        return LLMResponse(
            text="Create a payment charge for an agent workflow.",
            model="fake",
        )


def test_enrich_description_skips_rich_summary() -> None:
    provider = FakeProvider()
    endpoint = APIEndpoint(
        path="/charges",
        method="POST",
        summary="Create a charge with payment amount, currency, and metadata.",
    )

    assert enrich_description(endpoint, provider) == endpoint.summary
    assert provider.prompts == []


def test_enrich_description_calls_provider_for_sparse_summary() -> None:
    provider = FakeProvider()
    endpoint = APIEndpoint(path="/charges", method="POST", summary="Create charge")

    assert (
        enrich_description(endpoint, provider)
        == "Create a payment charge for an agent workflow."
    )
    assert "POST" in provider.prompts[0]
