import { describe, it, expect } from "vitest";
import { fetchSpec, parseSpec } from "../../ts/ingest/fetch";

const FIXTURE = "./ts-tests/fixtures/petstore.yaml";
const BARE_RELATIVE_FIXTURE = "ts-tests/fixtures/petstore.yaml";

describe("fetchSpec", () => {
  it("loads and parses a local YAML file", async () => {
    const doc = await fetchSpec(FIXTURE);
    expect(doc).toHaveProperty("openapi");
    expect((doc as { info: { title: string } }).info.title).toBe("Swagger Petstore");
  });

  it("loads bare relative local YAML paths", async () => {
    const doc = await fetchSpec(BARE_RELATIVE_FIXTURE);
    expect(doc).toHaveProperty("openapi");
  });

  it("throws a clear error for a missing file", async () => {
    await expect(fetchSpec("/nonexistent/path/spec.yaml")).rejects.toThrow(
      /Could not load spec/
    );
  });

  it("throws a clear error for a bad URL", async () => {
    await expect(
      fetchSpec("https://localhost:1/nonexistent.yaml")
    ).rejects.toThrow(/Could not load spec/);
  }, 5000);
});

describe("parseSpec", () => {
  it("parses JSON content from extensionless URL by sniffing content", () => {
    expect(parseSpec('{"openapi":"3.0.0"}', "https://api.example.com/spec")).toEqual({ openapi: "3.0.0" });
  });

  it("throws on bare JSON array (not a valid OpenAPI doc)", () => {
    expect(() => parseSpec('[{"name":"foo"}]', "https://api.example.com/spec")).toThrow("JSON document is not an object");
  });

  it("parses YAML content from .yaml file", () => {
    expect(parseSpec("openapi: '3.0.0'", "spec.yaml")).toEqual({ openapi: "3.0.0" });
  });

  it("parses JSON content from .json file", () => {
    expect(parseSpec('{"openapi":"3.0.0"}', "spec.json")).toEqual({ openapi: "3.0.0" });
  });
});
