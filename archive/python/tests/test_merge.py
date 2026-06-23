from apidiom.ingest.merge import merge_models
from apidiom.models import APIClientModel, APIEndpoint, AuthScheme


def test_merge_models_deduplicates_endpoints_and_auth() -> None:
    shared = APIEndpoint(path="/pets", method="GET", operation_id="listPets")
    first = APIClientModel(
        title="First",
        version="1",
        source="first",
        endpoints=[shared],
        auth_schemes=[AuthScheme(name="api_key", type="apiKey")],
    )
    second = APIClientModel(
        title="Second",
        version="1",
        source="second",
        endpoints=[
            shared,
            APIEndpoint(path="/users", method="GET", operation_id="listUsers"),
        ],
        auth_schemes=[
            AuthScheme(name="api_key", type="apiKey"),
            AuthScheme(name="bearerAuth", type="http", scheme="bearer"),
        ],
    )

    merged = merge_models([first, second])

    assert [endpoint.operation_id for endpoint in merged.endpoints] == [
        "listPets",
        "listUsers",
    ]
    assert [scheme.name for scheme in merged.auth_schemes] == [
        "api_key",
        "bearerAuth",
    ]
