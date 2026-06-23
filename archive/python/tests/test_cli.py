from click.testing import CliRunner

from apidiom.cli import main


def test_help_displays_apidiom_name() -> None:
    runner = CliRunner()

    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "apidiom" in result.output
