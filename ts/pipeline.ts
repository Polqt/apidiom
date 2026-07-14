import fs from "fs/promises";
import path from "path";
import { extractAuth } from "./auth";
import type { TargetConfig } from "./config";
import { generateMCPServer } from "./generate/mcp";
import { buildToolMetadata } from "./generate/tools";
import { fetchSpec } from "./ingest/fetch";
import { parseOpenAPI } from "./ingest/parse";
import { REGISTRY } from "./registry";

export type MCPMode = "flat" | "search";
export type RequestedMCPMode = MCPMode | "auto" | undefined;

export type MCPGenerationOptions = {
  readonly tags?: string[];
  readonly include?: string[];
  readonly groupByTag?: boolean;
  readonly mode: RequestedMCPMode;
  readonly maxTools: number;
};

export type MCPGenerationResult = {
  readonly code: string;
  readonly warnings: string[];
};

async function loadModelAndAuth(source: string) {
  const doc = await fetchSpec(source);
  const model = parseOpenAPI(doc);
  const serviceName = Object.keys(REGISTRY).find(
    (key) => REGISTRY[key].url === source || key === source.toLowerCase()
  );
  return { model, auth: extractAuth(model, serviceName) };
}

function unsupportedAuthWarning(
  source: string,
  model: Awaited<ReturnType<typeof loadModelAndAuth>>["model"],
  auth: Awaited<ReturnType<typeof loadModelAndAuth>>["auth"]
): string | undefined {
  const hasUnsupportedAuth = model.authSchemes.some(
    (scheme) => scheme.type === "oauth2" || scheme.type === "openIdConnect"
  );
  if (!hasUnsupportedAuth || auth.length > 0) return undefined;
  return `Warning: "${source}" uses OAuth2/OpenID Connect auth - not supported in generated code. API calls will be unauthenticated and likely return 401.\n`;
}

function selectMCPMode(
  requestedMode: RequestedMCPMode,
  toolCount: number,
  maxTools: number,
  source: string
): { readonly mode: MCPMode; readonly warning?: string } {
  if (requestedMode === "search") return { mode: "search" };
  if ((requestedMode === undefined || requestedMode === "auto") && toolCount > maxTools) {
    return {
      mode: "search",
      warning:
        `Warning: ${toolCount} tools generated (~${Math.round(toolCount * 380)} tokens in tools/list) - switching to --mode search.\n` +
        `  Use --mode flat --max-tools ${toolCount} to force a flat tools/list.\n`,
    };
  }
  if (requestedMode === "flat" && toolCount > maxTools) {
    throw new Error(
      `${toolCount} tools generated (~${Math.round(toolCount * 380)} tokens in tools/list) - exceeds recommended limit of ${maxTools}.\n` +
        `  Use --mode search for progressive discovery, or --tag/--include to filter.\n` +
        `  To force flat mode, raise the guard: --mode flat --max-tools ${toolCount}\n` +
        `  Example: apidiom generate mcp ${source} --mode search --output server.js`
    );
  }
  return { mode: "flat" };
}

export async function generateMCP(
  source: string,
  options: MCPGenerationOptions
): Promise<MCPGenerationResult> {
  const { model, auth } = await loadModelAndAuth(source);
  const warnings: string[] = [];
  const authWarning = unsupportedAuthWarning(source, model, auth);
  if (authWarning) warnings.push(authWarning);

  const toolOptions = { tags: options.tags, include: options.include };
  const toolCount = buildToolMetadata(model.endpoints, toolOptions).length;
  const selection = selectMCPMode(options.mode, toolCount, options.maxTools, source);
  if (selection.warning) warnings.push(selection.warning);

  return {
    code: generateMCPServer(model, auth, {
      ...toolOptions,
      groupByTag: options.groupByTag,
      mode: selection.mode,
    }),
    warnings,
  };
}

export async function runMCPTarget(
  name: string,
  target: TargetConfig,
  dryRun = false
): Promise<string> {
  const { model, auth } = await loadModelAndAuth(target.source);
  const hasUnsupportedAuth = model.authSchemes.some(
    (scheme) => scheme.type === "oauth2" || scheme.type === "openIdConnect"
  );
  if (hasUnsupportedAuth && auth.length === 0) {
    process.stderr.write(
      `Warning [${name}]: uses OAuth2/OpenID Connect - API calls will be unauthenticated.\n`
    );
  }

  const toolOptions = {
    tags: target.tags && target.tags.length > 0 ? target.tags : undefined,
    include: target.include && target.include.length > 0 ? target.include : undefined,
  };
  const toolCount = buildToolMetadata(model.endpoints, toolOptions).length;
  const maxTools = target.maxTools ?? 40;
  if (target.mode === "flat" && toolCount > maxTools) {
    throw new Error(
      `${toolCount} tools exceeds max-tools limit of ${maxTools} for flat mode. Use mode: search or raise max-tools.`
    );
  }
  const mode: MCPMode =
    (target.mode === undefined || target.mode === "auto") && toolCount > maxTools
      ? "search"
      : target.mode === "search"
        ? "search"
        : "flat";

  if (!dryRun) {
    const code = generateMCPServer(model, auth, {
      ...toolOptions,
      groupByTag: target.groupByTag,
      mode,
    });
    const outputPath = path.resolve(target.output);
    await fs.mkdir(path.dirname(outputPath), { recursive: true });
    await fs.writeFile(outputPath, code, "utf-8");
  }
  return `${toolCount} tools, ${mode} mode`;
}
