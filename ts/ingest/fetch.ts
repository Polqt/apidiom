import fs from "fs/promises";
import yaml from "js-yaml";
import { resolveSource } from "../registry";
import { resolveRefs } from "./resolve";

export async function fetchSpec(source: string): Promise<Record<string, unknown>> {
  const resolved = resolveSource(source);
  const isRemote = resolved.startsWith("https://") || resolved.startsWith("http://");

  try {
    const raw = isRemote ? await fetchRemote(resolved) : await fetchLocal(resolved);
    return resolveRefs(absolutizeServers(raw, isRemote ? resolved : undefined));
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`Could not load spec from "${source}": ${msg}`);
  }
}

// OpenAPI allows relative server URLs, resolved against the doc's own origin.
// A generated client needs an absolute base URL or `new URL()` throws at runtime.
// When fetched remotely, resolve against the fetch origin; local specs with a
// relative server URL are left as-is (no origin to resolve against — the
// generator warns and the user sets APIDIOM_BASE_URL).
export function absolutizeServers(
  doc: Record<string, unknown>,
  specUrl: string | undefined
): Record<string, unknown> {
  if (!specUrl) return doc;
  const servers = doc["servers"];
  if (!Array.isArray(servers) || servers.length === 0) return doc;

  const rewritten = servers.map((entry) => {
    if (typeof entry !== "object" || entry === null) return entry;
    const url = (entry as Record<string, unknown>)["url"];
    if (typeof url !== "string" || url === "") return entry;
    if (/^https?:\/\//.test(url)) return entry;
    try {
      return { ...(entry as Record<string, unknown>), url: new URL(url, specUrl).toString() };
    } catch {
      return entry;
    }
  });

  return { ...doc, servers: rewritten };
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
