import type { APIEndpoint, OpenAPIParam } from "../model";

export interface ToolGenOptions {
  tags?: string[];
  include?: string[];
  groupByTag?: boolean;
}

export interface ToolMetadata {
  endpoint: APIEndpoint;
  name: string;
  rawName: string;
  description: string;
  inputSchema: {
    type: "object";
    properties: Record<string, unknown>;
    required: string[];
  };
}

export function normalizeToolName(operationId: string): string {
  let name = operationId.replace(/V\d+/g, "");
  name = name
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1_$2")
    .replace(/([a-z\d])([A-Z])/g, "$1_$2")
    .toLowerCase()
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
  return name || operationId.toLowerCase();
}

export function enrichDescription(
  summary: string | undefined,
  description: string | undefined,
  params: OpenAPIParam[]
): string {
  const parts: string[] = [];

  const cleanSummary = summary?.replace(/\.$/, "").trim();
  if (cleanSummary) parts.push(cleanSummary);

  if (description) {
    const firstSentence = description.split(/\.\s+/)[0].replace(/\.$/, "").trim();
    if (firstSentence && firstSentence !== cleanSummary) {
      parts.push(firstSentence);
    }
  }

  const requiredParams = params.filter(
    (p) => p.required && (p.in === "path" || p.in === "query")
  );
  if (requiredParams.length > 0) {
    parts.push(`Params: ${requiredParams.map((p) => `${p.name} (required)`).join(", ")}`);
  }

  return parts.length > 0 ? parts.join(". ") + "." : "";
}

function filterEndpoints(
  endpoints: APIEndpoint[],
  opts: ToolGenOptions
): APIEndpoint[] {
  let result = endpoints;
  if (opts.tags && opts.tags.length > 0) {
    result = result.filter((e) => e.tags.some((t) => opts.tags!.includes(t)));
  }
  if (opts.include && opts.include.length > 0) {
    result = result.filter((e) => opts.include!.includes(e.operationId));
  }
  return result;
}

export function deduplicateToolNames(names: string[]): string[] {
  const seen = new Set<string>();
  return names.map((name) => {
    if (!seen.has(name)) {
      seen.add(name);
      return name;
    }
    let i = 2;
    let candidate = `${name}_${i}`;
    while (seen.has(candidate)) candidate = `${name}_${++i}`;
    seen.add(candidate);
    return candidate;
  });
}

export function buildInputSchema(endpoint: APIEndpoint): ToolMetadata["inputSchema"] {
  const properties: Record<string, unknown> = {};
  const required: string[] = [];

  for (const p of endpoint.parameters) {
    if (p.in === "path" || p.in === "query" || p.in === "header") {
      properties[p.name] = p.description
        ? { ...p.schema, description: p.description }
        : { ...p.schema };
      if (p.required) required.push(p.name);
    }
  }

  if (endpoint.requestBody) {
    properties.body = {
      type: "object",
      description: endpoint.requestBody.description ?? "Request body",
    };
    if (endpoint.requestBody.required) required.push("body");
  }

  return { type: "object", properties, required };
}

export function buildToolMetadata(
  endpoints: APIEndpoint[],
  opts: ToolGenOptions = {}
): ToolMetadata[] {
  const filtered = filterEndpoints(endpoints, opts);
  const rawNames = filtered.map((ep) => {
    const base = normalizeToolName(ep.operationId);
    if (opts.groupByTag && ep.tags.length > 0) return `${ep.tags[0]}__${base}`;
    return base;
  });
  const names = deduplicateToolNames(rawNames);

  return filtered.map((endpoint, index) => ({
    endpoint,
    name: names[index],
    rawName: rawNames[index],
    description: enrichDescription(endpoint.summary, endpoint.description, endpoint.parameters),
    inputSchema: buildInputSchema(endpoint),
  }));
}
