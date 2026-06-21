import { describe, it, expect } from "vitest";
import { fetchSpec } from "../../ts/ingest/fetch";

const FIXTURE = "./ts-tests/fixtures/petstore.yaml";

describe("fetchSpec", () => {
  it("loads and parses a local YAML file", async () => {
    const doc = await fetchSpec(FIXTURE);
    expect(doc).toHaveProperty("openapi");
    expect((doc as { info: { title: string } }).info.title).toBe("Swagger Petstore");
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
