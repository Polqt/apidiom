from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from bs4 import BeautifulSoup
from openapi_spec_validator import validate
from yaml import YAMLError, safe_load

from apidiom.ingest.openapi_ingest import normalize_openapi_document
from apidiom.llm.prompts import (
    EXTRACTION_SYSTEM,
    EXTRACTION_USER_TEMPLATE,
    REPAIR_SYSTEM,
)
from apidiom.llm.provider import LLMProvider
from apidiom.models import APIClientModel

_METHOD_BOUNDARY = re.compile(
    r"(?im)^(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|TRACE)\s+/[^\s]*"
)
_HEADING_BOUNDARY = re.compile(r"(?m)^#{1,6}\s+.+$")
_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


class DocToSpecError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        candidate_path: Path | None = None,
        validator_errors: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.candidate_path = candidate_path
        self.validator_errors = validator_errors or []


@dataclass(frozen=True)
class DocToSpecResult:
    spec: dict[str, Any]
    model: APIClientModel
    unverified_items: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def doc_to_spec(
    raw_documentation: str,
    *,
    provider: LLMProvider,
    token_budget: int = 6000,
    max_repair_attempts: int = 3,
    candidate_output_path: Path | None = None,
) -> DocToSpecResult:
    cleaned = clean_documentation(raw_documentation)
    chunks = chunk_documentation(cleaned, token_budget=token_budget)
    fragments: list[dict[str, Any]] = []
    context = _GlobalContext()

    for index, chunk in enumerate(chunks, start=1):
        fragment = _extract_fragment(
            provider=provider,
            chunk=chunk,
            index=index,
            total=len(chunks),
            context=context,
        )
        fragments.append(fragment)
        context.observe(fragment)

    merged = merge_openapi_fragments(fragments)
    pre_repair_endpoint_set = endpoint_set(merged)
    validated = _validate_or_repair(
        merged,
        provider=provider,
        pre_repair_endpoint_set=pre_repair_endpoint_set,
        max_repair_attempts=max_repair_attempts,
        candidate_output_path=candidate_output_path,
    )
    model = normalize_openapi_document(validated, "unstructured-docs")
    return DocToSpecResult(
        spec=validated,
        model=model,
        unverified_items=collect_unverified_items(validated),
        notes=collect_notes(validated),
    )


def clean_documentation(raw_documentation: str) -> str:
    postman_text = _flatten_postman(raw_documentation)
    if postman_text is not None:
        return postman_text

    soup = BeautifulSoup(raw_documentation, "lxml")
    if soup.find():
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()
        lines = [line.strip() for line in soup.get_text("\n").splitlines()]
        return "\n".join(line for line in lines if line)

    return "\n".join(line.rstrip() for line in raw_documentation.splitlines()).strip()


def chunk_documentation(cleaned_text: str, *, token_budget: int = 6000) -> list[str]:
    sections = _split_sections(cleaned_text)
    if not sections:
        return [cleaned_text.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for section in sections:
        section_tokens = _estimate_tokens(section)
        if current and current_tokens + section_tokens > token_budget:
            chunks.append("\n\n".join(current).strip())
            current = []
            current_tokens = 0
        current.append(section)
        current_tokens += section_tokens

    if current:
        chunks.append("\n\n".join(current).strip())
    return chunks


def merge_openapi_fragments(fragments: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "untitled", "version": "0.0.0"},
        "paths": {},
    }
    notes: list[str] = []

    for fragment in fragments:
        _merge_info(merged, fragment)
        _merge_servers(merged, fragment)
        _merge_security_schemes(merged, fragment, notes)
        _merge_schemas(merged, fragment, notes)
        _merge_paths(merged, fragment, notes)

    if notes:
        merged["x-apidiom-notes"] = notes
    if _needs_unknown_markers(merged):
        merged["x-apidiom-unknown"] = ["servers", "authentication"]
    return merged


def endpoint_set(spec: dict[str, Any]) -> set[tuple[str, str]]:
    paths = _mapping(spec.get("paths"))
    endpoints: set[tuple[str, str]] = set()
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in path_item:
            if method.lower() in _HTTP_METHODS:
                endpoints.add((path, method.lower()))
    return endpoints


def collect_unverified_items(spec: dict[str, Any]) -> list[str]:
    items: list[str] = []
    _collect_unknowns(spec, path="$", items=items)
    return items


def collect_notes(spec: dict[str, Any]) -> list[str]:
    notes = spec.get("x-apidiom-notes")
    if isinstance(notes, list):
        return [str(note) for note in notes]
    return []


