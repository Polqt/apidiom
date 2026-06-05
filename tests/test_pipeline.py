import json
from typing import Any

from apidiom.llm.provider import LLMProvider, LLMResponse
from apidiom.pipeline import generate_client


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses

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
        return LLMResponse(text=self.responses.pop(0), model="fake")


def _model_generator(spec_json: str) -> str:
    return "class Pet: ...\n"


def test_pipeline_structured_spec_returns_code_and_tier() -> None:
    result = generate_client(
        "tests/fixtures/petstore.yaml",
        provider=None,
        lang="python",
        codegen="builtin",
        model_generator=_model_generator,
    )

    assert result.generated_client is not None
    assert result.codegen_tier == "builtin"
    assert result.model.endpoint("GET", "/pets").operation_id == "listPets"


def test_pipeline_unstructured_docs_returns_code_unknowns_and_tier() -> None:
    fragment: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "Search API", "version": "1.0.0"},
        "paths": {
            "/search": {
                "get": {
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "required": False,
                            "schema": {},
                            "x-apidiom-unknown": ["type"],
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    result = generate_client(
        "GET /search query q",
        provider=FakeProvider([json.dumps(fragment)]),
        lang="python",
        input_kind="unstructured",
        codegen="builtin",
        model_generator=_model_generator,
    )

    assert result.generated_client is not None
    assert result.codegen_tier == "builtin"
    assert any("type" in item for item in result.unverified_items)
    assert "# UNVERIFIED: type not specified in docs" in result.generated_client
