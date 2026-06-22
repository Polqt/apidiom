import { describe, it, expect } from "vitest";
import path from "path";
import { execSync } from "child_process";

const CLI = path.resolve(__dirname, "../dist/cli.js");
const FIXTURE = path.resolve(__dirname, "fixtures/petstore.yaml");

// Build first — tests depend on dist/cli.js
try {
  execSync("npm run build", { stdio: "pipe", cwd: path.resolve(__dirname, "..") });
} catch (e) {
  throw new Error(`Build failed before CLI tests: ${e}`);
}

describe("CLI integration", () => {
  it("--help shows usage", () => {
    const out = execSync(`node "${CLI}" --help`).toString();
    expect(out).toContain("apidiom");
    expect(out).toContain("generate");
  });

  it("generate mcp --list shows known services", () => {
    const out = execSync(`node "${CLI}" generate mcp --list`).toString();
    expect(out).toContain("stripe");
    expect(out).toContain("github");
  });

  it("generate mcp <fixture> outputs valid JS", () => {
    const out = execSync(`node "${CLI}" generate mcp "${FIXTURE}"`).toString();
    expect(out).toContain("list_pets");
    expect(out).toContain("tools/list");
    expect(out).toContain("tools/call");
  });

  it("generate mcp <fixture> --output writes file", () => {
    const outFile = path.resolve(__dirname, "petstore-mcp.js");
    execSync(`node "${CLI}" generate mcp "${FIXTURE}" --output "${outFile}"`);
    const fs = require("fs");
    expect(fs.existsSync(outFile)).toBe(true);
    fs.unlinkSync(outFile);
  });

  it("generate mcp unknown-service exits 1", () => {
    let threw = false;
    try { execSync(`node "${CLI}" generate mcp totally-unknown-svc-xyz`); }
    catch { threw = true; }
    expect(threw).toBe(true);
  });
});
