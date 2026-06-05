import json
from typing import Any

from apidiom.llm.provider import LLMProvider, LLMResponse
from apidiom.pipeline import detect_input_kind, generate_client


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


def test_detect_input_kind_openapi_for_valid_spec() -> None:
    assert detect_input_kind("tests/fixtures/petstore.yaml") == "openapi"


def test_detect_input_kind_unstructured_for_plain_text_endpoint_blurb() -> None:
    assert detect_input_kind("GET /pets\nReturns a list of pets.") == "unstructured"


def test_detect_input_kind_unstructured_for_malformed_json() -> None:
    assert detect_input_kind('{"openapi": ') == "unstructured"


def test_detect_input_kind_unstructured_for_html_docs() -> None:
    html = "<html><body><h1>Pets API</h1><p>GET /pets returns pets.</p></body></html>"

    assert detect_input_kind(html) == "unstructured"


def test_detect_input_kind_unstructured_for_postman_collection() -> None:
    postman = json.dumps(
        {
            "info": {
                "name": "Pets",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [
                {
                    "name": "List pets",
                    "request": {"method": "GET", "url": {"path": ["pets"]}},
                }
            ],
        }
    )

    assert detect_input_kind(postman) == "unstructured"


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
    assert result.input_kind == "openapi"
    assert result.input_kind_source == "detected"


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
    assert result.input_kind == "unstructured"
    assert result.input_kind_source == "explicit"


def test_pipeline_auto_detects_unstructured_docs() -> None:
    fragment: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "Pets API", "version": "1.0.0"},
        "paths": {"/pets": {"get": {"responses": {"200": {"description": "OK"}}}}},
    }

    result = generate_client(
        "GET /pets\nReturns pets.",
        provider=FakeProvider([json.dumps(fragment)]),
        lang="python",
        codegen="builtin",
        model_generator=_model_generator,
    )

    assert result.generated_client is not None
    assert result.input_kind == "unstructured"
    assert result.input_kind_source == "detected"


def test_pipeline_explicit_openapi_override_does_not_redetect() -> None:
    try:
        generate_client(
            "GET /pets\nReturns pets.",
            provider=FakeProvider([]),
            lang="python",
            input_kind="openapi",
            codegen="builtin",
            model_generator=_model_generator,
        )
    except RuntimeError as exc:
        assert "Could not parse OpenAPI document" in str(exc)
    else:
        raise AssertionError("explicit openapi override should force OpenAPI parsing")


def test_pipeline_explicit_unstructured_override_does_not_redetect_clean_spec() -> None:
    fragment: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "Pets API", "version": "1.0.0"},
        "paths": {"/pets": {"get": {"responses": {"200": {"description": "OK"}}}}},
    }

    result = generate_client(
        "tests/fixtures/petstore.yaml",
        provider=FakeProvider([json.dumps(fragment)]),
        lang="python",
        input_kind="unstructured",
        codegen="builtin",
        model_generator=_model_generator,
    )

    assert result.input_kind == "unstructured"
    assert result.input_kind_source == "explicit"
