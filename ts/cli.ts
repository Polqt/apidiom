import { Command } from "commander";
import fs from "fs/promises";
import path from "path";
import { fetchSpec } from "./ingest/fetch";
import { parseOpenAPI } from "./ingest/parse";
import { extractAuth } from "./auth";
import { generateMCPServer } from "./generate/mcp";
import { buildToolMetadata } from "./generate/tools";
import { generateToolSchema, type SchemaFormat } from "./generate/schema";
import { parseConfig, type TargetConfig } from "./config";
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
  if (!/^\d+$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 1 ? parsed : null;
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

const INIT_TEMPLATE = `# apidiom.yaml
# Run \`apidiom run\` to regenerate all targets.
# Run \`apidiom run <name>\` to regenerate a single target.

targets:
  # discord:
  #   source: discord          # registry name, URL, or file path
  #   output: mcp/discord.js   # output file (directories created automatically)
  #   mode: search             # flat | search | auto (default: auto)
  #   tags: []                 # filter by OpenAPI tag
  #   include: []              # filter by operationId
  #   group-by-tag: false      # prefix tool names with tag
  #   max-tools: 40            # threshold before auto-switching to search mode
`;

program
  .command("init")
  .description("Create a starter apidiom.yaml in the current directory")
  .action(async () => {
    const dest = path.join(process.cwd(), "apidiom.yaml");
    try {
      await fs.access(dest);
      process.stderr.write(`apidiom.yaml already exists at ${dest}\n`);
      process.exit(1);
    } catch {
      await fs.writeFile(dest, INIT_TEMPLATE, "utf-8");
      process.stdout.write(`Created apidiom.yaml\n`);
    }
  });

async function runMCPTarget(name: string, t: TargetConfig): Promise<string> {
  const source = t.source;
  const maxTools = t.maxTools ?? 40;
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
      `Warning [${name}]: uses OAuth2/OpenID Connect - API calls will be unauthenticated.\n`
    );
  }
  const toolOptions = {
    tags: t.tags && t.tags.length > 0 ? t.tags : undefined,
    include: t.include && t.include.length > 0 ? t.include : undefined,
  };
  const toolCount = buildToolMetadata(model.endpoints, toolOptions).length;
  let mode: "flat" | "search" = t.mode === "search" ? "search" : "flat";
  if (t.mode === "flat" && toolCount > maxTools) {
    throw new Error(
      `${toolCount} tools exceeds max-tools limit of ${maxTools} for flat mode. Use mode: search or raise max-tools.`
    );
  }
  if ((t.mode === undefined || t.mode === "auto") && toolCount > maxTools) {
    mode = "search";
  }
  const code = generateMCPServer(model, auth, {
    ...toolOptions,
    groupByTag: t.groupByTag,
    mode,
  });
  const outPath = path.resolve(t.output);
  await fs.mkdir(path.dirname(outPath), { recursive: true });
  await fs.writeFile(outPath, code, "utf-8");
  return `${toolCount} tools, ${mode} mode`;
}

program
  .command("run [target]")
  .description("Generate from apidiom.yaml (all targets, or a single named target)")
  .option("--config <file>", "Path to config file (default: ./apidiom.yaml)")
  .action(async (target: string | undefined, opts: { config?: string }) => {
    const configPath = path.resolve(opts.config ?? "apidiom.yaml");
    let raw: string;
    try {
      raw = await fs.readFile(configPath, "utf-8");
    } catch {
      process.stderr.write(`Error: config file not found: ${configPath}\n`);
      process.stderr.write(`  Run \`apidiom init\` to create one.\n`);
      process.exit(1);
    }
    let config;
    try {
      config = parseConfig(raw);
    } catch (err) {
      process.stderr.write(`Error parsing ${configPath}: ${err instanceof Error ? err.message : String(err)}\n`);
      process.exit(1);
    }
    if (target && !config.targets[target]) {
      const known = Object.keys(config.targets).join(", ");
      process.stderr.write(`Error: unknown target "${target}". Known targets: ${known}\n`);
      process.exit(1);
    }
    const targets = target
      ? { [target]: config.targets[target] }
      : config.targets;
    let ok = true;
    for (const [name, t] of Object.entries(targets)) {
      try {
        const summary = await runMCPTarget(name, t);
        process.stdout.write(`✓ ${name.padEnd(16)} →  ${t.output}  (${summary})\n`);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        process.stderr.write(`✗ ${name}: ${msg}\n`);
        ok = false;
      }
    }
    if (!ok) process.exit(1);
  });

program.parse(process.argv);
