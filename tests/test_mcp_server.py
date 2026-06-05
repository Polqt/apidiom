from pathlib import Path

import pytest

from apidiom.pipeline import PipelineResult


def _result(
    *,
    code: str = "generated client",
    tier: str = "builtin",
    unknowns: list[str] | None = None,
    notes: list[str] | None = None,
    warning: str | None = None,
) -> PipelineResult:
    return PipelineResult(
        spec={"openapi": "3.1.0"},
        model=None,
        generated_client=code,
        generated_files={"client.py": code},
        codegen_tier=tier,
        unverified_items=unknowns or [],
        notes=notes or [],
        provider_warning=warning,
    )


class FakeProvider:
    name = "null"


class FakeGeminiProvider:
    name = "gemini"


def test_mcp_generate_client_matches_pipeline_result(monkeypatch) -> None:
    from apidiom.mcp import server

    expected = _result(code="shared pipeline code", tier="builtin")

    monkeypatch.setattr(server, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(server.pipeline, "generate_client", lambda *a, **k: expected)

    response = server.generate_client(
        "tests/fixtures/petstore.yaml",
        provider="null",
        codegen="builtin",
    )

    assert response["code"] == expected.generated_client
    assert response["tier"] == expected.codegen_tier
    assert response["unverified_fields"] == []
    assert response["notes"] == []


def test_mcp_generate_client_preserves_unverified_fields(monkeypatch) -> None:
    from apidiom.mcp import server

    monkeypatch.setattr(server, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(
        server.pipeline,
        "generate_client",
        lambda *a, **k: _result(unknowns=["$.paths./pets.get.parameters[0]: type"]),
    )

    response = server.generate_client("tests/fixtures/petstore.yaml")

    assert response["unverified_fields"] == ["$.paths./pets.get.parameters[0]: type"]


def test_mcp_generate_client_includes_gemini_privacy_note(monkeypatch) -> None:
    from apidiom.config import GEMINI_PRIVACY_WARNING
    from apidiom.mcp import server

    monkeypatch.setattr(server, "get_provider", lambda name: FakeGeminiProvider())
    monkeypatch.setattr(
        server.pipeline,
        "generate_client",
        lambda *a, **k: _result(warning=GEMINI_PRIVACY_WARNING),
    )

    response = server.generate_client(
        "GET /pets",
        provider="gemini",
        codegen="builtin",
    )

    assert response["privacy_warning"] == GEMINI_PRIVACY_WARNING
    assert GEMINI_PRIVACY_WARNING in response["message"]


def test_mcp_gemini_privacy_note_survives_missing_pipeline_warning(
    monkeypatch,
) -> None:
    from apidiom.config import GEMINI_PRIVACY_WARNING
    from apidiom.mcp import server

    monkeypatch.setattr(server, "get_provider", lambda name: FakeGeminiProvider())
    monkeypatch.setattr(
        server.pipeline,
        "generate_client",
        lambda *a, **k: _result(warning=None),
    )

    response = server.generate_client("GET /pets", provider="gemini")

    assert response["privacy_warning"] == GEMINI_PRIVACY_WARNING
    assert GEMINI_PRIVACY_WARNING in response["message"]


def test_mcp_generate_client_pipeline_error_is_clean_tool_error(monkeypatch) -> None:
    from apidiom.mcp import server

    def raise_pipeline_error(*args, **kwargs) -> PipelineResult:
        raise RuntimeError("Provider ollama is not ready. Start Ollama.")

    monkeypatch.setattr(server, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(server.pipeline, "generate_client", raise_pipeline_error)

    with pytest.raises(server.MCPToolError) as error:
        server.generate_client("GET /pets", provider="ollama")

    assert "Provider ollama is not ready" in str(error.value)
    assert "Traceback" not in str(error.value)


def test_mcp_generate_client_unexpected_error_is_clean_tool_error(
    monkeypatch,
) -> None:
    from apidiom.mcp import server

    def raise_unexpected_error(*args, **kwargs) -> PipelineResult:
        raise Exception("raw surprise")

    monkeypatch.setattr(server, "get_provider", lambda name: FakeProvider())
    monkeypatch.setattr(server.pipeline, "generate_client", raise_unexpected_error)

    with pytest.raises(server.MCPToolError) as error:
        server.generate_client("GET /pets")

    assert "raw surprise" in str(error.value)
    assert "Traceback" not in str(error.value)


def test_mcp_server_only_calls_pipeline_and_shapes_response(monkeypatch) -> None:
    from apidiom.mcp import server

    calls: list[dict[str, object]] = []

    def fake_pipeline_generate_client(source: str | Path, **kwargs) -> PipelineResult:
        calls.append({"source": source, "kwargs": kwargs})
        return _result(code="client")

    fake_provider = FakeProvider()
    monkeypatch.setattr(server, "get_provider", lambda name: fake_provider)
    monkeypatch.setattr(
        server.pipeline,
        "generate_client",
        fake_pipeline_generate_client,
    )

    server.generate_client("tests/fixtures/petstore.yaml", provider="null")

    assert calls == [
        {
            "source": "tests/fixtures/petstore.yaml",
            "kwargs": {
                "provider": fake_provider,
                "lang": "python",
                "codegen": "auto",
                "input_kind": None,
            },
        }
    ]


def test_mcp_default_input_kind_matches_cli_and_web_default(monkeypatch) -> None:
    from apidiom.mcp import server

    calls: list[dict[str, object]] = []
    fake_provider = FakeGeminiProvider()

    def fake_pipeline_generate_client(source: str | Path, **kwargs) -> PipelineResult:
        calls.append(kwargs)
        return _result(code="client")

    monkeypatch.setattr(server, "get_provider", lambda name: fake_provider)
    monkeypatch.setattr(
        server.pipeline,
        "generate_client",
        fake_pipeline_generate_client,
    )

    server.generate_client("tests/fixtures/petstore.yaml", provider="gemini")

    assert calls[0]["input_kind"] is None


def test_mcp_input_kind_can_match_cli_for_openapi_with_non_null_provider(
    monkeypatch,
) -> None:
    from apidiom.mcp import server

    calls: list[dict[str, object]] = []
    fake_provider = FakeGeminiProvider()

    def fake_pipeline_generate_client(source: str | Path, **kwargs) -> PipelineResult:
        calls.append(kwargs)
        return _result(code="client")

    monkeypatch.setattr(server, "get_provider", lambda name: fake_provider)
    monkeypatch.setattr(
        server.pipeline,
        "generate_client",
        fake_pipeline_generate_client,
    )

    server.generate_client(
        "tests/fixtures/petstore.yaml",
        provider="gemini",
        input_kind="openapi",
    )

    assert calls[0]["input_kind"] == "openapi"


def test_mcp_input_kind_can_match_cli_for_unstructured_with_non_null_provider(
    monkeypatch,
) -> None:
    from apidiom.mcp import server

    calls: list[dict[str, object]] = []
    fake_provider = FakeGeminiProvider()

    def fake_pipeline_generate_client(source: str | Path, **kwargs) -> PipelineResult:
        calls.append(kwargs)
        return _result(code="client")

    monkeypatch.setattr(server, "get_provider", lambda name: fake_provider)
    monkeypatch.setattr(
        server.pipeline,
        "generate_client",
        fake_pipeline_generate_client,
    )

    server.generate_client(
        "GET /pets",
        provider="gemini",
        input_kind="unstructured",
    )

    assert calls[0]["input_kind"] == "unstructured"
