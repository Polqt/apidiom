import { describe, it, expect, vi } from "vitest";
import { resolveRefs } from "../../ts/ingest/resolve";

// Minimal spec builder — one path with one operation.
function spec(op: Record<string, unknown>, components: Record<string, unknown> = {}) {
  return {
    openapi: "3.0.0",
    paths: { "/x": { get: op } },
    components,
  };
}

function getOp(doc: Record<string, unknown>): Record<string, unknown> {
  return (doc.paths as Record<string, Record<string, unknown>>)["/x"].get;
}

describe("resolveRefs", () => {
  it("returns the doc untouched when there are no paths", () => {
    const doc = { openapi: "3.0.0", components: {} };
    expect(resolveRefs(doc)).toBe(doc);
  });

  it("resolves a local parameter schema $ref to its concrete schema", () => {
    const doc = spec(
      { parameters: [{ name: "id", in: "path", schema: { $ref: "#/components/schemas/Id" } }] },
      { schemas: { Id: { type: "string", format: "uuid" } } }
    );
    const op = getOp(resolveRefs(doc));
    const params = op.parameters as { schema: Record<string, unknown> }[];
    expect(params[0].schema).toEqual({ type: "string", format: "uuid" });
  });

  it("deep-resolves the requestBody schema $ref into real properties", () => {
    const doc = spec(
      { requestBody: { content: { "application/json": { schema: { $ref: "#/components/schemas/Pet" } } } } },
      { schemas: { Pet: { type: "object", properties: { name: { type: "string" } }, required: ["name"] } } }
    );
    const op = getOp(resolveRefs(doc));
    const schema = (op.requestBody as Record<string, Record<string, Record<string, unknown>>>)
      .content["application/json"].schema;
    expect(schema).toEqual({ type: "object", properties: { name: { type: "string" } }, required: ["name"] });
  });

  it("resolves nested schema $refs (property referencing another schema)", () => {
    const doc = spec(
      { requestBody: { content: { "application/json": { schema: { $ref: "#/components/schemas/Order" } } } } },
      {
        schemas: {
          Order: { type: "object", properties: { pet: { $ref: "#/components/schemas/Pet" } } },
          Pet: { type: "object", properties: { name: { type: "string" } } },
        },
      }
    );
    const op = getOp(resolveRefs(doc));
    const schema = (op.requestBody as Record<string, Record<string, Record<string, Record<string, unknown>>>>)
      .content["application/json"].schema.properties as Record<string, unknown>;
    expect(schema.pet).toEqual({ type: "object", properties: { name: { type: "string" } } });
  });

  it("breaks self-referential schema cycles instead of infinite-looping", () => {
    const doc = spec(
      { requestBody: { content: { "application/json": { schema: { $ref: "#/components/schemas/Node" } } } } },
      { schemas: { Node: { type: "object", properties: { child: { $ref: "#/components/schemas/Node" } } } } }
    );
    // Must terminate. Cycle collapses to {} at the recursion boundary.
    const op = getOp(resolveRefs(doc));
    const schema = (op.requestBody as Record<string, Record<string, Record<string, Record<string, unknown>>>>)
      .content["application/json"].schema;
    expect(schema.properties).toHaveProperty("child");
  });

  it("merges sibling keys over a $ref target (siblings win)", () => {
    const doc = spec(
      { parameters: [{ name: "q", in: "query", schema: { $ref: "#/components/schemas/Str", description: "override" } }] },
      { schemas: { Str: { type: "string", description: "base" } } }
    );
    const op = getOp(resolveRefs(doc));
    const params = op.parameters as { schema: Record<string, unknown> }[];
    expect(params[0].schema).toEqual({ type: "string", description: "override" });
  });

  it("warns once and skips an external $ref", () => {
    const warn = vi.spyOn(process.stderr, "write").mockReturnValue(true);
    const doc = spec({
      requestBody: { content: { "application/json": { schema: { $ref: "external.yaml#/Pet" } } } },
    });
    const op = getOp(resolveRefs(doc));
    const schema = (op.requestBody as Record<string, Record<string, Record<string, Record<string, unknown>>>>)
      .content["application/json"].schema;
    expect(schema.$ref).toBe("external.yaml#/Pet"); // left as-is
    expect(warn).toHaveBeenCalledWith(expect.stringMatching(/external \$ref/));
    warn.mockRestore();
  });

  it("merges path-level and operation-level parameters (operation wins on conflict)", () => {
    const doc = {
      openapi: "3.0.0",
      paths: {
        "/x": {
          parameters: [{ name: "id", in: "path", required: false }],
          get: { parameters: [{ name: "id", in: "path", required: true }] },
        },
      },
      components: {},
    };
    const op = getOp(resolveRefs(doc));
    const params = op.parameters as { name: string; required: boolean }[];
    expect(params).toHaveLength(1);
    expect(params[0].required).toBe(true);
  });
});
