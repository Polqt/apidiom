from pathlib import Path

from fastapi.testclient import TestClient

from apidiom.pipeline import PipelineResult
from apidiom.web import app as web_app


def _result(
    *,
    code: str = "generated client",
    tier: str = "builtin",
    unknowns: list[str] | None = None,
    notes: list[str] | None = None,
    input_kind: str | None = "openapi",
    input_kind_source: str | None = "detected",
) -> PipelineResult:
    return PipelineResult(
        spec={"openapi": "3.1.0"},
        model=None,
        generated_client=code,
        generated_files={"client.py": code},
        codegen_tier=tier,
        unverified_items=unknowns or [],
        notes=notes or [],
        input_kind=input_kind,
        input_kind_source=input_kind_source,
    )


def test_home_returns_form() -> None:
    client = TestClient(web_app.app)

    response = client.get("/")

    assert response.status_code == 200
    assert "<form" in response.text
    assert 'name="source_url"' in response.text
    assert 'name="source_file"' in response.text
    assert "free-tier data may be used for training" in response.text


def test_generate_fragment_contains_generated_code_and_tier(monkeypatch) -> None:
    monkeypatch.setattr(
        web_app.pipeline,
        "generate_client",
        lambda *args, **kwargs: _result(code="class Client: pass", tier="builtin"),
    )
    client = TestClient(web_app.app)

    response = client.post(
        "/generate",
        data={
            "source_url": "tests/fixtures/petstore.yaml",
            "provider": "null",
            "lang": "python",
            "codegen": "builtin",
            "input_kind": "openapi",
        },
    )

    assert response.status_code == 200
    assert "class Client: pass" in response.text
    assert "builtin" in response.text


def test_web_result_code_matches_shared_pipeline_result(monkeypatch) -> None:
    expected = _result(code="shared pipeline code")
    monkeypatch.setattr(web_app.pipeline, "generate_client", lambda *a, **k: expected)
    client = TestClient(web_app.app)

    response = client.post(
        "/generate?format=json",
        data={
            "source_url": "tests/fixtures/petstore.yaml",
            "provider": "null",
            "lang": "python",
            "codegen": "builtin",
            "input_kind": "openapi",
        },
    )

    assert response.status_code == 200
    assert response.json()["code"] == expected.generated_client


def test_generate_json_variant_returns_agent_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        web_app.pipeline,
        "generate_client",
        lambda *args, **kwargs: _result(
            code="client",
            tier="builtin",
            unknowns=["$.paths./pets.get.parameters[0]: type"],
            notes=["conflict kept first value"],
        ),
    )
    client = TestClient(web_app.app)

    response = client.post(
        "/generate",
        headers={"Accept": "application/json"},
        data={
            "source_url": "tests/fixtures/petstore.yaml",
            "provider": "null",
            "lang": "python",
            "codegen": "builtin",
            "input_kind": "openapi",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "code": "client",
        "unknowns": ["$.paths./pets.get.parameters[0]: type"],
        "tier": "builtin",
        "notes": ["conflict kept first value"],
        "input_kind": "openapi",
        "input_kind_source": "detected",
    }


def test_unknowns_render_warning_banner(monkeypatch) -> None:
    monkeypatch.setattr(
        web_app.pipeline,
        "generate_client",
        lambda *args, **kwargs: _result(unknowns=["type"]),
    )
    client = TestClient(web_app.app)

    response = client.post(
        "/generate",
        data={
            "source_url": "tests/fixtures/petstore.yaml",
            "provider": "null",
            "lang": "python",
            "codegen": "builtin",
            "input_kind": "openapi",
        },
    )

    assert "1 field could not be verified from the docs" in response.text
    assert "type" in response.text


def test_generate_error_returns_clean_fragment(monkeypatch) -> None:
    def raise_pipeline_error(*args, **kwargs) -> PipelineResult:
        raise RuntimeError("Provider null is not ready. Use --provider ollama.")

    monkeypatch.setattr(web_app.pipeline, "generate_client", raise_pipeline_error)
    client = TestClient(web_app.app)

    response = client.post(
        "/generate",
        data={
            "source_url": "tests/fixtures/petstore.yaml",
            "provider": "null",
            "lang": "python",
            "codegen": "builtin",
            "input_kind": "openapi",
        },
    )

    assert response.status_code == 200
    assert "Provider null is not ready" in response.text
    assert "Traceback" not in response.text


def test_generate_requires_exactly_one_source() -> None:
    client = TestClient(web_app.app)

    response = client.post(
        "/generate",
        data={
            "provider": "null",
            "lang": "python",
            "codegen": "builtin",
            "input_kind": "openapi",
        },
    )

    assert response.status_code == 200
    assert "Provide exactly one input" in response.text


def test_generate_rejects_both_url_and_file() -> None:
    client = TestClient(web_app.app)

    response = client.post(
        "/generate",
        data={
            "source_url": "tests/fixtures/petstore.yaml",
            "provider": "null",
            "lang": "python",
            "codegen": "builtin",
            "input_kind": "openapi",
        },
        files={"source_file": ("docs.txt", b"GET /pets", "text/plain")},
    )

    assert response.status_code == 200
    assert "Provide exactly one input" in response.text


def test_file_upload_source_reaches_pipeline(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_generate_client(source: str | Path, **kwargs) -> PipelineResult:
        seen["source"] = source
        seen["kwargs"] = kwargs
        return _result(code="uploaded")

    monkeypatch.setattr(web_app.pipeline, "generate_client", fake_generate_client)
    client = TestClient(web_app.app)

    response = client.post(
        "/generate",
        data={
            "provider": "null",
            "lang": "python",
            "codegen": "builtin",
            "input_kind": "unstructured",
        },
        files={"source_file": ("docs.txt", b"GET /pets", "text/plain")},
    )

    assert response.status_code == 200
    assert seen["source"] == "GET /pets"
    assert response.text.count("uploaded") >= 1
