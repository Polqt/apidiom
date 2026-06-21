import { describe, it, expect } from "vitest";
import { resolveSource, REGISTRY } from "../ts/registry";

describe("resolveSource", () => {
  it("returns URL unchanged when source is a URL", () => {
    const url = "https://example.com/openapi.yaml";
    expect(resolveSource(url)).toBe(url);
  });

  it("returns URL unchanged when source is a file path", () => {
    expect(resolveSource("./my-api.yaml")).toBe("./my-api.yaml");
    expect(resolveSource("/abs/path/spec.json")).toBe("/abs/path/spec.json");
  });

  it("resolves 'stripe' to its spec URL", () => {
    const result = resolveSource("stripe");
    expect(result).toBe(REGISTRY["stripe"].url);
    expect(result).toContain("stripe");
  });

  it("throws on unknown service name", () => {
    expect(() => resolveSource("nonexistent-service-xyz")).toThrow(
      /Unknown service "nonexistent-service-xyz"/
    );
  });

  it("registry has at least 5 entries", () => {
    expect(Object.keys(REGISTRY).length).toBeGreaterThanOrEqual(5);
  });
});