def _extract_fragment(
    *,
    provider: LLMProvider,
    chunk: str,
    index: int,
    total: int,
    context: _GlobalContext,
) -> dict[str, Any]:
    prompt = EXTRACTION_USER_TEMPLATE.format(
        servers_or_unknown=context.servers_or_unknown,
        auth_or_unknown=context.auth_or_unknown,
        schema_names_or_none=context.schema_names_or_none,
        i=index,
        n=total,
        cleaned_chunk_text=chunk,
    )
    raw_text = _complete_json(provider, prompt=prompt, system=EXTRACTION_SYSTEM)
    try:
        return _parse_json_object(raw_text)
    except DocToSpecError:
        raw_text = _complete_json(provider, prompt=prompt, system=EXTRACTION_SYSTEM)
        return _parse_json_object(raw_text)


def _complete_json(provider: LLMProvider, *, prompt: str, system: str) -> str:
    return provider.complete(
        prompt,
        system=system,
        temperature=0.0,
        json_mode=True,
    ).text


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise DocToSpecError(
            "Model did not return valid JSON. Retry also failed."
        ) from exc

    if not isinstance(parsed, dict):
        raise DocToSpecError("Model returned JSON, but it was not an object.")
    return cast(dict[str, Any], parsed)


def _validate_or_repair(
    spec: dict[str, Any],
    *,
    provider: LLMProvider,
    pre_repair_endpoint_set: set[tuple[str, str]],
    max_repair_attempts: int,
    candidate_output_path: Path | None,
) -> dict[str, Any]:
    current = copy.deepcopy(spec)
    errors = _validation_errors(current)
    if not errors:
        return current

    for _attempt in range(max_repair_attempts):
        repair_prompt = (
            "VALIDATOR ERRORS\n"
            + "\n".join(errors)
            + "\n\nINVALID OPENAPI JSON\n"
            + json.dumps(current, indent=2, sort_keys=True)
        )
        repaired = _parse_json_object(
            _complete_json(provider, prompt=repair_prompt, system=REPAIR_SYSTEM)
        )
        if endpoint_set(repaired) != pre_repair_endpoint_set:
            raise DocToSpecError("Repair changed the endpoint set; rejecting it.")
        current = repaired
        errors = _validation_errors(current)
        if not errors:
            return current

    saved_path = _save_best_candidate(current, errors, candidate_output_path)
    raise DocToSpecError(
        "OpenAPI validation failed after 3 repair attempts. "
        f"Validator errors: {'; '.join(errors)}. "
        f"Best candidate saved to {saved_path}.",
        candidate_path=saved_path,
        validator_errors=errors,
    )


def _validation_errors(spec: dict[str, Any]) -> list[str]:
    try:
        validate(spec)
    except Exception as exc:
        return [str(exc)]
    return []


