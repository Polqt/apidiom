from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

HTTPMethod = Literal[
    "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"
]
ParameterLocation = Literal["path", "query"]


class OpenAPISchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: dict[str, Any]


class APIParameter(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    location: ParameterLocation
    required: bool
    schema_model: OpenAPISchema
    description: str | None = None


class APIResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status_code: str
    description: str | None = None
    schema_model: OpenAPISchema | None = None


class AuthScheme(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    type: str
    scheme: str | None = None
    bearer_format: str | None = None
    api_key_name: str | None = None
    api_key_in: str | None = None


class APIEndpoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    method: HTTPMethod
    operation_id: str | None = None
    summary: str | None = None
    path_parameters: list[APIParameter] = Field(default_factory=list)
    query_parameters: list[APIParameter] = Field(default_factory=list)
    request_schema: OpenAPISchema | None = None
    response_schemas: list[APIResponse] = Field(default_factory=list)
    auth_schemes: list[str] = Field(default_factory=list)


class APIClientModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    version: str
    source: str
    endpoints: list[APIEndpoint] = Field(default_factory=list)
    auth_schemes: list[AuthScheme] = Field(default_factory=list)

    def endpoint(self, method: str, path: str) -> APIEndpoint:
        normalized_method = method.upper()
        for endpoint in self.endpoints:
            if endpoint.method == normalized_method and endpoint.path == path:
                return endpoint
        raise KeyError(f"Endpoint not found: {normalized_method} {path}")
