from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pyperclip

from apidiom.pipeline import PipelineResult


class ClipboardModule(Protocol):
    class PyperclipException(Exception):
        pass

    def copy(self, text: str) -> None: ...


class OutputError(RuntimeError):
    pass


def write_output(
    result: PipelineResult,
    *,
    output: Path | None = None,
    clipboard: bool = False,
    force: bool = False,
    clipboard_module: ClipboardModule = pyperclip,
    stdout: object | None = None,
    stderr: object | None = None,
) -> None:
    stdout_writer = stdout if callable(stdout) else print
    stderr_writer = stderr if callable(stderr) else print
    client_text = result.generated_client or ""

    if output is not None:
        _write_path(result, output=output, force=force)
        return

    if clipboard:
        try:
            clipboard_module.copy(client_text)
        except clipboard_module.PyperclipException:
            stderr_writer(
                "Clipboard unavailable; printing generated client to stdout instead."
            )
            stdout_writer(client_text)
        return

    stdout_writer(client_text)


def _write_path(result: PipelineResult, *, output: Path, force: bool) -> None:
    files = result.generated_files
    if result.codegen_tier == "openapi-generator" and len(files) > 1:
        _write_directory(files, output=output, force=force)
        return
    if result.codegen_tier == "mcp" and "README.md" in files:
        readme_output = output.parent / "README.md"
        if readme_output.exists() and not force:
            raise OutputError(
                f"Refusing to overwrite existing file: {readme_output}. Use --force."
            )
        _write_file(result.generated_client or "", output=output, force=force)
        readme_text = files["README.md"].replace(
            "<generated-server-file>",
            output.name,
        )
        _write_file(readme_text, output=readme_output, force=force)
        return
    _write_file(result.generated_client or "", output=output, force=force)


def _write_file(text: str, *, output: Path, force: bool) -> None:
    if output.exists() and not force:
        raise OutputError(
            f"Refusing to overwrite existing file: {output}. Use --force."
        )
    if output.exists() and output.is_dir():
        raise OutputError(f"Output path is a directory, expected file: {output}.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def _write_directory(files: dict[str, str], *, output: Path, force: bool) -> None:
    if output.exists() and output.is_file():
        raise OutputError(f"Output path is a file, expected directory: {output}.")
    if output.exists() and any(output.iterdir()) and not force:
        raise OutputError(
            f"Refusing to overwrite non-empty directory: {output}. Use --force."
        )
    output.mkdir(parents=True, exist_ok=True)
    for relative_path, content in files.items():
        target = output / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
