# Agent Instructions

Build `apidiom` as a small, well-tested, open-source Python developer tool.

- Keep all real behavior in importable library code.
- Keep CLI and future web UI code thin.
- Prefer the simplest implementation that satisfies the current phase.
- Do not add paid services, accounts, databases, payments, sessions, or scope outside the current phase.
- Validate new behavior with tests before implementation.

## Skills

Project skills live in `.claude/skills/`. Read the relevant one before touching code.

- **`apidiom-style`** — conventions, toolchain, reusable helpers, test patterns. Read this before writing any code.
- **`openapi-to-mcp`** — feature spec for the OpenAPI → MCP server generator (`apidiom mcp <spec>`). Read this when working on `generate/mcp_generator.py` or the `mcp` CLI command.

## Active Feature: OpenAPI → MCP Server Generator

**Plan:** `.claude/plans/openapi-to-mcp.md`

`apidiom mcp <spec>` takes any OpenAPI spec and outputs a runnable MCP server Python file — one `@mcp.tool()` per endpoint. Agents (Claude, etc.) can then call real APIs through that server.

**Note:** `src/apidiom/mcp/server.py` is apidiom's OWN MCP server. The new feature generates MCP server files for external APIs. These are distinct.

New files:
- `src/apidiom/generate/mcp_generator.py`
- `src/apidiom/generate/templates/mcp_server.py.j2`
- `tests/test_mcp_generator.py`
- `tests/test_cli_mcp.py`

