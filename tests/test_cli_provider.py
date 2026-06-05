from click.testing import CliRunner

from apidiom.cli import main


def test_check_reports_null_provider_ready() -> None:
    result = CliRunner().invoke(main, ["check", "--provider", "null"])

    assert result.exit_code == 0
    assert "Provider null is ready." in result.output


def test_check_prints_gemini_privacy_warning(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    result = CliRunner().invoke(main, ["check", "--provider", "gemini"])

    assert result.exit_code == 0
    assert "Gemini free-tier data may be used for training" in result.output
    assert "Provider gemini is ready." in result.output


def test_check_reports_not_ready_with_reason(
    monkeypatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = CliRunner().invoke(main, ["check", "--provider", "gemini"])

    assert result.exit_code == 1
    assert "Provider gemini is not ready:" in result.output
    assert "Set GEMINI_API_KEY" in result.output
