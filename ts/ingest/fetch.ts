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
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
  const text = await res.text();
  return parseText(text, url);
}

async function fetchLocal(filePath: string): Promise<Record<string, unknown>> {
  const text = await fs.readFile(filePath, "utf-8");
  return parseText(text, filePath);
}

function parseText(text: string, source: string): Record<string, unknown> {
  if (source.endsWith(".json")) {
    return JSON.parse(text) as Record<string, unknown>;
  }
  return yaml.load(text) as Record<string, unknown>;
}
