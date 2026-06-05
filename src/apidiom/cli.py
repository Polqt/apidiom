from pathlib import Path
from typing import cast

import click

from apidiom.config import GEMINI_PRIVACY_WARNING, readiness_reason
from apidiom.generate.codegen import CodegenMode
from apidiom.llm.provider import get_provider
from apidiom.output.writer import OutputError, write_output
from apidiom.pipeline import InputKind, Language, generate_client

_PROVIDERS = ("gemini", "ollama", "null")
_CODEGEN_MODES = ("auto", "openapi-generator", "builtin")
_INPUT_KINDS = ("auto", "openapi", "unstructured")


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--provider",
    type=click.Choice(_PROVIDERS),
    default="null",
    show_default=True,
    help="LLM provider for commands that need model access.",
)
@click.option(
    "--codegen",
    type=click.Choice(_CODEGEN_MODES),
    default="auto",
    show_default=True,
    help="Client generation backend.",
)
@click.pass_context
def main(ctx: click.Context, provider: str, codegen: str) -> None:
    """apidiom turns API documentation into idiomatic API clients."""
    ctx.ensure_object(dict)
    ctx.obj["provider"] = provider
    ctx.obj["codegen"] = codegen


@main.command()
@click.option(
    "--provider",
    type=click.Choice(_PROVIDERS),
    default=None,
    help="Provider to check. Defaults to the global --provider value.",
)
@click.pass_context
def check(ctx: click.Context, provider: str | None) -> None:
    """Check whether an LLM provider is ready."""
    selected_provider = provider or ctx.obj["provider"]
    if selected_provider == "gemini":
        click.echo(GEMINI_PRIVACY_WARNING)

    llm_provider = get_provider(selected_provider)
    if llm_provider.is_available():
        click.echo(f"Provider {selected_provider} is ready.")
        return

    click.echo(
        f"Provider {selected_provider} is not ready: "
        f"{readiness_reason(selected_provider)}"
    )
    raise click.exceptions.Exit(1)


@main.command()
@click.argument("source")
@click.option(
    "--input-kind",
    type=click.Choice(_INPUT_KINDS),
    default="auto",
    show_default=True,
    help="Input type to process. Auto detects OpenAPI specs conservatively.",
)
@click.option("--provider", type=click.Choice(_PROVIDERS), default=None)
@click.option("--codegen", type=click.Choice(_CODEGEN_MODES), default=None)
@click.option(
    "--lang",
    type=click.Choice(("python",)),
    default="python",
    show_default=True,
)
@click.option("--output", type=click.Path(path_type=Path), default=None)
@click.option("--clipboard", is_flag=True, help="Copy generated client to clipboard.")
@click.option("--force", is_flag=True, help="Overwrite existing output paths.")
@click.option("--quiet", is_flag=True, help="Suppress unverified-field summary.")
@click.pass_context
def generate(
    ctx: click.Context,
    source: str,
    input_kind: str,
    provider: str | None,
    codegen: str | None,
    lang: str,
    output: Path | None,
    clipboard: bool,
    force: bool,
    quiet: bool,
) -> None:
    """Generate a Python httpx client.

    Example:
      apidiom generate https://example.com/openapi.yaml --output client.py
    """
    selected_provider = provider or ctx.obj["provider"]
    selected_codegen = codegen or ctx.obj["codegen"]
    selected_input_kind = _input_kind_override(input_kind)
    llm_provider = get_provider(selected_provider)

    if selected_provider == "gemini":
        click.echo(GEMINI_PRIVACY_WARNING, err=True)
    if not llm_provider.is_available():
        _fail(
            f"Provider {selected_provider} is not ready: "
            f"{readiness_reason(selected_provider)}"
        )

    try:
        result = generate_client(
            source,
            provider=llm_provider,
            lang=cast(Language, lang),
            input_kind=selected_input_kind,
            codegen=cast(CodegenMode, selected_codegen),
        )
        write_output(
            result,
            output=output,
            clipboard=clipboard,
            force=force,
            stdout=click.echo,
            stderr=lambda message: click.echo(message, err=True),
        )
    except (OSError, RuntimeError, ValueError, OutputError) as exc:
        _fail(str(exc))

    if not quiet:
        _print_summary(result)


def _print_summary(result: object) -> None:
    input_kind = getattr(result, "input_kind", None)
    input_kind_source = getattr(result, "input_kind_source", None)
    if input_kind_source == "detected" and input_kind is not None:
        click.echo(f"Detected input kind: {input_kind}", err=True)
    tier = getattr(result, "codegen_tier", None) or "unknown"
    click.echo(f"Codegen tier: {tier}", err=True)
    unknowns = list(getattr(result, "unverified_items", []))
    if not unknowns:
        click.echo("All generated fields were verified from the input.", err=True)
        return
    noun = "field" if len(unknowns) == 1 else "fields"
    click.echo(
        f"{len(unknowns)} {noun} could not be verified from the docs:",
        err=True,
    )
    for item in unknowns:
        click.echo(f"- {item}", err=True)


def _fail(message: str) -> None:
    raise click.ClickException(message)


def _input_kind_override(input_kind: str) -> InputKind | None:
    if input_kind == "auto":
        return None
    return cast(InputKind, input_kind)
