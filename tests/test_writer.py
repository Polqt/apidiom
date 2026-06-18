from pathlib import Path
from typing import cast

import pytest

from apidiom.models import APIClientModel
from apidiom.output.writer import ClipboardModule, OutputError, write_output
from apidiom.pipeline import PipelineResult


class BrokenClipboard:
    class PyperclipException(RuntimeError):
        pass

    def copy(self, text: str) -> None:
        raise self.PyperclipException("no clipboard")


class WorkingClipboard:
    class PyperclipException(RuntimeError):
        pass

    def __init__(self) -> None:
        self.copied = ""

    def copy(self, text: str) -> None:
        self.copied = text


def _result(
    *,
    text: str = "client code",
    files: dict[str, str] | None = None,
    tier: str = "builtin",
) -> PipelineResult:
    return PipelineResult(
        spec={},
        model=APIClientModel(title="Test API", version="1.0.0", source="test"),
        generated_client=text,
        generated_files=files or {"client.py": text},
        codegen_tier=tier,
    )


def _clean(path: Path) -> None:
    if path.is_dir():
        import shutil

        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def test_writer_writes_single_file() -> None:
    output = Path("tests/fixtures/generated-client.py")
    _clean(output)

    write_output(_result(text="hello"), output=output)

    assert output.read_text(encoding="utf-8") == "hello"
    _clean(output)


def test_writer_writes_mcp_readme_next_to_server() -> None:
    output = Path("tests/fixtures/generated-mcp.py")
    readme = output.parent / "README.md"
    _clean(output)
    _clean(readme)

    write_output(
        _result(
            text="server",
            files={
                "server.py": "server",
                "README.md": "python <generated-server-file>",
            },
            tier="mcp",
        ),
        output=output,
    )

    assert output.read_text(encoding="utf-8") == "server"
    assert readme.read_text(encoding="utf-8") == "python generated-mcp.py"
    _clean(output)
    _clean(readme)


def test_writer_writes_mcp_directory_output() -> None:
    output = Path("tests/fixtures/generated-mcp-dir")
    _clean(output)

    write_output(
        _result(
            text="server",
            files={
                "server.py": "server",
                "README.md": "python <generated-server-file>",
            },
            tier="mcp",
        ),
        output=output,
    )

    assert (output / "server.py").read_text(encoding="utf-8") == "server"
    assert (output / "README.md").read_text(encoding="utf-8") == (
        "python <generated-server-file>"
    )
    _clean(output)


def test_writer_writes_multi_file_directory() -> None:
    output = Path("tests/fixtures/generated-client-dir")
    _clean(output)

    write_output(
        _result(
            files={"client.py": "client", "models/pet.py": "model"},
            tier="openapi-generator",
        ),
        output=output,
    )

    assert (output / "client.py").read_text(encoding="utf-8") == "client"
    assert (output / "models" / "pet.py").read_text(encoding="utf-8") == "model"
    _clean(output)


def test_writer_refuses_overwrite_without_force() -> None:
    output = Path("tests/fixtures/generated-existing.py")
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(OutputError, match="Refusing to overwrite"):
        write_output(_result(text="new"), output=output)

    assert output.read_text(encoding="utf-8") == "existing"
    _clean(output)


def test_writer_clipboard_missing_falls_back_to_stdout() -> None:
    stdout: list[str] = []
    stderr: list[str] = []

    write_output(
        _result(text="client"),
        clipboard=True,
        clipboard_module=cast(ClipboardModule, BrokenClipboard()),
        stdout=stdout.append,
        stderr=stderr.append,
    )

    assert stdout == ["client"]
    assert "Clipboard unavailable" in stderr[0]


def test_writer_stdout_default() -> None:
    stdout: list[str] = []

    write_output(_result(text="client"), stdout=stdout.append)

    assert stdout == ["client"]


def test_writer_clipboard_success() -> None:
    clipboard = WorkingClipboard()

    write_output(
        _result(text="client"),
        clipboard=True,
        clipboard_module=cast(ClipboardModule, clipboard),
    )

    assert clipboard.copied == "client"
