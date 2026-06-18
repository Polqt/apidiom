from dataclasses import dataclass
from typing import Protocol

from click.testing import CliRunner

from apidiom import cli
from apidiom.models import APIClientModel
from apidiom.pipeline import PipelineResult, ToolGenerationRequest


@dataclass(frozen=True)
class _FakeOperation:
    selector: str
    function_name: str
    description: str
    tags: list[str]


class _MonkeyPatch(Protocol):
    def setattr(self, target: object, name: str, value: object) -> None: ...


def _empty_model() -> APIClientModel:
    return APIClientModel(title="Test API", version="1.0.0", source="test")


def test_generate_calls_pipeline_and_routes_stdout(
    monkeypatch: _MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_generate_client(*args: object, **kwargs: object) -> PipelineResult:
        calls.append((args, kwargs))
        return PipelineResult(
            spec={},
            model=_empty_model(),
            generated_client="client",
            generated_files={"client.py": "client"},
            codegen_tier="builtin",
            unverified_items=["$.paths./pets.get.parameters[0]: type"],
        )

    monkeypatch.setattr(cli, "generate_client", fake_generate_client)
    result = CliRunner().invoke(
        cli.main,
        [
            "generate",
            "docs text",
            "--input-kind",
            "unstructured",
            "--codegen",
            "builtin",
        ],
    )

    assert result.exit_code == 0
    assert "client" in result.stdout
    assert "builtin" in result.stderr
    assert "1 field could not be verified" in result.stderr
    assert calls[0][1]["input_kind"] == "unstructured"


def test_generate_mcp_calls_pipeline_and_routes_stdout(
    monkeypatch: _MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_generate_agent_tools(request: ToolGenerationRequest) -> PipelineResult:
        calls.append(((request,), {}))
        return PipelineResult(
            spec={},
            model=_empty_model(),
            generated_client="mcp server",
            generated_files={"server.py": "mcp server"},
            codegen_tier="mcp",
            input_kind="openapi",
            input_kind_source="explicit",
        )

    monkeypatch.setattr(cli, "generate_agent_tools", fake_generate_agent_tools)
    result = CliRunner().invoke(
        cli.main,
        [
            "generate",
            "mcp",
            "tests/fixtures/petstore.yaml",
            "--tag",
            "pets",
            "--include",
            "GET:/pets",
        ],
    )

    assert result.exit_code == 0
    assert "mcp server" in result.stdout
    assert "mcp" in result.stderr
    request = calls[0][0][0]
    assert isinstance(request, ToolGenerationRequest)
    assert request.target == "mcp"
    assert request.sources == ["tests/fixtures/petstore.yaml"]
    assert request.include_tags == ["pets"]
    assert request.include_operations == ["GET:/pets"]
    assert request.provider is None
    assert request.enrich_docs is False


def test_generate_mcp_check_reports_generated_server_summary(
    monkeypatch: _MonkeyPatch,
) -> None:
    server = """
from __future__ import annotations
import os
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("demo")
API_BASE_URL = os.environ.get("APIDIOM_API_BASE_URL", "")

@mcp.tool()
def get_pet() -> dict:
    return {}
"""

    def fake_generate_agent_tools(request: ToolGenerationRequest) -> PipelineResult:
        return PipelineResult(
            spec={},
            model=_empty_model(),
            generated_client=server,
            generated_files={"server.py": server},
            codegen_tier="mcp",
            input_kind="openapi",
            input_kind_source="explicit",
        )

    monkeypatch.setattr(cli, "generate_agent_tools", fake_generate_agent_tools)
    result = CliRunner().invoke(
        cli.main,
        ["generate", "mcp", "tests/fixtures/petstore.yaml", "--check", "--quiet"],
    )

    assert result.exit_code == 0
    assert "MCP check: 1 tools" in result.stderr
    assert "APIDIOM_API_BASE_URL" in result.stderr


def test_generate_mcp_list_reports_available_selectors(
    monkeypatch: _MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_list_mcp_operations(
        *args: object,
        **kwargs: object,
    ) -> list[_FakeOperation]:
        calls.append((args, kwargs))
        return [
            _FakeOperation(
                selector="GET:/pets",
                function_name="list_pets",
                description="List pets",
                tags=["pets"],
            )
        ]

    monkeypatch.setattr(cli, "list_mcp_operations", fake_list_mcp_operations)
    result = CliRunner().invoke(
        cli.main,
        [
            "generate",
            "mcp",
            "tests/fixtures/petstore.yaml",
            "--tag",
            "pets",
            "--list",
            "--quiet",
        ],
    )

    assert result.exit_code == 0
    assert "GET:/pets list_pets - List pets [tags: pets]" in result.stdout
    assert calls[0][0] == (["tests/fixtures/petstore.yaml"],)
    assert calls[0][1] == {
        "include_tags": ["pets"],
        "include_operations": [],
    }


def test_generate_langchain_calls_pipeline(monkeypatch: _MonkeyPatch) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_generate_agent_tools(request: ToolGenerationRequest) -> PipelineResult:
        calls.append(((request,), {}))
        return PipelineResult(
            spec={},
            model=_empty_model(),
            generated_client="tools",
            generated_files={"tools.py": "tools"},
            codegen_tier="langchain",
            input_kind="openapi",
            input_kind_source="explicit",
        )

    monkeypatch.setattr(cli, "generate_agent_tools", fake_generate_agent_tools)
    result = CliRunner().invoke(
        cli.main,
        [
            "generate",
            "langchain",
            "stripe.yaml",
            "github.yaml",
            "--include",
            "GET:/repos",
            "--quiet",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == "tools\n"
    request = calls[0][0][0]
    assert isinstance(request, ToolGenerationRequest)
    assert request.target == "langchain"
    assert request.sources == ["stripe.yaml", "github.yaml"]
    assert request.include_operations == ["GET:/repos"]


def test_generate_schema_calls_pipeline_with_format(monkeypatch: _MonkeyPatch) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_generate_agent_tools(request: ToolGenerationRequest) -> PipelineResult:
        calls.append(((request,), {}))
        return PipelineResult(
            spec={},
            model=_empty_model(),
            generated_client="[]",
            generated_files={"tools.json": "[]"},
            codegen_tier="schema:openai",
            input_kind="openapi",
            input_kind_source="explicit",
        )

    monkeypatch.setattr(cli, "generate_agent_tools", fake_generate_agent_tools)
    result = CliRunner().invoke(
        cli.main,
        [
            "generate",
            "schema",
            "tests/fixtures/petstore.yaml",
            "--format",
            "openai",
            "--quiet",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == "[]\n"
    request = calls[0][0][0]
    assert isinstance(request, ToolGenerationRequest)
    assert request.target == "schema"
    assert request.schema_format == "openai"
