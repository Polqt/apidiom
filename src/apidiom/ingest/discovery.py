from __future__ import annotations

from collections.abc import Callable
from typing import cast
from urllib.error import URLError
from urllib.request import urlopen

import yaml

DISCOVERY_PATHS = [
    "/openapi.json",
    "/openapi.yaml",
    "/swagger.json",
    "/swagger.yaml",
    "/api-docs",
    "/api-docs.json",
    "/api/openapi.json",
    "/api/swagger.json",
    "/.well-known/openapi.json",
    "/v1/openapi.json",
    "/v2/openapi.json",
    "/v3/openapi.json",
]


def discover_openapi_spec(
    base_url: str,
    *,
    fetch: Callable[[str], str] | None = None,
) -> str | None:
    """Try common OpenAPI URLs and return the first valid spec URL."""
    read = fetch or _read_url
    for path in DISCOVERY_PATHS:
        url = base_url.rstrip("/") + path
        try:
            if _looks_like_openapi(read(url)):
                return url
        except (OSError, URLError, UnicodeDecodeError):
            continue
    return None


def _read_url(url: str) -> str:
    with urlopen(url, timeout=5) as response:  # noqa: S310
        body = cast(bytes, response.read())
        return body.decode("utf-8")


def _looks_like_openapi(text: str) -> bool:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return False
    return isinstance(doc, dict) and (
        isinstance(doc.get("openapi"), str) or isinstance(doc.get("swagger"), str)
    )
