import type { APIEndpoint, APIModel, AuthScheme, OpenAPIParam, RequestBody, Doc } from "../model";

export function parseOpenAPI(doc: Doc): APIModel {
  if (typeof doc["openapi"] !== "string" || !doc["openapi"].startsWith("3")) {
    throw new Error("Only OpenAPI 3.x documents are supported.");
  }

  const info = (doc["info"] as Doc) ?? {};
  const servers = (doc["servers"] as Doc[]) ?? [];
  const paths = (doc["paths"] as Record<string, Doc>) ?? {};
  const components = (doc["components"] as Doc) ?? {};
  const securitySchemes = (components["securitySchemes"] as Record<string, Doc>) ?? {};

  const serverUrl =
    servers.length > 0 ? String((servers[0] as Doc)["url"] ?? "") : "";

  const endpoints: APIEndpoint[] = [];
  for (const [path, pathItem] of Object.entries(paths)) {
    for (const method of ["get", "post", "put", "patch", "delete", "head", "options"]) {
      const op = (pathItem as Record<string, Doc>)[method];
      if (!op) continue;
      endpoints.push(parseEndpoint(path, method.toUpperCase(), op));
    }
  }

  const authSchemes: AuthScheme[] = Object.entries(securitySchemes).map(
    ([name, scheme]) => parseAuthScheme(name, scheme)
  );

  return {
    title: String(info["title"] ?? "API"),
    version: String(info["version"] ?? "0.0.0"),
    serverUrl,
    endpoints,
    authSchemes,
  };
}

function parseEndpoint(path: string, method: string, op: Doc): APIEndpoint {
  const rawParams = (op["parameters"] as Doc[]) ?? [];
  const parameters: OpenAPIParam[] = rawParams.map((p) => ({
    name: String(p["name"] ?? ""),
    in: p["in"] as OpenAPIParam["in"],
    required: Boolean(p["required"] ?? false),
    description: p["description"] ? String(p["description"]) : undefined,
    schema: (p["schema"] as Record<string, unknown>) ?? {},
  }));

  let requestBody: RequestBody | undefined;
  if (op["requestBody"]) {
    const rb = op["requestBody"] as Doc;
    const content = (rb["content"] as Record<string, Doc>) ?? {};
    const jsonContent = content["application/json"] as Doc | undefined;
    const schema = jsonContent ? ((jsonContent["schema"] as Record<string, unknown>) ?? {}) : {};
    requestBody = {
      required: Boolean(rb["required"] ?? false),
      description: rb["description"] ? String(rb["description"]) : undefined,
      schema,
    };
  }

  const operationId =
    op["operationId"]
      ? String(op["operationId"])
      : `${method.toLowerCase()}_${path.replace(/[^a-zA-Z0-9]/g, "_")}`;

  return {
    path,
    method,
    operationId,
    summary: op["summary"] ? String(op["summary"]) : undefined,
    description: op["description"] ? String(op["description"]) : undefined,
    tags: (op["tags"] as string[]) ?? [],
    parameters,
    requestBody,
  };
}

function parseAuthScheme(name: string, scheme: Doc): AuthScheme {
  return {
    name,
    type: scheme["type"] as AuthScheme["type"],
    scheme: scheme["scheme"] ? String(scheme["scheme"]) : undefined,
    apiKeyIn: scheme["in"] as AuthScheme["apiKeyIn"] | undefined,
    apiKeyHeaderName: scheme["name"] ? String(scheme["name"]) : undefined,
  };
}
