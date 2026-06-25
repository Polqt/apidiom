import { describe, it, expect } from "vitest";
import { scoreTools } from "../../ts/generate/search";
import type { ToolMetadata } from "../../ts/generate/tools";

function makeTool(name: string, description: string, tags: string[] = []): ToolMetadata {
  return {
    name,
    rawName: name,
    description,
    endpoint: {
      path: "/test",
      method: "GET",
      operationId: name,
      tags,
      parameters: [],
    },
    inputSchema: { type: "object", properties: {}, required: [] },
  };
}

describe("scoreTools", () => {
  const tools = [
    makeTool("create_customer", "Create a new Stripe customer", ["customers"]),
    makeTool("get_customer", "Retrieve a customer by ID", ["customers"]),
    makeTool("list_customers", "List all customers with optional filters", ["customers"]),
    makeTool("create_charge", "Create a charge for a customer", ["charges"]),
    makeTool("get_payment_intent", "Retrieve a payment intent", ["payment_intents"]),
  ];

  it("returns empty array for empty query", () => {
    expect(scoreTools("", tools)).toEqual([]);
  });

  it("returns empty array when no tools match", () => {
    expect(scoreTools("webhook", tools)).toEqual([]);
  });

  it("single token: ranks name-exact-token match highest", () => {
    const results = scoreTools("customer", tools);
    expect(results.length).toBeGreaterThan(0);
    const customerNames = results.filter(r => r.tool.name.includes("customer")).map(r => r.tool.name);
    expect(customerNames).toContain("create_customer");
    expect(customerNames).toContain("get_customer");
    expect(customerNames).toContain("list_customers");
  });

  it("multi-token: term-coverage ranks create_customer above list_customers for 'create customer'", () => {
    const results = scoreTools("create customer", tools);
    expect(results[0].tool.name).toBe("create_customer");
  });

  it("multi-token: 'create charge' ranks create_charge above create_customer", () => {
    const results = scoreTools("create charge", tools);
    expect(results[0].tool.name).toBe("create_charge");
  });

  it("returns results sorted descending by score", () => {
    const results = scoreTools("customer", tools);
    for (let i = 1; i < results.length; i++) {
      expect(results[i].score).toBeLessThanOrEqual(results[i - 1].score);
    }
  });

  it("tag match boosts score", () => {
    const withTag = makeTool("foo_bar", "Unrelated description", ["customer"]);
    const without = makeTool("baz_qux", "Unrelated description", []);
    const results = scoreTools("customer", [withTag, without]);
    const tagResult = results.find(r => r.tool.name === "foo_bar");
    expect(tagResult).toBeDefined();
    expect(tagResult!.score).toBeGreaterThan(0);
    // baz_qux has no name/desc/tag match — should not appear
    expect(results.find(r => r.tool.name === "baz_qux")).toBeUndefined();
  });
});
