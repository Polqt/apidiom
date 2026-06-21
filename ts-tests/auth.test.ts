import { describe, it, expect } from "vitest";
import { extractAuth } from "../ts/auth";
import type { APIModel } from "../ts/model";

const BASE_MODEL: APIModel = {
  title: "Test API",
  version: "1.0.0",
  serverUrl: "https://api.example.com",
  endpoints: [],
  authSchemes: [],
};

describe("extractAuth", () => {
  it("returns empty array when no auth schemes", () => {
    expect(extractAuth(BASE_MODEL)).toEqual([]);
  });

  it("maps apiKey-in-header scheme to correct env var and header", () => {
    const model: APIModel = {
      ...BASE_MODEL,
      authSchemes: [
        { name: "api_key", type: "apiKey", apiKeyIn: "header", apiKeyHeaderName: "api_key" },
      ],
    };
    const result = extractAuth(model, "petstore");
    expect(result).toHaveLength(1);
    expect(result[0].envVar).toBe("PETSTORE_API_KEY");
    expect(result[0].headerName).toBe("api_key");
    expect(result[0].headerFormat).toBe("{value}");
  });

  it("maps http bearer scheme to Authorization header", () => {
    const model: APIModel = {
      ...BASE_MODEL,
      authSchemes: [{ name: "bearerAuth", type: "http", scheme: "bearer" }],
    };
    const result = extractAuth(model, "stripe");
    expect(result).toHaveLength(1);
    expect(result[0].envVar).toBe("STRIPE_BEARER_TOKEN");
    expect(result[0].headerName).toBe("Authorization");
    expect(result[0].headerFormat).toBe("Bearer {value}");
  });

  it("uses 'API' as service prefix when serviceName omitted", () => {
    const model: APIModel = {
      ...BASE_MODEL,
      authSchemes: [{ name: "bearerAuth", type: "http", scheme: "bearer" }],
    };
    const result = extractAuth(model);
    expect(result[0].envVar).toBe("API_BEARER_TOKEN");
  });

  it("skips oauth2 and openIdConnect schemes", () => {
    const model: APIModel = {
      ...BASE_MODEL,
      authSchemes: [{ name: "oauth", type: "oauth2" }],
    };
    expect(extractAuth(model, "myservice")).toHaveLength(0);
  });
});
