import type { Doc } from "../model";

const HTTP_METHODS = ["get", "post", "put", "patch", "delete", "head", "options"];

function isDoc(value: unknown): value is Doc {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function resolveRefs(doc: Doc): Doc {
  const paths = doc["paths"] as Record<string, Doc> | undefined;
  if (!paths) return doc;

  function lookup(ref: string): unknown {
    const parts = ref.slice(2).split("/");
    let node: unknown = doc;
    for (const part of parts) {
      if (!isDoc(node)) return undefined;
      node = node[decodeURIComponent(part.replace(/~1/g, "/").replace(/~0/g, "~"))];
    }
    return node;
  }

  const warnedExternalRefs = new Set<string>();

  function warnExternalRef(ref: string): void {
    if (warnedExternalRefs.has(ref)) return;
    warnedExternalRefs.add(ref);
    process.stderr.write(`Warning: external $ref "${ref}" not supported — skipped.\n`);
  }

  function deref(node: unknown): unknown {
    if (!isDoc(node)) return node;
    const ref = node["$ref"];
    if (typeof ref !== "string") return node;
    if (ref.startsWith("#/")) return lookup(ref) ?? node;
    warnExternalRef(ref);
    return node;
  }

  const schemaCache = new Map<string, unknown>();

  function resolveSchema(node: unknown, activeRefs = new Set<string>()): unknown {
    if (Array.isArray(node)) {
      return node.map((item) => resolveSchema(item, activeRefs));
    }
    if (!isDoc(node)) return node;

    const ref = node["$ref"];
    if (typeof ref === "string" && !ref.startsWith("#/")) {
      warnExternalRef(ref);
      return node;
    }
    if (typeof ref === "string" && ref.startsWith("#/")) {
      return resolveLocalSchemaRef(node, ref, activeRefs);
    }

    return Object.fromEntries(
      Object.entries(node).map(([key, value]) => [key, resolveSchema(value, activeRefs)])
    );
  }

  function resolveLocalSchemaRef(
    schema: Doc,
    ref: string,
    activeRefs: Set<string>
  ): unknown {
    if (activeRefs.has(ref)) return {};
    if (Object.keys(schema).length === 1 && schemaCache.has(ref)) {
      return schemaCache.get(ref);
    }

    const target = lookup(ref);
    if (!isDoc(target)) return schema;

    const nextRefs = new Set(activeRefs);
    nextRefs.add(ref);
    const siblings = Object.fromEntries(
      Object.entries(schema).filter(([key]) => key !== "$ref")
    );
    const resolved = resolveSchema({ ...target, ...siblings }, nextRefs);
    if (Object.keys(schema).length === 1) schemaCache.set(ref, resolved);
    return resolved;
  }

  function resolveParameter(node: unknown): unknown {
    const parameter = deref(node);
    if (!isDoc(parameter)) return parameter;
    return parameter["schema"] === undefined
      ? parameter
      : { ...parameter, schema: resolveSchema(parameter["schema"]) };
  }

  // Deref the requestBody envelope, then deep-resolve each content type's schema
  // so body fields survive as concrete properties instead of an unresolved $ref.
  function resolveRequestBody(node: unknown): unknown {
    const body = deref(node);
    if (!isDoc(body)) return body;
    const content = body["content"];
    if (!isDoc(content)) return body;
    const resolvedContent = Object.fromEntries(
      Object.entries(content).map(([mediaType, media]) => {
        if (!isDoc(media)) return [mediaType, media];
        return media["schema"] === undefined
          ? [mediaType, media]
          : [mediaType, { ...media, schema: resolveSchema(media["schema"]) }];
      })
    );
    return { ...body, content: resolvedContent };
  }

  const resolvedPaths: Record<string, Doc> = {};

  for (const [path, pathItem] of Object.entries(paths)) {
    if (typeof pathItem !== "object" || pathItem === null) {
      resolvedPaths[path] = pathItem;
      continue;
    }

    const pi = pathItem;
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
