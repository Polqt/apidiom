import type { Doc } from "../model";

const HTTP_METHODS = ["get", "post", "put", "patch", "delete", "head", "options"];

/**
 * Resolves local $ref pointers at the parameter and requestBody level only.
 * Does NOT recurse into schemas — avoids OOM on large specs like Stripe.
 */
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

  function deref(node: unknown): unknown {
    if (typeof node !== "object" || node === null) return node;
    const ref = (node as Doc)["$ref"];
    if (typeof ref === "string" && ref.startsWith("#/")) return lookup(ref) ?? node;
    return node;
  }

  const resolvedPaths: Record<string, Doc> = {};

  for (const [path, pathItem] of Object.entries(paths)) {
    if (typeof pathItem !== "object" || pathItem === null) {
      resolvedPaths[path] = pathItem as Doc;
      continue;
    }

    const pi = pathItem as Doc;
    // Path-level shared parameters
    const sharedParams = (pi["parameters"] as unknown[] | undefined)?.map(deref) ?? [];
    const resolved: Doc = { ...pi };

    for (const method of HTTP_METHODS) {
      const op = pi[method];
      if (typeof op !== "object" || op === null) continue;
      const operation = op as Doc;

      // Merge shared params under operation params (operation-level wins)
      const opParams = (operation["parameters"] as unknown[] | undefined)?.map(deref) ?? [];
      const mergedParams = mergeParams(sharedParams, opParams);

      resolved[method] = {
        ...operation,
        parameters: mergedParams,
        ...(operation["requestBody"] !== undefined
          ? { requestBody: deref(operation["requestBody"]) }
          : {}),
      };
    }

    // Remove path-level parameters (now merged into each operation)
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
