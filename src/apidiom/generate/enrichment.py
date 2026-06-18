from __future__ import annotations

from apidiom.llm.provider import LLMProvider
from apidiom.models import APIEndpoint


def enrich_description(endpoint: APIEndpoint, provider: LLMProvider) -> str:
    """Write a short agent-tool description for sparse OpenAPI summaries."""
    if _description_is_rich_enough(endpoint):
        return endpoint.summary or f"{endpoint.method} {endpoint.path}"

    params = endpoint.path_parameters + endpoint.query_parameters
    body = endpoint.request_schema.value if endpoint.request_schema else None
    prompt = f"""Write a 1-2 sentence description for an AI agent tool.
                Method: {endpoint.method}
                Path: {endpoint.path}
                Summary: {endpoint.summary or "none"}
                Parameters: {[parameter.name for parameter in params]}
                Body: {body or "none"}

                Write only the description. No quotes. No prefix.
            """
    text = provider.complete(prompt, temperature=0.0, max_tokens=256).text.strip()
    return text or endpoint.summary or f"{endpoint.method} {endpoint.path}"


def _description_is_rich_enough(endpoint: APIEndpoint) -> bool:
    return len((endpoint.summary or "").split()) >= 8
