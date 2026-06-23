import { describe, it, expect } from "vitest";
import path from "path";
import { execSync, spawn } from "child_process";
import fs from "fs";
import http from "http";
import os from "os";
import type { AddressInfo } from "net";

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

  it("generate mcp accepts bare relative file paths", () => {
    const out = execSync(
      `node "${CLI}" generate mcp ts-tests/fixtures/petstore.yaml`
    ).toString();
    expect(out).toContain("list_pets");
  });

  it("generate mcp <fixture> --output writes file", () => {
    const outFile = path.resolve(__dirname, "petstore-mcp.js");
    execSync(`node "${CLI}" generate mcp "${FIXTURE}" --output "${outFile}"`);
    const fs = require("fs");
    expect(fs.existsSync(outFile)).toBe(true);
    fs.unlinkSync(outFile);
  });

  it("generate schema prints Anthropic JSON", () => {
    const out = execSync(
      `node "${CLI}" generate schema "${FIXTURE}" --format anthropic`
    ).toString();
    const tools = JSON.parse(out);
    expect(tools[0].name).toBe("list_pets");
    expect(tools[0].input_schema.type).toBe("object");
  });

  it("generate schema --output writes OpenAI JSON", () => {
    const outFile = path.resolve(__dirname, "petstore-tools.json");
    execSync(
      `node "${CLI}" generate schema "${FIXTURE}" --format openai --output "${outFile}"`
    );
    const tools = JSON.parse(fs.readFileSync(outFile, "utf8"));
    expect(tools[0].type).toBe("function");
    expect(tools[0].function.name).toBe("list_pets");
    fs.unlinkSync(outFile);
  });

  it("generate schema requires --format", () => {
    let threw = false;
    try { execSync(`node "${CLI}" generate schema "${FIXTURE}"`); }
    catch { threw = true; }
    expect(threw).toBe(true);
  });

  it("generate mcp unknown-service exits 1", () => {
    let threw = false;
    try { execSync(`node "${CLI}" generate mcp totally-unknown-svc-xyz`); }
    catch { threw = true; }
    expect(threw).toBe(true);
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
        execSync(`node "${CLI}" generate mcp "${specPath}" --output "${outputPath}"`);

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
