from typing import Any

from apidiom.generate.langchain_gen import generate_langchain_tools
from apidiom.ingest.openapi_ingest import normalize_openapi_document


def _spec() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Tiny API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.test"}],
        "paths": {
            "/charges": {
                "post": {
                    "operationId": "createCharge",
                    "summary": "Create charge",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["amount"],
                                    "properties": {
                                        "amount": {"type": "integer"},
                                        "currency": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }


def test_generate_langchain_tools_emits_importable_tool_functions() -> None:
    spec = _spec()
    model = normalize_openapi_document(spec, "test")

    tools = generate_langchain_tools(spec, model)

    assert "from langchain_core.tools import tool" in tools
    assert "@tool" in tools
    assert "def create_charge(" in tools
    assert "amount: int," in tools
    assert "currency: str | None = None," in tools
    assert 'json_body["amount"] = amount' in tools
    compile(tools, "generated_langchain_tools.py", "exec")


def test_generate_langchain_tools_filters_by_include_selector() -> None:
    spec = _spec()
    model = normalize_openapi_document(spec, "test")

    tools = generate_langchain_tools(
        spec,
        model,
        include_operations=["POST:/charges"],
    )

    assert "def create_charge(" in tools
