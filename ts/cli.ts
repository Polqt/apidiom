import { Command } from "commander";
import fs from "fs/promises";
import { fetchSpec } from "./ingest/fetch";
import { parseOpenAPI } from "./ingest/parse";
import { extractAuth } from "./auth";
import { generateMCPServer } from "./generate/mcp";
import { buildToolMetadata } from "./generate/tools";
import { generateToolSchema, type SchemaFormat } from "./generate/schema";
import { REGISTRY } from "./registry";

const program = new Command();

program
  .name("apidiom")
  .description("Turn any API into an MCP server in one command.")
  .version((require("../package.json") as { version: string }).version);

const generate = program.command("generate").description("Generate code from an API spec");

function collect(value: string, previous: string[]): string[] {
  return previous.concat([value]);
}

function parseMaxTools(value: string): number | null {
  const parsed = parseInt(value, 10);
  return isNaN(parsed) || parsed < 1 ? null : parsed;
}

generate
  .command("mcp [source]")
  .description("Generate a standalone MCP server JS file")
  .option("-o, --output <file>", "Write output to file (default: stdout)")
  .option("--tag <tag>", "Include only endpoints with this tag (repeatable)", collect, [])
  .option("--include <operationId>", "Include only this operationId (repeatable)", collect, [])
  .option("--group-by-tag", "Prefix tool names with their OpenAPI tag (e.g. pets__list_pets)")
  .option("--list", "List available built-in services")
  .option("--mode <mode>", "Tool exposure mode: auto (default), flat, or search")
  .option("--max-tools <n>", "Max flat tools before auto-search or explicit-flat guard (default: 40)", "40")
  .action(async (source: string | undefined, opts: { output?: string; tag: string[]; include: string[]; groupByTag?: boolean; list?: boolean; mode?: string; maxTools: string }) => {
    if (opts.list) {
      for (const [name, entry] of Object.entries(REGISTRY)) {
        process.stdout.write(`${name.padEnd(16)} ${entry.description}\n`);
      }
      return;
    }

    if (opts.mode !== undefined && opts.mode !== "auto" && opts.mode !== "flat" && opts.mode !== "search") {
      process.stderr.write("Error: --mode must be auto, flat, or search\n");
      process.exit(1);
    }
    const maxTools = parseMaxTools(opts.maxTools);
    if (maxTools === null) {
      process.stderr.write("Error: --max-tools must be a positive integer\n");
      process.exit(1);
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
          `Warning: "${source}" uses OAuth2/OpenID Connect auth - not supported in generated code. API calls will be unauthenticated and likely return 401.\n`
        );
      }
      const toolOptions = {
        tags: opts.tag.length > 0 ? opts.tag : undefined,
        include: opts.include.length > 0 ? opts.include : undefined,
      };
      const toolCount = buildToolMetadata(model.endpoints, toolOptions).length;
      let mode: "flat" | "search" = opts.mode === "search" ? "search" : "flat";

      if ((opts.mode === undefined || opts.mode === "auto") && toolCount > maxTools) {
        mode = "search";
        process.stderr.write(
          `Warning: ${toolCount} tools generated (~${Math.round(toolCount * 380)} tokens in tools/list) - switching to --mode search.\n` +
          `  Use --mode flat --max-tools ${toolCount} to force a flat tools/list.\n`
        );
      }

      if (opts.mode === "flat") {
        if (toolCount > maxTools) {
          process.stderr.write(
            `Error: ${toolCount} tools generated (~${Math.round(toolCount * 380)} tokens in tools/list) - exceeds recommended limit of ${maxTools}.\n` +
            `  Use --mode search for progressive discovery, or --tag/--include to filter.\n` +
            `  To force flat mode, raise the guard: --mode flat --max-tools ${toolCount}\n` +
            `  Example: apidiom generate mcp ${source} --mode search --output server.js\n`
          );
          process.exit(1);
        }
      }
      const code = generateMCPServer(model, auth, {
        ...toolOptions,
        groupByTag: opts.groupByTag,
        mode,
      });

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
  .option("--max-tools <n>", "Warn when schema tool count exceeds this limit (default: 40)", "40")
  .action(async (
    source: string,
    opts: { format: string; output?: string; tag: string[]; include: string[]; maxTools: string }
  ) => {
    if (opts.format !== "anthropic" && opts.format !== "openai") {
      process.stderr.write("Error: --format must be anthropic or openai\n");
      process.exit(1);
    }
    const maxTools = parseMaxTools(opts.maxTools);
    if (maxTools === null) {
      process.stderr.write("Error: --max-tools must be a positive integer\n");
      process.exit(1);
    }

    try {
      const doc = await fetchSpec(source);
      const model = parseOpenAPI(doc);
      const toolOptions = {
        tags: opts.tag.length > 0 ? opts.tag : undefined,
        include: opts.include.length > 0 ? opts.include : undefined,
      };
      const toolCount = buildToolMetadata(model.endpoints, toolOptions).length;
      if (toolCount > maxTools) {
        process.stderr.write(
          `Warning: ${toolCount} tool schemas generated (~${Math.round(toolCount * 380)} tokens) exceeds recommended limit of ${maxTools}.\n` +
          `  Use --tag/--include to reduce raw SDK context size.\n`
        );
      }
      const json = generateToolSchema(model, {
        format: opts.format as SchemaFormat,
        ...toolOptions,
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
