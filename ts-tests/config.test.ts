import { describe, it, expect } from "vitest";
import { parseConfig, type ApidiomConfig } from "../ts/config";

describe("parseConfig", () => {
  it("parses minimal target", () => {
    const yaml = `
targets:
  discord:
    source: discord
    output: mcp/discord.js
`;
    const config = parseConfig(yaml);
    expect(config.targets.discord).toEqual({
      source: "discord",
      output: "mcp/discord.js",
      mode: undefined,
      tags: undefined,
      include: undefined,
      groupByTag: undefined,
      maxTools: undefined,
    });
  });

  it("parses full target with all options", () => {
    const yaml = `
targets:
  stripe:
    source: stripe
    output: mcp/stripe.js
    mode: search
    tags: [payments, billing]
    max-tools: 50
    group-by-tag: true
`;
    const config = parseConfig(yaml);
    expect(config.targets.stripe).toEqual({
      source: "stripe",
      output: "mcp/stripe.js",
      mode: "search",
      tags: ["payments", "billing"],
      include: undefined,
      groupByTag: true,
      maxTools: 50,
    });
  });

  it("parses multiple targets", () => {
    const yaml = `
targets:
  discord:
    source: discord
    output: mcp/discord.js
  stripe:
    source: stripe
    output: mcp/stripe.js
`;
    const config = parseConfig(yaml);
    expect(Object.keys(config.targets)).toEqual(["discord", "stripe"]);
  });

  it("throws on missing targets key", () => {
    expect(() => parseConfig(`source: discord`)).toThrow(/targets/);
  });

  it("throws on target missing source", () => {
    const yaml = `
targets:
  bad:
    output: mcp/bad.js
`;
    expect(() => parseConfig(yaml)).toThrow(/source/);
  });

  it("throws on target missing output", () => {
    const yaml = `
targets:
  bad:
    source: discord
`;
    expect(() => parseConfig(yaml)).toThrow(/output/);
  });

  it("throws on invalid mode", () => {
    const yaml = `
targets:
  bad:
    source: discord
    output: out.js
    mode: invalid
`;
    expect(() => parseConfig(yaml)).toThrow(/mode/);
  });

  it("throws on empty targets", () => {
    expect(() => parseConfig(`targets: {}`)).toThrow(/targets/);
  });

  it("handles include as array", () => {
    const yaml = `
targets:
  discord:
    source: discord
    output: mcp/discord.js
    include: [listPets, createPet]
`;
    const config = parseConfig(yaml);
    expect(config.targets.discord.include).toEqual(["listPets", "createPet"]);
  });
});
