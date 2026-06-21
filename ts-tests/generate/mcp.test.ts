import { describe, it, expect } from "vitest";
import path from "path";
import yaml from "js-yaml";
import fs from "fs";
import { parseOpenAPI } from "../../ts/ingest/parse";
import { extractAuth } from "../../ts/auth";
import { generateMCPServer } from "../../ts/generate/mcp";

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

  it("includes all 3 tool names from petstore", () => {
    const output = generateMCPServer(model, auth);
    expect(output).toContain("listPets");
    expect(output).toContain("createPet");
    expect(output).toContain("getPet");
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
    expect(output).not.toContain("listPets");
  });

  it("filters by operationId when include option provided", () => {
    const output = generateMCPServer(model, auth, { include: ["listPets"] });
    expect(output).toContain("listPets");
    expect(output).not.toContain("createPet");
    expect(output).not.toContain("getPet");
  });

  it("includes path parameter substitution for getPet", () => {
    const output = generateMCPServer(model, auth);
    expect(output).toContain("petId");
  });

  it("output is valid JavaScript (no syntax errors)", () => {
    const output = generateMCPServer(model, auth);
    expect(() => new Function(output)).not.toThrow();
  });
});
