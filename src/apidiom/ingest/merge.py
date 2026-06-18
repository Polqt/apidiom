from __future__ import annotations

from apidiom.models import APIClientModel, APIEndpoint, AuthScheme


def merge_models(models: list[APIClientModel]) -> APIClientModel:
    """Merge API models and deduplicate endpoints by operation ID."""
    if not models:
        raise ValueError("At least one OpenAPI model is required.")

    seen_ops: set[str] = set()
    endpoints: list[APIEndpoint] = []
    auth_schemes: list[AuthScheme] = []
    seen_auth: set[str] = set()

    for model in models:
        for endpoint in model.endpoints:
            key = endpoint.operation_id or f"{endpoint.method}:{endpoint.path}"
            if key in seen_ops:
                continue
            seen_ops.add(key)
            endpoints.append(endpoint)
        for scheme in model.auth_schemes:
            if scheme.name in seen_auth:
                continue
            seen_auth.add(scheme.name)
            auth_schemes.append(scheme)

    return APIClientModel(
        title="merged",
        version="0.0.0",
        source=", ".join(model.source for model in models),
        endpoints=endpoints,
        auth_schemes=auth_schemes,
    )
