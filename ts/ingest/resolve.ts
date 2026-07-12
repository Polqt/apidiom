import type { Doc } from "../model";

const HTTP_METHODS = ["get", "post", "put", "patch", "delete", "head", "options"];

export function resolveRefs(doc: Doc): Doc {
  const paths = doc["paths"] as Record<string, Doc> | undefined;
  if (!paths) return doc;

  function lookup(ref: string): unknown {
    const parts = ref.slice(2).split("/");
    let node: unknown = doc;
    for (const part of parts) {
      if (typeof node !== "object" || node === null) return undefined;
      node = (node as Doc)[decodeURIComponent(part.replace(/~1/g, "/").replace(/~0/g, "~"))];
    }
    return node;
  }

  const warnedExternalRefs = new Set<string>();

  function deref(node: unknown): unknown {
    if (typeof node !== "object" || node === null) return node;
    const ref = (node as Doc)["$ref"];
    if (typeof ref !== "string") return node;
    if (ref.startsWith("#/")) return lookup(ref) ?? node;
    if (!warnedExternalRefs.has(ref)) {
      warnedExternalRefs.add(ref);
      process.stderr.write(`Warning: external $ref "${ref}" not supported — skipped.\n`);
    }
    return node;
  }

  const schemaCache = new Map<string, unknown>();

  function resolveSchema(node: unknown, activeRefs = new Set<string>()): unknown {
    if (Array.isArray(node)) {
      return node.map((item) => resolveSchema(item, activeRefs));
    }
    if (typeof node !== "object" || node === null) return node;

    const schema = node as Doc;
    const ref = schema["$ref"];
    if (typeof ref === "string" && !ref.startsWith("#/")) {
      if (!warnedExternalRefs.has(ref)) {
        warnedExternalRefs.add(ref);
        process.stderr.write(`Warning: external $ref "${ref}" not supported — skipped.\n`);
      }
      return node;
    }
    if (typeof ref === "string" && ref.startsWith("#/")) {
      if (activeRefs.has(ref)) return {};
      if (Object.keys(schema).length === 1 && schemaCache.has(ref)) {
        return schemaCache.get(ref);
      }

      const target = lookup(ref);
      if (typeof target !== "object" || target === null) return node;

      const nextRefs = new Set(activeRefs);
      nextRefs.add(ref);
      const siblings = Object.fromEntries(
        Object.entries(schema).filter(([key]) => key !== "$ref")
      );
      const resolved = resolveSchema({ ...(target as Doc), ...siblings }, nextRefs);
      if (Object.keys(schema).length === 1) schemaCache.set(ref, resolved);
      return resolved;
    }

    return Object.fromEntries(
      Object.entries(schema).map(([key, value]) => [key, resolveSchema(value, activeRefs)])
    );
  }

  function resolveParameter(node: unknown): unknown {
    const parameter = deref(node);
    if (typeof parameter !== "object" || parameter === null) return parameter;
    const value = parameter as Doc;
    return value["schema"] === undefined
      ? value
      : { ...value, schema: resolveSchema(value["schema"]) };
  }

  // Deref the requestBody envelope, then deep-resolve each content type's schema
  // so body fields survive as concrete properties instead of an unresolved $ref.
  function resolveRequestBody(node: unknown): unknown {
    const body = deref(node);
    if (typeof body !== "object" || body === null) return body;
    const value = body as Doc;
    const content = value["content"];
    if (typeof content !== "object" || content === null) return value;
    const resolvedContent = Object.fromEntries(
      Object.entries(content as Record<string, unknown>).map(([mediaType, media]) => {
        if (typeof media !== "object" || media === null) return [mediaType, media];
        const m = media as Doc;
        return m["schema"] === undefined
          ? [mediaType, m]
          : [mediaType, { ...m, schema: resolveSchema(m["schema"]) }];
      })
    );
    return { ...value, content: resolvedContent };
  }

  const resolvedPaths: Record<string, Doc> = {};

  for (const [path, pathItem] of Object.entries(paths)) {
    if (typeof pathItem !== "object" || pathItem === null) {
      resolvedPaths[path] = pathItem as Doc;
      continue;
    }

    const pi = pathItem as Doc;
    const sharedParams =
      (pi["parameters"] as unknown[] | undefined)?.map(resolveParameter) ?? [];
    const resolved: Doc = { ...pi };

    for (const method of HTTP_METHODS) {
      const op = pi[method];
      if (typeof op !== "object" || op === null) continue;
      const operation = op as Doc;

      const opParams =
        (operation["parameters"] as unknown[] | undefined)?.map(resolveParameter) ?? [];
      const mergedParams = mergeParams(sharedParams, opParams);

      resolved[method] = {
        ...operation,
        parameters: mergedParams,
        ...(operation["requestBody"] !== undefined
          ? { requestBody: resolveRequestBody(operation["requestBody"]) }
          : {}),
      };
    }

    const { parameters: _, ...pathWithoutParams } = resolved;
    resolvedPaths[path] = pathWithoutParams;
  }

  return { ...doc, paths: resolvedPaths };
}

function mergeParams(shared: unknown[], operation: unknown[]): unknown[] {
  const opNames = new Set(
    operation.map((p) => {
      const param = p as Doc;
      return `${param["in"]}:${param["name"]}`;
    })
  );
  const base = shared.filter((p) => {
    const param = p as Doc;
    return !opNames.has(`${param["in"]}:${param["name"]}`);
  });
  return [...base, ...operation];
}
