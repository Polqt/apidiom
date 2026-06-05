import json
import textwrap
from pathlib import Path

import pytest

from apidiom.ingest.doc_to_spec import (
    DocToSpecError,
    chunk_documentation,
    doc_to_spec,
    merge_openapi_fragments,
)
from apidiom.llm.provider import LLMProvider, LLMResponse
from apidiom.pipeline import generate_client


class FakeProvider(LLMProvider):
    name = "fake"

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
    ) -> LLMResponse:
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "json_mode": json_mode,
            }
        )
        return LLMResponse(text=self.responses.pop(0), model="fake")


def _valid_pet_fragment() -> dict[str, object]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Pet API", "version": "1.0.0"},
        "paths": {
            "/pets/{petId}": {
                "get": {
                    "operationId": "getPet",
                    "parameters": [
                        {
                            "name": "petId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer", "format": "int64"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Pet response",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Pet"}
                                }
                            },
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "Pet": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}},
                }
            }
        },
    }


def test_clean_extraction_returns_expected_normalized_model() -> None:
    provider = FakeProvider([json.dumps(_valid_pet_fragment())])

    result = doc_to_spec(
        "<h1>Pets</h1><p>GET /pets/{petId}</p><p>petId is required integer.</p>",
        provider=provider,
    )

    endpoint = result.model.endpoint("GET", "/pets/{petId}")
    assert result.spec["info"]["title"] == "Pet API"
    assert endpoint.operation_id == "getPet"
    assert endpoint.path_parameters[0].name == "petId"
    assert endpoint.path_parameters[0].schema_model.value["type"] == "integer"
    assert provider.calls[0]["json_mode"] is True


