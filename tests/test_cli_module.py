from __future__ import annotations

from pathlib import Path


def test_cli_module_entrypoint_exists() -> None:
    module = Path("src/apidiom/__main__.py")

    assert module.exists()
    assert "main()" in module.read_text(encoding="utf-8")
