from pathlib import Path

import pytest

from apidiom.output.writer import OutputError, write_output
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
        model=None,
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
        clipboard_module=BrokenClipboard(),
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

    write_output(_result(text="client"), clipboard=True, clipboard_module=clipboard)

    assert clipboard.copied == "client"
