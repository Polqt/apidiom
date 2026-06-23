import { Command } from "commander";
import fs from "fs/promises";
import { fetchSpec } from "./ingest/fetch";
import { parseOpenAPI } from "./ingest/parse";
import { extractAuth } from "./auth";
import { generateMCPServer } from "./generate/mcp";
import { generateToolSchema, type SchemaFormat } from "./generate/schema";
import { REGISTRY } from "./registry";

const program = new Command();

program
  .name("apidiom")
  .description("Turn any API into an MCP server in one command.")
  .version("0.2.2");

const generate = program.command("generate").description("Generate code from an API spec");

function collect(value: string, previous: string[]): string[] {
  return previous.concat([value]);
}

generate
  .command("mcp [source]")
  .description("Generate a standalone MCP server JS file")
  .option("-o, --output <file>", "Write output to file (default: stdout)")
  .option("--tag <tag>", "Include only endpoints with this tag (repeatable)", collect, [])
  .option("--include <operationId>", "Include only this operationId (repeatable)", collect, [])
  .option("--group-by-tag", "Prefix tool names with their OpenAPI tag (e.g. pets__list_pets)")
  .option("--list", "List available built-in services")
  .action(async (source: string | undefined, opts: { output?: string; tag: string[]; include: string[]; groupByTag?: boolean; list?: boolean }) => {
    if (opts.list) {
      for (const [name, entry] of Object.entries(REGISTRY)) {
        process.stdout.write(`${name.padEnd(16)} ${entry.description}\n`);
      }
      return;
    }

    if (!source) {
      process.stderr.write("Error: source argument required. Usage: apidiom generate mcp <service|url|file>\n");
      process.exit(1);
    }

    try {
      const doc = await fetchSpec(source);
      const model = parseOpenAPI(doc);
      const serviceName = Object.keys(REGISTRY).find(
        (k) => REGISTRY[k].url === source || k === source.toLowerCase()
      );
      const auth = extractAuth(model, serviceName);
      const hasUnsupportedAuth = model.authSchemes.some(
        (s) => s.type === "oauth2" || s.type === "openIdConnect"
      );
      if (hasUnsupportedAuth && auth.length === 0) {
        process.stderr.write(
          `Warning: "${source}" uses OAuth2/OpenID Connect auth — not supported in generated code. API calls will be unauthenticated and likely return 401.\n`
        );
      }
      const code = generateMCPServer(model, auth, {
        tags: opts.tag.length > 0 ? opts.tag : undefined,
        include: opts.include.length > 0 ? opts.include : undefined,
        groupByTag: opts.groupByTag,
      });

      if (model.endpoints.length > 200) {
        process.stderr.write(
          `Warning: ${model.endpoints.length} endpoints found — consider filtering with --tag or --include to reduce tool count for Claude Desktop.\n`
        );
      }

      if (opts.output) {
        await fs.writeFile(opts.output, code, "utf-8");
        process.stderr.write(`Written to ${opts.output}\n`);
      } else {
        process.stdout.write(code);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      process.stderr.write(`Error: ${msg}\n`);
      process.exit(1);
    }
  });

generate
  .command("schema <source>")
  .description("Generate Anthropic or OpenAI JSON tool schemas")
  .requiredOption("--format <format>", "Tool schema format: anthropic or openai")
  .option("-o, --output <file>", "Write output to file (default: stdout)")
  .option("--tag <tag>", "Include only endpoints with this tag (repeatable)", collect, [])
  .option("--include <operationId>", "Include only this operationId (repeatable)", collect, [])
  .action(async (
    source: string,
    opts: { format: string; output?: string; tag: string[]; include: string[] }
  ) => {
    if (opts.format !== "anthropic" && opts.format !== "openai") {
      process.stderr.write("Error: --format must be anthropic or openai\n");
      process.exit(1);
    }

    try {
      const doc = await fetchSpec(source);
      const model = parseOpenAPI(doc);
      const json = generateToolSchema(model, {
        format: opts.format as SchemaFormat,
        tags: opts.tag.length > 0 ? opts.tag : undefined,
        include: opts.include.length > 0 ? opts.include : undefined,
      });

      if (opts.output) {
        await fs.writeFile(opts.output, json, "utf-8");
        process.stderr.write(`Written to ${opts.output}\n`);
      } else {
        process.stdout.write(json);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      process.stderr.write(`Error: ${msg}\n`);
      process.exit(1);
    }
  });

program.parse(process.argv);
