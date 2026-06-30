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
    const t = entry as Record<string, unknown>;

    if (typeof t.source !== "string" || !t.source) {
      throw new Error(`Target "${name}" missing required field: source`);
    }
    if (typeof t.output !== "string" || !t.output) {
      throw new Error(`Target "${name}" missing required field: output`);
    }

    const mode = t.mode as string | undefined;
    if (mode !== undefined && mode !== "flat" && mode !== "search" && mode !== "auto") {
      throw new Error(`Target "${name}" has invalid mode "${mode}". Must be flat, search, or auto`);
    }

    targets[name] = {
      source: t.source,
      output: t.output,
      mode: mode as TargetConfig["mode"],
      tags: Array.isArray(t.tags) ? (t.tags as string[]) : undefined,
      include: Array.isArray(t.include) ? (t.include as string[]) : undefined,
      groupByTag: typeof t["group-by-tag"] === "boolean" ? t["group-by-tag"] : undefined,
      maxTools: typeof t["max-tools"] === "number" ? t["max-tools"] : undefined,
    };
  }

  return { targets };
}
