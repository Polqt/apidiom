import { describe, it, expect } from "vitest";
import path from "path";
import { execSync, spawn, spawnSync } from "child_process";
import fs from "fs";
import fsp from "fs/promises";
import http from "http";
import os from "os";
import type { AddressInfo } from "net";

const CLI = path.resolve(__dirname, "../dist/cli.js");
const FIXTURE = path.resolve(__dirname, "fixtures/petstore.yaml");
const ROOT = path.resolve(__dirname, "..");

function runCli(args: string[]) {
  return spawnSync(process.execPath, [CLI, ...args], {
    cwd: ROOT,
    encoding: "utf-8",
  });
}

function expectCliOk(args: string[]): string {
  const result = runCli(args);
  expect(result.status).toBe(0);
  expect(result.stderr).toBe("");
  return result.stdout;
}

// Build first — tests depend on dist/cli.js
try {
  execSync("npm run build", { stdio: "pipe", cwd: ROOT });
} catch (e) {
  throw new Error(`Build failed before CLI tests: ${e}`);
}

describe("CLI integration", () => {
  it("--help shows usage", () => {
    const out = expectCliOk(["--help"]);
    expect(out).toContain("apidiom");
    expect(out).toContain("generate");
  });

  it("generate mcp --list shows known services", () => {
    const out = expectCliOk(["generate", "mcp", "--list"]);
    expect(out).toContain("stripe");
    expect(out).toContain("github");
  });

  it("generate mcp <fixture> outputs valid JS", () => {
    const out = expectCliOk(["generate", "mcp", FIXTURE]);
    expect(out).toContain("list_pets");
    expect(out).toContain("tools/list");
    expect(out).toContain("tools/call");
  });

  it("generate mcp accepts bare relative file paths", () => {
    const out = expectCliOk(["generate", "mcp", "ts-tests/fixtures/petstore.yaml"]);
    expect(out).toContain("list_pets");
  });

  it("generate mcp <fixture> --output writes file", () => {
    const outFile = path.resolve(__dirname, "petstore-mcp.js");
    const result = runCli(["generate", "mcp", FIXTURE, "--output", outFile]);
    expect(result.status).toBe(0);
    expect(result.stderr).toContain(`Written to ${outFile}`);
    expect(fs.existsSync(outFile)).toBe(true);
    fs.unlinkSync(outFile);
  });

  it("generate schema prints Anthropic JSON", () => {
    const out = expectCliOk(["generate", "schema", FIXTURE, "--format", "anthropic"]);
    const tools = JSON.parse(out);
    expect(tools[0].name).toBe("list_pets");
    expect(tools[0].input_schema.type).toBe("object");
  });

  it("generate schema --output writes OpenAI JSON", () => {
    const outFile = path.resolve(__dirname, "petstore-tools.json");
    const result = runCli(["generate", "schema", FIXTURE, "--format", "openai", "--output", outFile]);
    expect(result.status).toBe(0);
    expect(result.stderr).toContain(`Written to ${outFile}`);
    const tools = JSON.parse(fs.readFileSync(outFile, "utf8"));
    expect(tools[0].type).toBe("function");
    expect(tools[0].function.name).toBe("list_pets");
    fs.unlinkSync(outFile);
  });

  it("generate schema requires --format", () => {
    const result = runCli(["generate", "schema", FIXTURE]);
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("required option '--format <format>' not specified");
  });

  it("generate mcp unknown-service exits 1", () => {
    const result = runCli(["generate", "mcp", "totally-unknown-svc-xyz"]);
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('Unknown service "totally-unknown-svc-xyz"');
  });

  it("generated MCP server lists and calls tools against a local API", async () => {
    await new Promise<void>((resolve, reject) => {
      const server = http.createServer((req, res) => {
        res.setHeader("content-type", "application/json");
        if (req.method === "GET" && req.url?.startsWith("/books?")) {
          res.end(JSON.stringify({ route: "list", url: req.url }));
          return;
        }
        if (req.method === "GET" && req.url === "/books/b1") {
          res.end(JSON.stringify({ id: "b1", title: "Agent Tools" }));
          return;
        }
        if (req.method === "POST" && req.url === "/books") {
          let body = "";
          req.on("data", (chunk) => {
            body += chunk.toString();
          });
          req.on("end", () => {
            res.statusCode = 201;
            res.end(JSON.stringify({ created: JSON.parse(body) }));
          });
          return;
        }
        res.statusCode = 404;
        res.end(JSON.stringify({ error: "not found" }));
      });

      server.listen(0, "127.0.0.1", () => {
        const { port } = server.address() as AddressInfo;
        const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "apidiom-smoke-"));
        const specPath = path.join(tempDir, "book-api.yaml");
        const outputPath = path.join(tempDir, "book-api-mcp.js");
        fs.writeFileSync(specPath, bookApiSpec(port), "utf8");
        const generateResult = runCli(["generate", "mcp", specPath, "--output", outputPath]);
        expect(generateResult.status).toBe(0);

        const child = spawn(process.execPath, [outputPath], {
          stdio: ["pipe", "pipe", "pipe"],
        });
        let stdout = "";
        let stderr = "";
        const timer = setTimeout(() => {
          child.kill();
          reject(new Error("generated MCP smoke test timed out"));
        }, 5000);

        child.stdout.on("data", (chunk) => {
          stdout += chunk.toString();
          if (stdout.includes('"id":5')) {
            child.kill();
          }
        });
        child.stderr.on("data", (chunk) => {
          stderr += chunk.toString();
        });
        child.on("error", reject);
        child.on("close", () => {
          clearTimeout(timer);
          server.close();
          fs.rmSync(tempDir, { recursive: true, force: true });
          try {
            expect(stderr).toBe("");
            expect(stdout).toContain('"name":"list_books"');
            expect(stdout).toContain('"name":"create_book"');
            expect(stdout).toContain('"name":"get_book"');
            expect(stdout).toContain('\\"route\\": \\"list\\"');
            expect(stdout).toContain('\\"id\\": \\"b1\\"');
            expect(stdout).toContain('\\"created\\": {');
            resolve();
          } catch (error) {
            reject(error);
          }
        });

        child.stdin.end(
          [
            JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize" }),
            JSON.stringify({
              jsonrpc: "2.0",
              method: "notifications/initialized",
            }),
            JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list" }),
            JSON.stringify({
              jsonrpc: "2.0",
              id: 3,
              method: "tools/call",
              params: { name: "list_books", arguments: { limit: 1 } },
            }),
            JSON.stringify({
              jsonrpc: "2.0",
              id: 4,
              method: "tools/call",
              params: { name: "get_book", arguments: { bookId: "b1" } },
            }),
            JSON.stringify({
              jsonrpc: "2.0",
              id: 5,
              method: "tools/call",
              params: {
                name: "create_book",
                arguments: { body: { title: "New", pages: 99 } },
              },
            }),
            "",
          ].join("\n")
        );
      });
    });
  }, 10000);

  it("reports version from package.json", () => {
    const pkg = require("../package.json") as { version: string };
    const output = expectCliOk(["--version"]).trim();
    expect(output).toBe(pkg.version);
  });

  it("schema command validates --format before fetching spec", async () => {
    const cliPath = path.resolve(__dirname, "../ts/cli.ts");
    const src = await fsp.readFile(cliPath, "utf-8");
    const schemaSection = src.slice(src.indexOf('.command("schema'));
    const formatCheckIdx = schemaSection.indexOf('opts.format !== "anthropic"');
    const fetchIdx = schemaSection.indexOf("fetchSpec");
    expect(formatCheckIdx).toBeGreaterThan(-1);
    expect(fetchIdx).toBeGreaterThan(-1);
    expect(formatCheckIdx).toBeLessThan(fetchIdx);
  });

  it("generate mcp auto-switches to search mode when tool count exceeds --max-tools", () => {
    const result = spawnSync(
      process.execPath,
      [CLI, "generate", "mcp", FIXTURE, "--max-tools", "1"],
      { cwd: ROOT, encoding: "utf-8" }
    );

    expect(result.status).toBe(0);
    expect(result.stderr).toContain("switching to --mode search");
    expect(result.stdout).toContain("search_tools");
    expect(result.stdout).toContain("call_tool");
    expect(result.stdout).not.toContain("_TOOLS.map(function(t)");
  });

  it("generate mcp --mode auto behaves like default auto mode", () => {
    const result = spawnSync(
      process.execPath,
      [CLI, "generate", "mcp", FIXTURE, "--mode", "auto", "--max-tools", "1"],
      { cwd: ROOT, encoding: "utf-8" }
    );

    expect(result.status).toBe(0);
    expect(result.stderr).toContain("switching to --mode search");
    expect(result.stdout).toContain("search_tools");
    expect(result.stdout).toContain("call_tool");
  });

  it("generate mcp --mode flat still errors when explicit flat output exceeds --max-tools", () => {
    const result = spawnSync(
      process.execPath,
      [CLI, "generate", "mcp", FIXTURE, "--mode", "flat", "--max-tools", "1"],
      { cwd: ROOT, encoding: "utf-8" }
    );

    expect(result.status).toBe(1);
    expect(result.stderr).toContain("tokens in tools/list");
    expect(result.stderr).toContain("--mode search");
  });

  it("generate schema warns when tool count exceeds --max-tools but still prints JSON", () => {
    const result = spawnSync(
      process.execPath,
      [CLI, "generate", "schema", FIXTURE, "--format", "anthropic", "--max-tools", "1"],
      { cwd: ROOT, encoding: "utf-8" }
    );

    expect(result.status).toBe(0);
    expect(result.stderr).toContain("Warning: 3 tool schemas generated");
    const tools = JSON.parse(result.stdout);
    expect(tools).toHaveLength(3);
  });

  it("generate mcp --mode search generates 2 meta-tools not flat list", () => {
    const output = expectCliOk(["generate", "mcp", FIXTURE, "--mode", "search"]);
    expect(output).toContain("search_tools");
    expect(output).toContain("call_tool");
    expect(output).not.toContain("_TOOLS.map(function(t)");
  });
});

function bookApiSpec(port: number): string {
  return `openapi: 3.0.3
info:
  title: Book API
  version: 1.0.0
servers:
  - url: http://127.0.0.1:${port}
paths:
  /books:
    get:
      operationId: listBooks
      summary: List books
      parameters:
        - name: limit
          in: query
          required: false
          schema:
            type: integer
      responses:
        "200":
          description: OK
    post:
      operationId: createBook
      summary: Create book
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
      responses:
        "201":
          description: Created
  /books/{bookId}:
    get:
      operationId: getBook
      summary: Get book
      parameters:
        - name: bookId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: OK
`;
}
