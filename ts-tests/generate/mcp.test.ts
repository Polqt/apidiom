import { describe, it, expect, vi } from "vitest";
import path from "path";
import yaml from "js-yaml";
import fs from "fs";
import { parseOpenAPI } from "../../ts/ingest/parse";
import { resolveRefs } from "../../ts/ingest/resolve";
import { extractAuth } from "../../ts/auth";
import { generateMCPServer } from "../../ts/generate/mcp";
import { normalizeToolName, enrichDescription } from "../../ts/generate/tools";
import type { APIModel } from "../../ts/model";

const FIXTURE_PATH = path.resolve(__dirname, "../fixtures/petstore.yaml");
const doc = yaml.load(fs.readFileSync(FIXTURE_PATH, "utf-8")) as Record<string, unknown>;
const model = parseOpenAPI(doc);
const auth = extractAuth(model, "petstore");

describe("generateMCPServer", () => {
  it("produces a non-empty JS string", () => {
    const output = generateMCPServer(model, auth);
    expect(typeof output).toBe("string");
    expect(output.length).toBeGreaterThan(100);
  });

  it("includes all 3 tool names from petstore (normalized)", () => {
    const output = generateMCPServer(model, auth);
    expect(output).toContain('"list_pets"');
    expect(output).toContain('"create_pet"');
    expect(output).toContain('"get_pet"');
  });

  it("includes MCP protocol handler methods", () => {
    const output = generateMCPServer(model, auth);
    expect(output).toContain("tools/list");
    expect(output).toContain("tools/call");
    expect(output).toContain("initialize");
  });

  it("includes env var check for PETSTORE_API_KEY", () => {
    const output = generateMCPServer(model, auth);
    expect(output).toContain("PETSTORE_API_KEY");
    expect(output).toContain("process.env");
  });

  it("includes server URL in HTTP calls", () => {
    const output = generateMCPServer(model, auth);
    expect(output).toContain("petstore.swagger.io");
  });

  it("filters by tag when tags option provided", () => {
    const output = generateMCPServer(model, auth, { tags: ["nonexistent"] });
    expect(output).not.toContain('"list_pets"');
  });

  it("filters by operationId when include option provided", () => {
    const output = generateMCPServer(model, auth, { include: ["listPets"] });
    expect(output).toContain('"list_pets"');
    expect(output).not.toContain('"create_pet"');
    expect(output).not.toContain('"get_pet"');
  });

  it("includes path parameter substitution for getPet", () => {
    const output = generateMCPServer(model, auth);
    expect(output).toContain("petId");
  });

  it("output is valid JavaScript (no syntax errors)", () => {
    const output = generateMCPServer(model, auth);
    expect(() => new Function(output)).not.toThrow();
  });

  it("inlines local schema refs used by tool parameters", () => {
    const resolved = resolveRefs({
      openapi: "3.0.3",
      info: { title: "Discord-like API", version: "1.0.0" },
      servers: [{ url: "https://api.example.com" }],
      paths: {
        "/channels/{channel_id}": {
          get: {
            operationId: "getChannel",
            parameters: [
              {
                name: "channel_id",
                in: "path",
                required: true,
                schema: { $ref: "#/components/schemas/SnowflakeType" },
              },
            ],
            responses: { "200": { description: "OK" } },
          },
        },
      },
      components: {
        schemas: {
          SnowflakeType: { type: "string", pattern: "^[0-9]+$" },
        },
      },
    });

    const output = generateMCPServer(parseOpenAPI(resolved), []);

    expect(output).not.toContain("#/components/schemas/SnowflakeType");
    expect(output).toContain('"pattern":"^[0-9]+$"');
  });

  it("prefixes tool name with tag when groupByTag is true", () => {
    // petstore fixture tags its endpoints with "pets"
    const output = generateMCPServer(model, auth, { groupByTag: true });
    expect(output).toContain('"pets__list_pets"');
    expect(output).toContain('"pets__create_pet"');
    expect(output).toContain('"pets__get_pet"');
  });
});

describe("normalizeToolName", () => {
  it("converts camelCase to snake_case", () => {
    expect(normalizeToolName("listPets")).toBe("list_pets");
  });

  it("converts PascalCase to snake_case", () => {
    expect(normalizeToolName("GetPet")).toBe("get_pet");
  });

  it("strips V1 version prefix", () => {
    expect(normalizeToolName("GetV1ChargesChargeId")).toBe("get_charges_charge_id");
  });

  it("strips V2 version prefix", () => {
    expect(normalizeToolName("PostV2Users")).toBe("post_users");
  });

  it("passes through already-snake_case names unchanged", () => {
    expect(normalizeToolName("list_pets")).toBe("list_pets");
  });

  it("handles names with digits", () => {
    expect(normalizeToolName("getV1Order123")).toBe("get_order123");
  });
});

