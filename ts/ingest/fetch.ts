import fs from "fs/promises";
import yaml from "js-yaml";
import { resolveSource } from "../registry";
import { resolveRefs } from "./resolve";

export async function fetchSpec(source: string): Promise<Record<string, unknown>> {
  const resolved = resolveSource(source);

  try {
    const raw = resolved.startsWith("https://") || resolved.startsWith("http://")
      ? await fetchRemote(resolved)
      : await fetchLocal(resolved);
    return resolveRefs(raw);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`Could not load spec from "${source}": ${msg}`);
  }
}

async function fetchRemote(url: string): Promise<Record<string, unknown>> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    const text = await res.text();
    return parseSpec(text, url);
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchLocal(filePath: string): Promise<Record<string, unknown>> {
  const text = await fs.readFile(filePath, "utf-8");
  return parseSpec(text, filePath);
}

export function parseSpec(text: string, source: string): Record<string, unknown> {
  const trimmed = text.trimStart();
  const looksLikeJson = trimmed.startsWith("{") || trimmed.startsWith("[") || source.endsWith(".json");
  if (looksLikeJson) {
    const parsed = JSON.parse(text);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      throw new Error("JSON document is not an object");
    }
    return parsed as Record<string, unknown>;
  }
  const result = yaml.load(text);
  if (typeof result !== "object" || result === null || Array.isArray(result)) {
    throw new Error("YAML document is not an object");
  }
  return result as Record<string, unknown>;
}
