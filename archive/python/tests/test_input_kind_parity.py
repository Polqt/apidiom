from pathlib import Path
from typing import Any

from click.testing import CliRunner
from fastapi.testclient import TestClient

from apidiom import cli
from apidiom.mcp import server
from apidiom.pipeline import InputKind, PipelineResult, detect_input_kind
from apidiom.web import app as web_app


class FakeProvider:
    name = "null"

    def is_available(self) -> bool:
        return True


def _front_end_result(
    source: str | Path,
    *,
    input_kind: InputKind | None,
    **kwargs: Any,
) -> PipelineResult:
    used_kind = input_kind or detect_input_kind(source)
    return PipelineResult(
        spec={},
        model=None,
        generated_client=f"{used_kind}-client",
        generated_files={"client.py": f"{used_kind}-client"},
        codegen_tier="builtin",
        input_kind=used_kind,
        input_kind_source="detected" if input_kind is None else "explicit",
    )


def _patch_front_ends(monkeypatch) -> None:
    monkeypatch.setattr(cli, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(cli, "generate_client", _front_end_result)
    monkeypatch.setattr(web_app, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(web_app.pipeline, "generate_client", _front_end_result)
    monkeypatch.setattr(server, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(server.pipeline, "generate_client", _front_end_result)


def _cli_generate(source: str, *, input_kind: str | None = None) -> str:
    args = ["generate", source, "--codegen", "builtin", "--quiet"]
    if input_kind is not None:
        args.extend(["--input-kind", input_kind])
    result = CliRunner().invoke(cli.main, args)
    assert result.exit_code == 0
    return result.stdout.strip()


def _web_generate(source: str, *, input_kind: str | None = None) -> dict[str, Any]:
    data = {
        "source_url": source,
        "provider": "null",
        "lang": "python",
        "codegen": "builtin",
    }
    if input_kind is not None:
        data["input_kind"] = input_kind
    response = TestClient(web_app.app).post("/generate?format=json", data=data)
    assert response.status_code == 200
    return response.json()


def _mcp_generate(source: str, *, input_kind: str | None = None) -> dict[str, Any]:
    kwargs = {"provider": "null", "codegen": "builtin"}
    if input_kind is not None:
        kwargs["input_kind"] = input_kind
    return server.generate_client(source, **kwargs)


def test_auto_detects_clean_spec_same_way_across_front_ends(monkeypatch) -> None:
    _patch_front_ends(monkeypatch)
    source = "tests/fixtures/petstore.yaml"

    cli_code = _cli_generate(source)
    web_payload = _web_generate(source)
    mcp_payload = _mcp_generate(source)

    assert cli_code == web_payload["code"] == mcp_payload["code"] == "openapi-client"
    assert web_payload["input_kind"] == mcp_payload["input_kind"] == "openapi"
    assert (
        web_payload["input_kind_source"]
        == mcp_payload["input_kind_source"]
        == "detected"
    )


def test_auto_detects_messy_docs_same_way_across_front_ends(monkeypatch) -> None:
    _patch_front_ends(monkeypatch)
    source = "GET /pets\nReturns a list of pets."

    cli_code = _cli_generate(source)
    web_payload = _web_generate(source)
    mcp_payload = _mcp_generate(source)

    assert (
        cli_code == web_payload["code"] == mcp_payload["code"] == "unstructured-client"
    )
    assert web_payload["input_kind"] == mcp_payload["input_kind"] == "unstructured"
    assert (
        web_payload["input_kind_source"]
        == mcp_payload["input_kind_source"]
        == "detected"
    )


def test_explicit_openapi_override_wins_across_front_ends(monkeypatch) -> None:
    _patch_front_ends(monkeypatch)
    source = "GET /pets\nReturns a list of pets."

    cli_code = _cli_generate(source, input_kind="openapi")
    web_payload = _web_generate(source, input_kind="openapi")
    mcp_payload = _mcp_generate(source, input_kind="openapi")

    assert cli_code == web_payload["code"] == mcp_payload["code"] == "openapi-client"
    assert (
        web_payload["input_kind_source"]
        == mcp_payload["input_kind_source"]
        == "explicit"
    )


def test_explicit_unstructured_override_wins_across_front_ends(monkeypatch) -> None:
    _patch_front_ends(monkeypatch)
    source = "tests/fixtures/petstore.yaml"

    cli_code = _cli_generate(source, input_kind="unstructured")
    web_payload = _web_generate(source, input_kind="unstructured")
    mcp_payload = _mcp_generate(source, input_kind="unstructured")

    assert (
        cli_code == web_payload["code"] == mcp_payload["code"] == "unstructured-client"
    )
    assert (
        web_payload["input_kind_source"]
        == mcp_payload["input_kind_source"]
        == "explicit"
    )
