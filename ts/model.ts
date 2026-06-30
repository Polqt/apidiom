export type Doc = Record<string, unknown>;

export interface OpenAPIParam {
  name: string;
  in: "path" | "query" | "header" | "cookie";
  required: boolean;
  description?: string;
  schema: Record<string, unknown>;
}

export interface RequestBody {
  required: boolean;
  description?: string;
  schema: Record<string, unknown>;
}

export interface APIEndpoint {
  path: string;
  method: string;
  operationId: string;
  summary?: string;
  description?: string;
  tags: string[];
  parameters: OpenAPIParam[];
  requestBody?: RequestBody;
}

type AuthType = "apiKey" | "http" | "oauth2" | "openIdConnect";

export interface AuthScheme {
  name: string;
  type: AuthType;
  scheme?: string;       // "bearer" | "basic" for http type
  apiKeyIn?: "header" | "query" | "cookie";
  apiKeyHeaderName?: string;
}

export interface APIModel {
  title: string;
  version: string;
  serverUrl: string;
  endpoints: APIEndpoint[];
  authSchemes: AuthScheme[];
}

export interface AuthConfig {
  envVar: string;         // e.g. "STRIPE_API_KEY"
  headerName: string;     // e.g. "Authorization"
  headerFormat: string;   // e.g. "Bearer {value}" or "{value}"
  queryParam?: string;    // set when auth goes in query string, not header
}
