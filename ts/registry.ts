import registryData from "./registry.json";

export interface RegistryEntry {
  url: string;
  description: string;
}

export const REGISTRY = registryData as Record<string, RegistryEntry>;

const URL_PREFIXES = ["https://", "http://", "/", "./", "../"];
// Windows absolute paths: C:\ or C:/
const WINDOWS_ABS_PATH = /^[A-Za-z]:[/\\]/;

export function resolveSource(source: string): string {
  if (URL_PREFIXES.some((p) => source.startsWith(p)) || WINDOWS_ABS_PATH.test(source)) {
    return source;
  }
  const entry = REGISTRY[source.toLowerCase()];
  if (!entry) {
    const known = Object.keys(REGISTRY).join(", ");
    throw new Error(
      `Unknown service "${source}". Known services: ${known}.\n` +
        `Pass a URL or file path to use a custom spec.`
    );
  }
  return entry.url;
}