def _save_best_candidate(
    spec: dict[str, Any],
    errors: list[str],
    candidate_output_path: Path | None,
) -> Path:
    path = candidate_output_path or Path("apidiom-best-candidate-spec.json")
    payload = {
        "validator errors": errors,
        "candidate": spec,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _split_sections(cleaned_text: str) -> list[str]:
    starts = {match.start() for match in _HEADING_BOUNDARY.finditer(cleaned_text)}
    if not starts:
        starts.update(
            match.start() for match in _METHOD_BOUNDARY.finditer(cleaned_text)
        )
    if not starts:
        stripped = cleaned_text.strip()
        return [stripped] if stripped else []

    ordered = sorted(starts)
    sections: list[str] = []
    for index, start in enumerate(ordered):
        end = ordered[index + 1] if index + 1 < len(ordered) else len(cleaned_text)
        section = cleaned_text[start:end].strip()
        if section:
            sections.append(section)
    prefix = cleaned_text[: ordered[0]].strip()
    if prefix:
        sections.insert(0, prefix)
    return sections


def _estimate_tokens(text: str) -> int:
    return max(1, len(re.findall(r"\S+", text)))


def _flatten_postman(raw_documentation: str) -> str | None:
    try:
        parsed = json.loads(raw_documentation)
    except json.JSONDecodeError:
        try:
            parsed = safe_load(raw_documentation)
        except YAMLError:
            return None
    if not isinstance(parsed, dict) or "item" not in parsed:
        return None

    lines: list[str] = []
    _walk_postman_items(parsed.get("item"), lines)
    return "\n".join(lines).strip()


def _walk_postman_items(items: object, lines: list[str]) -> None:
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        request = item.get("request")
        if isinstance(request, dict):
            method = str(request.get("method", "")).upper()
            url = request.get("url")
            path = _postman_url_path(url)
            name = str(item.get("name", "")).strip()
            if name:
                lines.append(f"## {name}")
            if method and path:
                lines.append(f"{method} {path}")
        _walk_postman_items(item.get("item"), lines)


def _postman_url_path(url: object) -> str:
    if isinstance(url, str):
        return url
    if isinstance(url, dict):
        path = url.get("path")
        if isinstance(path, list):
            return "/" + "/".join(str(part) for part in path)
        raw = url.get("raw")
        if isinstance(raw, str):
            return raw
    return ""


def _merge_info(merged: dict[str, Any], fragment: dict[str, Any]) -> None:
    info = _mapping(fragment.get("info"))
    if not info:
        return
    if merged["info"]["title"] == "untitled" and isinstance(info.get("title"), str):
        merged["info"]["title"] = info["title"]
    if merged["info"]["version"] == "0.0.0" and isinstance(info.get("version"), str):
        merged["info"]["version"] = info["version"]


def _merge_servers(merged: dict[str, Any], fragment: dict[str, Any]) -> None:
    servers = fragment.get("servers")
    if isinstance(servers, list) and servers:
        merged.setdefault("servers", servers)


def _merge_security_schemes(
    merged: dict[str, Any],
    fragment: dict[str, Any],
    notes: list[str],
) -> None:
    schemes = _mapping(_mapping(fragment.get("components")).get("securitySchemes"))
    if not schemes:
        return
    components = merged.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    if not isinstance(security_schemes, dict):
        return
    for name, scheme in schemes.items():
        if name in security_schemes and security_schemes[name] != scheme:
            notes.append(f"Conflict for security scheme {name}; kept first value.")
            continue
        security_schemes[name] = scheme


def _merge_schemas(
    merged: dict[str, Any],
    fragment: dict[str, Any],
    notes: list[str],
) -> None:
    schemas = _mapping(_mapping(fragment.get("components")).get("schemas"))
    if not schemas:
        return
    components = merged.setdefault("components", {})
    merged_schemas = components.setdefault("schemas", {})
    if not isinstance(merged_schemas, dict):
        return
    for name, schema in schemas.items():
        if name in merged_schemas and merged_schemas[name] != schema:
            notes.append(f"Conflict for schema {name}; kept first value.")
            continue
        merged_schemas[name] = schema


def _merge_paths(
    merged: dict[str, Any],
    fragment: dict[str, Any],
    notes: list[str],
) -> None:
    paths = _mapping(fragment.get("paths"))
    merged_paths = _mapping(merged.get("paths"))
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        target_path = merged_paths.setdefault(path, {})
        if not isinstance(target_path, dict):
            continue
        for method, operation in path_item.items():
            method_key = method.lower()
            if method_key not in _HTTP_METHODS:
                continue
            if method_key in target_path and target_path[method_key] != operation:
                notes.append(
                    f"Conflict for endpoint {method_key.upper()} {path}; "
                    "kept first value."
                )
                continue
            target_path[method_key] = operation


def _needs_unknown_markers(spec: dict[str, Any]) -> bool:
    return bool(spec.get("paths")) and (
        "servers" not in spec
        or "securitySchemes" not in _mapping(spec.get("components"))
    )


def _collect_unknowns(value: object, *, path: str, items: list[str]) -> None:
    if isinstance(value, dict):
        unknown = value.get("x-apidiom-unknown")
        if isinstance(unknown, list):
            items.extend(f"{path}: {item}" for item in unknown)
        description = value.get("description")
        if isinstance(description, str) and "UNVERIFIED:" in description:
            items.append(f"{path}: {description}")
        for key, child in value.items():
            _collect_unknowns(child, path=f"{path}.{key}", items=items)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _collect_unknowns(child, path=f"{path}[{index}]", items=items)


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


class _GlobalContext:
    def __init__(self) -> None:
        self.servers: list[str] = []
        self.auth: list[str] = []
        self.schema_names: list[str] = []

    @property
    def servers_or_unknown(self) -> str:
        return ", ".join(self.servers) if self.servers else "unknown"

    @property
    def auth_or_unknown(self) -> str:
        return ", ".join(self.auth) if self.auth else "unknown"

    @property
    def schema_names_or_none(self) -> str:
        return ", ".join(self.schema_names) if self.schema_names else "none"

    def observe(self, fragment: dict[str, Any]) -> None:
        for server in fragment.get("servers", []):
            if isinstance(server, dict) and isinstance(server.get("url"), str):
                _append_unique(self.servers, server["url"])
        schemes = _mapping(_mapping(fragment.get("components")).get("securitySchemes"))
        for name in schemes:
            _append_unique(self.auth, name)
        schemas = _mapping(_mapping(fragment.get("components")).get("schemas"))
        for name in schemas:
            _append_unique(self.schema_names, name)


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
