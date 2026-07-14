import yaml from "js-yaml";

export interface TargetConfig {
  source: string;
  output: string;
  mode?: "flat" | "search" | "auto";
  tags?: string[];
  include?: string[];
  groupByTag?: boolean;
  maxTools?: number;
}

export interface ApidiomConfig {
  targets: Record<string, TargetConfig>;
}

function isTargetMode(value: unknown): value is TargetConfig["mode"] {
  return value === "flat" || value === "search" || value === "auto";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringArray(value: unknown): string[] | undefined {
  if (
    !Array.isArray(value) ||
    !value.every((item): item is string => typeof item === "string")
  ) {
    return undefined;
  }
  return value;
}

function parseTarget(name: string, entry: unknown): TargetConfig {
  if (!isRecord(entry)) {
    throw new Error(`Target "${name}" must be an object`);
  }
  const target = entry;

  if (typeof target.source !== "string" || !target.source) {
    throw new Error(`Target "${name}" missing required field: source`);
  }
  if (typeof target.output !== "string" || !target.output) {
    throw new Error(`Target "${name}" missing required field: output`);
  }
  if (target.mode !== undefined && !isTargetMode(target.mode)) {
    const invalidMode =
      typeof target.mode === "string" ? `"${target.mode}"` : `of type ${typeof target.mode}`;
    throw new Error(
      `Target "${name}" has invalid mode ${invalidMode}. Must be flat, search, or auto`
    );
  }

  return {
    source: target.source,
    output: target.output,
    mode: isTargetMode(target.mode) ? target.mode : undefined,
    tags: stringArray(target.tags),
    include: stringArray(target.include),
    groupByTag:
      typeof target["group-by-tag"] === "boolean" ? target["group-by-tag"] : undefined,
    maxTools: typeof target["max-tools"] === "number" ? target["max-tools"] : undefined,
  };
}

export function parseConfig(raw: string): ApidiomConfig {
  const doc = yaml.load(raw) as Record<string, unknown>;

  if (!doc || typeof doc.targets !== "object" || doc.targets === null || Array.isArray(doc.targets)) {
    throw new Error("Config must have a 'targets' object");
  }

  const rawTargets = doc.targets as Record<string, unknown>;
  if (Object.keys(rawTargets).length === 0) {
    throw new Error("'targets' must have at least one entry");
  }

  const targets: Record<string, TargetConfig> = {};

  for (const [name, entry] of Object.entries(rawTargets)) {
    targets[name] = parseTarget(name, entry);
  }

  return { targets };
}
