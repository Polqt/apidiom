from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, cast

import click

from apidiom.config import GEMINI_PRIVACY_WARNING, readiness_reason
from apidiom.generate.codegen import CodegenMode
from apidiom.generate.mcp import MCPOperationSummary, validate_mcp_server_text
from apidiom.generate.schema_gen import SchemaFormat
from apidiom.llm.provider import LLMProvider, get_provider
from apidiom.output.writer import OutputError, write_output
from apidiom.pipeline import (
    InputKind,
    Language,
    ToolGenerationRequest,
    generate_agent_tools,
    generate_client,
    list_mcp_operations,
)

_PROVIDERS = ("gemini", "ollama", "null")
_CODEGEN_MODES = ("auto", "openapi-generator", "builtin")
_INPUT_KINDS = ("auto", "openapi", "unstructured")
_SCHEMA_FORMATS = ("anthropic", "openai")


@dataclass(frozen=True)
class _ToolArgs:
    sources: list[str]
    include_tags: list[str]
    include_operations: list[str]
    check: bool = False
    list_only: bool = False
    enrich_docs: bool = False
    schema_format: str = "anthropic"


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


@main.command(
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    }
)
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
    if source == "mcp":
        _generate_mcp(
            ctx,
            provider=provider,
            output=output,
            clipboard=clipboard,
            force=force,
            quiet=quiet,
        )
        return
    if source == "langchain":
        _generate_langchain(
            ctx,
            provider=provider,
            output=output,
            clipboard=clipboard,
            force=force,
            quiet=quiet,
        )
        return
    if source == "schema":
        _generate_schema(
            ctx,
            provider=provider,
            output=output,
            clipboard=clipboard,
            force=force,
            quiet=quiet,
        )
        return
    if ctx.args:
        _fail(f"Unexpected arguments: {' '.join(ctx.args)}")

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


def _generate_mcp(
    ctx: click.Context,
    *,
    provider: str | None,
    output: Path | None,
    clipboard: bool,
    force: bool,
    quiet: bool,
) -> None:
    parsed = _parse_tool_args(ctx.args, command="mcp")
    try:
        if parsed.list_only:
            _print_mcp_operations(
                list_mcp_operations(
                    parsed.sources,
                    include_tags=parsed.include_tags,
                    include_operations=parsed.include_operations,
                )
            )
            return
        result = generate_agent_tools(
            ToolGenerationRequest(
                target="mcp",
                sources=parsed.sources,
                include_tags=parsed.include_tags,
                include_operations=parsed.include_operations,
                provider=_tool_provider(ctx, provider, enrich_docs=parsed.enrich_docs),
                enrich_docs=parsed.enrich_docs,
            )
        )
        if parsed.check:
            _print_mcp_check(result.generated_client or "")
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


def _generate_langchain(
    ctx: click.Context,
    *,
    provider: str | None,
    output: Path | None,
    clipboard: bool,
    force: bool,
    quiet: bool,
) -> None:
    parsed = _parse_tool_args(ctx.args, command="langchain")
    try:
        result = generate_agent_tools(
            ToolGenerationRequest(
                target="langchain",
                sources=parsed.sources,
                include_tags=parsed.include_tags,
                include_operations=parsed.include_operations,
                provider=_tool_provider(ctx, provider, enrich_docs=parsed.enrich_docs),
                enrich_docs=parsed.enrich_docs,
            )
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


def _generate_schema(
    ctx: click.Context,
    *,
    provider: str | None,
    output: Path | None,
    clipboard: bool,
    force: bool,
    quiet: bool,
) -> None:
    parsed = _parse_tool_args(ctx.args, command="schema")
    try:
        result = generate_agent_tools(
            ToolGenerationRequest(
                target="schema",
                sources=parsed.sources,
                schema_format=cast(SchemaFormat, parsed.schema_format),
                include_tags=parsed.include_tags,
                include_operations=parsed.include_operations,
                provider=_tool_provider(ctx, provider, enrich_docs=parsed.enrich_docs),
                enrich_docs=parsed.enrich_docs,
            )
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


def _parse_tool_args(args: list[str], *, command: str) -> _ToolArgs:
    if not args:
        _fail(f"Usage: apidiom generate {command} <openapi-spec>")
    sources: list[str] = []
    include_tags: list[str] = []
    include_operations: list[str] = []
    check = False
    list_only = False
    enrich_docs = False
    schema_format = "anthropic"
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--check":
            if command != "mcp":
                _fail("--check is only supported for MCP generation")
            check = True
            index += 1
            continue
        if arg == "--list":
            if command != "mcp":
                _fail("--list is only supported for MCP generation")
            list_only = True
            index += 1
            continue
        if arg == "--enrich-docs":
            enrich_docs = True
            index += 1
            continue
        if arg in {"--tag", "--include", "--format"}:
            if index + 1 >= len(args):
                _fail(f"{arg} requires a value")
            value = args[index + 1]
            index += 2
        elif arg.startswith("--tag="):
            value = arg.removeprefix("--tag=")
            arg = "--tag"
            index += 1
        elif arg.startswith("--include="):
            value = arg.removeprefix("--include=")
            arg = "--include"
            index += 1
        elif arg.startswith("--format="):
            value = arg.removeprefix("--format=")
            arg = "--format"
            index += 1
        else:
            if arg.startswith("-"):
                _fail(f"Unexpected {command} argument: {arg}")
            sources.append(arg)
            index += 1
            continue

        if arg == "--tag":
            include_tags.append(value)
        elif arg == "--include":
            include_operations.append(value)
        else:
            if command != "schema":
                _fail("--format is only supported for schema generation")
            if value not in _SCHEMA_FORMATS:
                _fail("--format must be 'anthropic' or 'openai'")
            schema_format = value
    if not sources:
        _fail(f"Usage: apidiom generate {command} <openapi-spec>")
    return _ToolArgs(
        sources=sources,
        include_tags=include_tags,
        include_operations=include_operations,
        check=check,
        list_only=list_only,
        enrich_docs=enrich_docs,
        schema_format=schema_format,
    )


def _tool_provider(
    ctx: click.Context,
    provider: str | None,
    *,
    enrich_docs: bool,
) -> LLMProvider | None:
    if not enrich_docs:
        return None
    selected_provider = provider or ctx.obj["provider"]
    if selected_provider == "null":
        _fail("--enrich-docs needs --provider gemini or --provider ollama")
    llm_provider = get_provider(selected_provider)
    if not llm_provider.is_available():
        _fail(
            f"Provider {selected_provider} is not ready: "
            f"{readiness_reason(selected_provider)}"
        )
    return llm_provider


def _print_mcp_operations(operations: list[MCPOperationSummary]) -> None:
    for operation in operations:
        tags = ", ".join(operation.tags)
        suffix = f" [tags: {tags}]" if tags else ""
        click.echo(
            f"{operation.selector} {operation.function_name} - "
            f"{operation.description}{suffix}"
        )


def _print_mcp_check(server_text: str) -> None:
    check = validate_mcp_server_text(server_text)
    click.echo(f"MCP check: {check.tool_count} tools", err=True)
    if check.env_vars:
        click.echo(f"Env vars: {', '.join(check.env_vars)}", err=True)


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


def _fail(message: str) -> NoReturn:
    raise click.ClickException(message)


def _input_kind_override(input_kind: str) -> InputKind | None:
    if input_kind == "auto":
        return None
    return cast(InputKind, input_kind)
