# Apidiom

Apidiom turns an OpenAPI source into agent-ready tools while keeping generated
outputs portable and directly usable.

## Language

**OpenAPI source**:
A local file, URL, or built-in service name that identifies one OpenAPI document.
_Avoid_: Input, API docs

**Agent tool**:
One callable API operation with a name, description, and JSON input schema.
_Avoid_: Function, endpoint wrapper

**Tool catalog**:
The complete set of agent tools derived from an OpenAPI source.
_Avoid_: Tool list, registry

**Flat mode**:
An MCP output mode that exposes every agent tool directly.
_Avoid_: Normal mode, default mode

**Search mode**:
An MCP output mode that exposes discovery and dispatch meta-tools over a hidden
tool catalog.
_Avoid_: Compact mode, lazy mode

**Progressive discovery**:
The behavior that selects search mode when a tool catalog exceeds the configured
threshold.
_Avoid_: Auto filtering, tool truncation

**Generated MCP server**:
A standalone JavaScript program that exposes agent tools through MCP.
_Avoid_: MCP file, generated script
