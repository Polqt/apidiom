from __future__ import annotations

import json

from apidiom.pipeline import (
    ToolGenerationRequest,
    generate_agent_tools,
)


def test_generated_langchain_tools_compile_without_importing_runtime() -> None:
    result = generate_agent_tools(
        ToolGenerationRequest(
            target="langchain",
            sources="tests/fixtures/petstore.yaml",
            include_operations=["GET:/pets/{petId}"],
        )
    )

    assert result.generated_client is not None
    compile(result.generated_client, "generated_langchain_tools.py", "exec")


def test_generated_openai_schema_is_valid_json() -> None:
    result = generate_agent_tools(
        ToolGenerationRequest(
            target="schema",
            sources="tests/fixtures/petstore.yaml",
            schema_format="openai",
            include_operations=["GET:/pets/{petId}"],
        )
    )

    assert result.generated_client is not None
    payload = json.loads(result.generated_client)
    assert payload[0]["type"] == "function"
    assert payload[0]["function"]["name"] == "get_pet"
