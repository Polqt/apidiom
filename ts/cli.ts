import { Command } from "commander";
import fs from "fs/promises";
import path from "path";
import { fetchSpec } from "./ingest/fetch";
import { parseOpenAPI } from "./ingest/parse";
import { buildToolMetadata } from "./generate/tools";
import { generateToolSchema, type SchemaFormat } from "./generate/schema";
import { parseConfig, type TargetConfig } from "./config";
import { generateMCP, runMCPTarget, type RequestedMCPMode } from "./pipeline";
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

type MCPCommandOptions = {
  output?: string;
  tag: string[];
  include: string[];
  groupByTag?: boolean;
  list?: boolean;
  mode?: string;
  maxTools: string;
};

function parseRequestedMode(mode: string | undefined): RequestedMCPMode {
  if (mode === undefined || mode === "auto" || mode === "flat" || mode === "search") {
    return mode;
  }
  process.stderr.write("Error: --mode must be auto, flat, or search\n");
  process.exit(1);
}

function requireMaxTools(value: string): number {
  const maxTools = parseMaxTools(value);
  if (maxTools !== null) return maxTools;
  process.stderr.write("Error: --max-tools must be a positive integer\n");
  process.exit(1);
}

function requireSource(source: string | undefined): string {
  if (source) return source;
  process.stderr.write(
    "Error: source argument required. Usage: apidiom generate mcp <service|url|file>\n"
  );
  process.exit(1);
}

function listServices(): void {
  for (const [name, entry] of Object.entries(REGISTRY)) {
    process.stdout.write(`${name.padEnd(16)} ${entry.description}\n`);
  }
}

async function writeGeneratedOutput(output: string | undefined, contents: string): Promise<void> {
  if (!output) {
    process.stdout.write(contents);
    return;
  }
  await fs.writeFile(output, contents, "utf-8");
  process.stderr.write(`Written to ${output}\n`);
}

async function generateMCPCommand(source: string, opts: MCPCommandOptions): Promise<void> {
  const requestedMode = parseRequestedMode(opts.mode);
  const maxTools = requireMaxTools(opts.maxTools);
  const result = await generateMCP(source, {
    tags: opts.tag.length > 0 ? opts.tag : undefined,
    include: opts.include.length > 0 ? opts.include : undefined,
    groupByTag: opts.groupByTag,
    mode: requestedMode,
    maxTools,
  });
  for (const warning of result.warnings) process.stderr.write(warning);
  await writeGeneratedOutput(opts.output, result.code);
}

async function handleMCPCommand(
  source: string | undefined,
  opts: MCPCommandOptions
): Promise<void> {
  if (opts.list) {
    listServices();
    return;
  }
  try {
    await generateMCPCommand(requireSource(source), opts);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`Error: ${message}\n`);
    process.exit(1);
  }
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
  .action(handleMCPCommand);

generate
  .command("schema <source>")
  .description("Generate Anthropic or OpenAI JSON tool schemas")
  .requiredOption("--format <format>", "Tool schema format: anthropic or openai")
  .option("-o, --output <file>", "Write output to file (default: stdout)")
  .option("--tag <tag>", "Include only endpoints with this tag (repeatable)", collect, [])
  .option("--include <operationId>", "Include only this operationId (repeatable)", collect, [])
  .option("--group-by-tag", "Prefix tool names with their OpenAPI tag (e.g. pets__list_pets)")
  .option("--max-tools <n>", "Warn when schema tool count exceeds this limit (default: 40)", "40")
  .action(async (
    source: string,
    opts: { format: string; output?: string; tag: string[]; include: string[]; groupByTag?: boolean; maxTools: string }
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
        groupByTag: opts.groupByTag,
      };
      const toolCount = buildToolMetadata(model.endpoints, toolOptions).length;
      if (toolCount > maxTools) {
        process.stderr.write(
          `Warning: ${toolCount} tool schemas generated (~${Math.round(toolCount * 380)} tokens) exceeds recommended limit of ${maxTools}.\n` +
          `  Use --tag/--include to reduce raw SDK context size.\n`
        );
      }
      const json = generateToolSchema(model, { format: opts.format as SchemaFormat, ...toolOptions });

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

type RunCommandOptions = { config?: string; dryRun?: boolean };

async function loadConfig(configPath: string): Promise<ReturnType<typeof parseConfig>> {
  let raw: string;
  try {
    raw = await fs.readFile(configPath, "utf-8");
  } catch {
    process.stderr.write(`Error: config file not found: ${configPath}\n`);
    process.stderr.write("  Run `apidiom init` to create one.\n");
    process.exit(1);
  }

  try {
    return parseConfig(raw);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`Error parsing ${configPath}: ${message}\n`);
    process.exit(1);
  }
}

function selectTargets(
  config: ReturnType<typeof parseConfig>,
  target: string | undefined
): Record<string, TargetConfig> {
  if (target === undefined) return config.targets;
  const selected = config.targets[target];
  if (selected) return { [target]: selected };

  const known = Object.keys(config.targets).join(", ");
  process.stderr.write(`Error: unknown target "${target}". Known targets: ${known}\n`);
  process.exit(1);
}

async function executeTargets(
  targets: Record<string, TargetConfig>,
  dryRun: boolean
): Promise<void> {
  let succeeded = true;
  for (const [name, target] of Object.entries(targets)) {
    try {
      const summary = await runMCPTarget(name, target, dryRun);
      const arrow = dryRun ? "→ (dry)" : "→ ";
      process.stdout.write(`✓ ${name.padEnd(16)} ${arrow} ${target.output}  (${summary})\n`);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      process.stderr.write(`✗ ${name}: ${message}\n`);
      succeeded = false;
    }
  }
  if (!succeeded) process.exit(1);
}

async function handleRunCommand(
  target: string | undefined,
  opts: RunCommandOptions
): Promise<void> {
  const configPath = path.resolve(opts.config ?? "apidiom.yaml");
  const config = await loadConfig(configPath);
  const targets = selectTargets(config, target);
  const dryRun = opts.dryRun ?? false;
  if (dryRun) process.stderr.write("Dry run — no files will be written.\n");
  await executeTargets(targets, dryRun);
}

program
  .command("run [target]")
  .description("Generate from apidiom.yaml (all targets, or a single named target)")
  .option("--config <file>", "Path to config file (default: ./apidiom.yaml)")
  .option("--dry-run", "Show what would be generated without writing files")
  .action(handleRunCommand);

program.parse(process.argv);
