from click.testing import CliRunner

from apidiom import cli
from apidiom.pipeline import PipelineResult


def test_generate_calls_pipeline_and_routes_stdout(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_generate_client(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return PipelineResult(
            spec={},
            model=None,
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
    assert calls[0]["kwargs"]["input_kind"] == "unstructured"
