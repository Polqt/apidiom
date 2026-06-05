from pathlib import Path

import pytest

from apidiom.ingest.openapi_ingest import OpenAPIIngestError, load_openapi

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_openapi_normalizes_petstore_endpoints() -> None:
    api = load_openapi(FIXTURES / "petstore.yaml")

    assert api.title == "Swagger Petstore"
    assert api.version == "1.0.0"
    assert api.source == str(FIXTURES / "petstore.yaml")
    assert len(api.endpoints) == 3

    list_pets = api.endpoint("GET", "/pets")
    assert list_pets.operation_id == "listPets"
    assert list_pets.summary == "List all pets"
    assert [parameter.name for parameter in list_pets.query_parameters] == ["limit"]
    assert list_pets.query_parameters[0].schema_model.value["type"] == "integer"
    assert list_pets.path_parameters == []
    assert list_pets.response_schemas[0].status_code == "200"
    list_pets_response_schema = list_pets.response_schemas[0].schema_model
    assert list_pets_response_schema is not None
    assert list_pets_response_schema.value["type"] == "array"
    assert list_pets_response_schema.value["items"]["$ref"].endswith("/Pet")

    create_pet = api.endpoint("POST", "/pets")
    assert create_pet.auth_schemes == ["api_key"]
    assert create_pet.request_schema is not None
    assert create_pet.request_schema.value["$ref"].endswith("/Pet")
    assert create_pet.response_schemas[0].status_code == "201"

    get_pet = api.endpoint("GET", "/pets/{petId}")
    assert [parameter.name for parameter in get_pet.path_parameters] == ["petId"]
    assert get_pet.path_parameters[0].required is True
    assert get_pet.path_parameters[0].schema_model.value["format"] == "int64"

    assert api.auth_schemes[0].name == "api_key"
    assert api.auth_schemes[0].type == "apiKey"
    assert api.auth_schemes[0].api_key_name == "api_key"
    assert api.auth_schemes[0].api_key_in == "header"


def test_load_openapi_accepts_json_file() -> None:
    api = load_openapi(FIXTURES / "petstore.json")

    assert api.endpoint("GET", "/pets").operation_id == "listPets"


def test_load_openapi_missing_file_raises_actionable_error() -> None:
    missing = FIXTURES / "missing.yaml"

    with pytest.raises(OpenAPIIngestError, match="OpenAPI file not found"):
        load_openapi(missing)


def test_load_openapi_invalid_yaml_raises_actionable_error() -> None:
    with pytest.raises(OpenAPIIngestError, match="Could not parse OpenAPI document"):
        load_openapi(FIXTURES / "invalid-openapi.txt")


def test_load_openapi_validation_failure_raises_actionable_error() -> None:
    with pytest.raises(OpenAPIIngestError, match="OpenAPI validation failed"):
        load_openapi(FIXTURES / "validation_failure.yaml")