def test_unknown_handling_collects_unknown_items_without_guessing() -> None:
    fragment = {
        "openapi": "3.1.0",
        "info": {"title": "Unknown API", "version": "1.0.0"},
        "paths": {
            "/search": {
                "get": {
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "required": False,
                            "schema": {},
                            "description": "UNVERIFIED: type not stated",
                            "x-apidiom-unknown": ["type"],
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    result = doc_to_spec(
        "GET /search query q",
        provider=FakeProvider([json.dumps(fragment)]),
    )

    parameter = result.model.endpoint("GET", "/search").query_parameters[0]
    assert parameter.schema_model.value == {}
    assert any("type" in item for item in result.unverified_items)


def test_never_required_defaults_not_required_and_is_flagged() -> None:
    fragment = {
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
                            "schema": {"type": "string"},
                            "description": "UNVERIFIED: required not stated",
                            "x-apidiom-unknown": ["required"],
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    result = doc_to_spec(
        "GET /search query q string",
        provider=FakeProvider([json.dumps(fragment)]),
    )

    parameter = result.model.endpoint("GET", "/search").query_parameters[0]
    assert parameter.required is False
    assert any("required" in item for item in result.unverified_items)


def test_no_api_chunk_returns_empty_skeleton() -> None:
    result = doc_to_spec(
        "This page only describes account billing policies.",
        provider=FakeProvider(
            [
                json.dumps(
                    {
                        "openapi": "3.1.0",
                        "info": {"title": "untitled", "version": "0.0.0"},
                        "paths": {},
                    }
                )
            ]
        ),
    )

    assert result.spec["paths"] == {}
    assert result.model.endpoints == []


def test_chunking_keeps_sections_intact() -> None:
    docs = textwrap.dedent("""
        ## List pets
        GET /pets
        Returns pets.

        ## Create pet
        POST /pets
        Creates a pet.

        ## Delete pet
        DELETE /pets/{petId}
        Deletes a pet.
        """)
    chunks = chunk_documentation(docs, token_budget=12)

    assert len(chunks) == 3
    assert all("##" in chunk for chunk in chunks)
    assert "GET /pets" in chunks[0]
    assert "POST /pets" in chunks[1]
    assert "DELETE /pets/{petId}" in chunks[2]


def test_merge_combines_chunks_and_records_conflicts() -> None:
    first = _valid_pet_fragment()
    second = {
        "openapi": "3.1.0",
        "info": {"title": "Pet API", "version": "1.0.0"},
        "paths": {
            "/pets/{petId}": {
                "get": {
                    "operationId": "getPetConflicting",
                    "responses": {"200": {"description": "Conflict"}},
                }
            },
            "/pets": {
                "get": {
                    "operationId": "listPets",
                    "responses": {"200": {"description": "OK"}},
                }
            },
        },
        "components": {
            "schemas": {
                "Pet": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            }
        },
    }

    merged = merge_openapi_fragments([first, second])

    assert "/pets" in merged["paths"]
    assert merged["paths"]["/pets/{petId}"]["get"]["operationId"] == "getPet"
    assert len(merged["x-apidiom-notes"]) == 2


def test_repair_loop_stops_after_valid_response() -> None:
    invalid = {
        "openapi": "3.1.0",
        "info": {"title": "Broken", "version": "1.0.0"},
        "paths": {"/broken": {"get": {"responses": {}}}},
    }
    repaired = {
        "openapi": "3.1.0",
        "info": {"title": "Broken", "version": "1.0.0"},
        "paths": {
            "/broken": {
                "get": {
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    provider = FakeProvider([json.dumps(invalid), json.dumps(repaired)])

    result = doc_to_spec("GET /broken", provider=provider)

    assert (
        result.spec["paths"]["/broken"]["get"]["responses"]["200"]["description"]
        == "OK"
    )
    assert len(provider.calls) == 2


def test_repair_cap_raises_and_saves_best_candidate() -> None:
    invalid = {
        "openapi": "3.1.0",
        "info": {"title": "Broken", "version": "1.0.0"},
        "paths": {"/broken": {"get": {"responses": {}}}},
    }
    output_path = Path("tests/fixtures/best_candidate.generated.json")
    if output_path.exists():
        output_path.unlink()

    provider = FakeProvider(
        [
            json.dumps(invalid),
            json.dumps(invalid),
            json.dumps(invalid),
            json.dumps(invalid),
        ]
    )

    with pytest.raises(
        DocToSpecError,
        match="OpenAPI validation failed after 3 repair attempts",
    ):
        doc_to_spec("GET /broken", provider=provider, candidate_output_path=output_path)

    assert output_path.exists()
    assert "validator errors" in output_path.read_text(encoding="utf-8")
    output_path.unlink()


def test_integrity_guard_rejects_repair_that_adds_endpoint() -> None:
    invalid = {
        "openapi": "3.1.0",
        "info": {"title": "Broken", "version": "1.0.0"},
        "paths": {"/broken": {"get": {"responses": {}}}},
    }
    repaired = {
        "openapi": "3.1.0",
        "info": {"title": "Broken", "version": "1.0.0"},
        "paths": {
            "/broken": {"get": {"responses": {"200": {"description": "OK"}}}},
            "/extra": {"get": {"responses": {"200": {"description": "OK"}}}},
        },
    }

    with pytest.raises(DocToSpecError, match="changed the endpoint set"):
        doc_to_spec(
            "GET /broken",
            provider=FakeProvider([json.dumps(invalid), json.dumps(repaired)]),
        )


def test_pipeline_generate_client_uses_unstructured_path() -> None:
    result = generate_client(
        "GET /pets/{petId}",
        provider=FakeProvider([json.dumps(_valid_pet_fragment())]),
        input_kind="unstructured",
        codegen="builtin",
        model_generator=lambda spec_json: "class Pet: ...\n",
    )

    assert result.model.endpoint("GET", "/pets/{petId}").operation_id == "getPet"


def test_pipeline_generates_client_and_preserves_unknowns() -> None:
    fragment = _valid_pet_fragment()
    parameter = fragment["paths"]["/pets/{petId}"]["get"]["parameters"][0]
    parameter["x-apidiom-unknown"] = ["required"]
    parameter["description"] = "UNVERIFIED: required not specified"

    result = generate_client(
        "GET /pets/{petId}",
        provider=FakeProvider([json.dumps(fragment)]),
        input_kind="unstructured",
        codegen="builtin",
        model_generator=lambda spec_json: "class Pet: ...\n",
    )

    assert result.generated_client is not None
    assert "# UNVERIFIED: required not specified in docs" in result.generated_client
    assert any("required" in item for item in result.unverified_items)
