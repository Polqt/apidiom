from apidiom.ingest.discovery import discover_openapi_spec


def test_discover_openapi_spec_returns_first_matching_common_path() -> None:
    calls: list[str] = []

    def fetch(url: str) -> str:
        calls.append(url)
        if url.endswith("/openapi.yaml"):
            return "openapi: 3.1.0\ninfo: {title: Demo, version: '1'}\npaths: {}"
        raise OSError("missing")

    found = discover_openapi_spec("https://api.example.test", fetch=fetch)

    assert found == "https://api.example.test/openapi.yaml"
    assert calls[:2] == [
        "https://api.example.test/openapi.json",
        "https://api.example.test/openapi.yaml",
    ]


def test_discover_openapi_spec_returns_none_when_missing() -> None:
    assert (
        discover_openapi_spec(
            "https://api.example.test",
            fetch=lambda _url: "not yaml: [",
        )
        is None
    )
