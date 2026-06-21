import type { APIModel, AuthConfig } from "./model";

export function extractAuth(model: APIModel, serviceName?: string): AuthConfig[] {
  const prefix = (serviceName ?? "api").toUpperCase().replace(/[^A-Z0-9]/g, "_");
  const result: AuthConfig[] = [];

  for (const scheme of model.authSchemes) {
    if (scheme.type === "apiKey") {
      const keyName = scheme.apiKeyHeaderName ?? scheme.name;
      if (scheme.apiKeyIn === "query") {
        result.push({
          envVar: `${prefix}_${toEnvKey(keyName)}`,
          headerName: keyName,
          headerFormat: "{value}",
          queryParam: keyName,  // signals query-param auth
        });
      } else {
        // header (default)
        result.push({
          envVar: `${prefix}_${toEnvKey(keyName)}`,
          headerName: keyName,
          headerFormat: "{value}",
        });
      }
    } else if (scheme.type === "http" && scheme.scheme?.toLowerCase() === "bearer") {
      result.push({
        envVar: `${prefix}_BEARER_TOKEN`,
        headerName: "Authorization",
        headerFormat: "Bearer {value}",
      });
    } else if (scheme.type === "http" && scheme.scheme?.toLowerCase() === "basic") {
      result.push({
        envVar: `${prefix}_BASIC_TOKEN`,
        headerName: "Authorization",
        headerFormat: "Basic {value}",
      });
    }
    // oauth2 and openIdConnect: skip — too complex for generated static clients
  }

  return result;
}

function toEnvKey(name: string): string {
  return name.toUpperCase().replace(/[^A-Z0-9]/g, "_");
}
