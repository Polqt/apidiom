import { describe, it, expect } from "vitest";
import path from "path";
import yaml from "js-yaml";
import fs from "fs";
import { parseOpenAPI } from "../../ts/ingest/parse";

const FIXTURE_PATH = path.resolve(__dirname, "../fixtures/petstore.yaml");
const doc = yaml.load(fs.readFileSync(FIXTURE_PATH, "utf-8")) as Record<string, unknown>;

describe("parseOpenAPI", () => {
  it("returns correct title and version", () => {
    const model = parseOpenAPI(doc);
    expect(model.title).toBe("Swagger Petstore");
    expect(model.version).toBe("1.0.0");
  });

  it("extracts server URL", () => {
    const model = parseOpenAPI(doc);
    expect(model.serverUrl).toBe("https://petstore.swagger.io/v2");
  });

  it("extracts all 3 endpoints", () => {
    const model = parseOpenAPI(doc);
    expect(model.endpoints).toHaveLength(3);
  });

  it("extracts GET /pets endpoint correctly", () => {
    const model = parseOpenAPI(doc);
    const ep = model.endpoints.find(
      (e) => e.method === "GET" && e.path === "/pets"
    );
    expect(ep).toBeDefined();
    expect(ep!.operationId).toBe("listPets");
    expect(ep!.parameters).toHaveLength(1);
    expect(ep!.parameters[0].name).toBe("limit");
    expect(ep!.parameters[0].in).toBe("query");
  });

  it("extracts path parameter from GET /pets/{petId}", () => {
    const model = parseOpenAPI(doc);
    const ep = model.endpoints.find(
      (e) => e.method === "GET" && e.path === "/pets/{petId}"
    );
    expect(ep).toBeDefined();
    expect(ep!.parameters[0].name).toBe("petId");
    expect(ep!.parameters[0].in).toBe("path");
    expect(ep!.parameters[0].required).toBe(true);
  });

  it("extracts path-item parameters shared by operations", () => {
    const model = parseOpenAPI({
      openapi: "3.0.3",
      info: { title: "Books", version: "1.0.0" },
      paths: {
        "/books/{bookId}": {
          parameters: [
            {
              name: "bookId",
              in: "path",
              required: true,
              schema: { type: "string" },
            },
          ],
          get: {
            operationId: "getBook",
            responses: { "200": { description: "OK" } },
          },
        },
      },
    });

    expect(model.endpoints[0].parameters).toEqual([
      {
        name: "bookId",
        in: "path",
        required: true,
        description: undefined,
        schema: { type: "string" },
      },
    ]);
  });

  it("extracts POST /pets request body", () => {
    const model = parseOpenAPI(doc);
    const ep = model.endpoints.find(
      (e) => e.method === "POST" && e.path === "/pets"
    );
    expect(ep).toBeDefined();
    expect(ep!.requestBody).toBeDefined();
    expect(ep!.requestBody!.required).toBe(true);
  });

  it("extracts auth schemes", () => {
    const model = parseOpenAPI(doc);
    expect(model.authSchemes).toHaveLength(1);
    expect(model.authSchemes[0].name).toBe("api_key");
    expect(model.authSchemes[0].type).toBe("apiKey");
    expect(model.authSchemes[0].apiKeyIn).toBe("header");
    expect(model.authSchemes[0].apiKeyHeaderName).toBe("api_key");
  });

  it("throws on non-OpenAPI-3 document", () => {
    expect(() => parseOpenAPI({ swagger: "2.0" })).toThrow(/OpenAPI 3/);
  });

  it("uses safe defaults for non-string OpenAPI text fields", () => {
    const model = parseOpenAPI({
      openapi: "3.0.3",
      info: { title: { unsafe: true }, version: [1, 0] },
      servers: [{ url: { host: "api.example.com" } }],
      paths: {
        "/pets": {
          post: {
            operationId: { unsafe: true },
            summary: { unsafe: true },
            description: ["unsafe"],
            parameters: [
              {
                name: { unsafe: true },
                in: "query",
                description: { unsafe: true },
              },
            ],
            requestBody: {
              description: { unsafe: true },
              content: { "application/json": { schema: { type: "object" } } },
            },
          },
        },
      },
      components: {
        securitySchemes: {
          apiKey: {
            type: "apiKey",
            in: "header",
            scheme: { unsafe: true },
            name: { unsafe: true },
          },
        },
      },
    });

    expect(model).toMatchObject({
      title: "API",
      version: "0.0.0",
      serverUrl: "",
      endpoints: [
        {
          operationId: "post__pets",
          summary: undefined,
          description: undefined,
          parameters: [{ name: "", description: undefined }],
          requestBody: { description: undefined },
        },
      ],
      authSchemes: [{ scheme: undefined, apiKeyHeaderName: undefined }],
    });
    expect(JSON.stringify(model)).not.toContain("[object Object]");
  });
});