describe("enrichDescription", () => {
  it("returns summary when no description and no required params", () => {
    expect(enrichDescription("List pets", undefined, [])).toBe("List pets.");
  });

  it("appends first sentence of description when different from summary", () => {
    expect(
      enrichDescription("List pets", "Returns all pets in the store. Supports pagination.", [])
    ).toBe("List pets. Returns all pets in the store.");
  });

  it("does not duplicate summary when description starts with same text", () => {
    expect(enrichDescription("List pets", "List pets. Max 100 returned.", [])).toBe("List pets.");
  });

  it("appends required path and query params", () => {
    const params: import("../../ts/model").OpenAPIParam[] = [
      { name: "petId", in: "path", required: true, schema: {} },
      { name: "limit", in: "query", required: false, schema: {} },
    ];
    expect(enrichDescription("Get pet", undefined, params)).toBe(
      "Get pet. Params: petId (required)."
    );
  });

  it("appends multiple required params comma-separated", () => {
    const params: import("../../ts/model").OpenAPIParam[] = [
      { name: "userId", in: "path", required: true, schema: {} },
      { name: "orderId", in: "path", required: true, schema: {} },
    ];
    expect(enrichDescription("Get order", undefined, params)).toBe(
      "Get order. Params: userId (required), orderId (required)."
    );
  });

  it("returns empty string when summary and description are both missing", () => {
    expect(enrichDescription(undefined, undefined, [])).toBe("");
  });

  it("ignores header and cookie params in param list", () => {
    const params: import("../../ts/model").OpenAPIParam[] = [
      { name: "X-Token", in: "header", required: true, schema: {} },
      { name: "session", in: "cookie", required: true, schema: {} },
    ];
    expect(enrichDescription("Do thing", undefined, params)).toBe("Do thing.");
  });
});

describe("generateMCPServer — deduplication", () => {
  it("renames colliding normalized tool names with _2 suffix", () => {
    const stderr = vi.spyOn(process.stderr, "write").mockImplementation(() => true);
    const collidingModel: import("../../ts/model").APIModel = {
      title: "Test API",
      version: "1.0",
      serverUrl: "https://api.example.com",
      authSchemes: [],
      endpoints: [
        {
          path: "/pets",
          method: "GET",
          operationId: "GetV1Pets",
          tags: [],
          parameters: [],
        },
        {
          path: "/pets/all",
          method: "GET",
          operationId: "GetV2Pets",
          tags: [],
          parameters: [],
        },
      ],
    };
    const output = generateMCPServer(collidingModel, []);
    expect(output).toContain('"get_pets"');
    expect(output).toContain('"get_pets_2"');
    expect(stderr).toHaveBeenCalledWith(expect.stringContaining('renamed to "get_pets_2"'));
    stderr.mockRestore();
  });

  it("generates no triple blank lines when no auth schemes present", () => {
    const model: import("../../ts/model").APIModel = {
      title: "Test API",
      version: "1.0.0",
      serverUrl: "https://api.test.com",
      endpoints: [],
      authSchemes: [],
    };
    const output = generateMCPServer(model, []);
    expect(output).not.toMatch(/\n\n\n/);
  });
});

describe("generateMCPServer — search mode", () => {
  it("search mode: tools/list returns exactly 2 meta-tools", () => {
    const model: APIModel = {
      title: "Test API",
      version: "1.0.0",
      serverUrl: "https://api.test.com",
      endpoints: [
        { path: "/a", method: "GET", operationId: "getA", tags: [], parameters: [] },
        { path: "/b", method: "GET", operationId: "getB", tags: [], parameters: [] },
      ],
      authSchemes: [],
    };
    const output = generateMCPServer(model, [], { mode: "search" });
    expect(output).toContain('"search_tools"');
    expect(output).toContain('"call_tool"');
    expect(output).not.toContain("_TOOLS.map(function(t)");
  });

  it("search mode: output contains scorer logic", () => {
    const model: APIModel = {
      title: "Test API",
      version: "1.0.0",
      serverUrl: "https://api.test.com",
      endpoints: [
        { path: "/a", method: "GET", operationId: "getA", tags: [], parameters: [] },
      ],
      authSchemes: [],
    };
    const output = generateMCPServer(model, [], { mode: "search" });
    expect(output).toContain("total_matched");
    expect(output).toContain("_scoreTools");
  });

  it("flat mode: tools/list still returns all tools (unchanged)", () => {
    const model: APIModel = {
      title: "Test API",
      version: "1.0.0",
      serverUrl: "https://api.test.com",
      endpoints: [
        { path: "/a", method: "GET", operationId: "getA", tags: [], parameters: [] },
      ],
      authSchemes: [],
    };
    const output = generateMCPServer(model, [], { mode: "flat" });
    expect(output).toContain("_TOOLS.map(function(t)");
  });

  it("search mode: generated JS contains _tags on tools and scorer structure", () => {
    const model: APIModel = {
      title: "Test API",
      version: "1.0.0",
      serverUrl: "https://api.test.com",
      endpoints: [
        { path: "/customers", method: "POST", operationId: "createCustomer", tags: ["customers"], parameters: [] },
        { path: "/customers/{id}", method: "GET", operationId: "getCustomer", tags: ["customers"], parameters: [] },
        { path: "/charges", method: "POST", operationId: "createCharge", tags: ["charges"], parameters: [] },
      ],
      authSchemes: [],
    };
    const output = generateMCPServer(model, [], { mode: "search" });

    // Meta-tools present
    expect(output).toContain("search_tools");
    expect(output).toContain("call_tool");
    expect(output).toContain("total_matched");
    expect(output).toContain("_scoreTools");

    // _tags baked into _TOOLS for scorer; search mode must have scorer referencing them
    expect(output).toContain("_tags:");
    expect(output).toContain('"customers"');
    expect(output).toContain('"charges"');
    expect(output).toContain("_TOOLS[i]._tags");

    // K=5 cap in search_tools handler
    expect(output).toContain("slice(0, 5)");

    // Permissive dispatch: call_tool unwraps name + arguments
    expect(output).toContain("args.name");
    expect(output).toContain("args.arguments");
  });
});
