import type { APIModel } from "../model";
import { buildToolMetadata, type ToolGenOptions } from "./tools";

export type SchemaFormat = "anthropic" | "openai";

interface SchemaGenOptions extends ToolGenOptions {
  format: SchemaFormat;
}

export function generateToolSchema(model: APIModel, opts: SchemaGenOptions): string {
  const tools = buildToolMetadata(model.endpoints, opts);
  const output = tools.map((tool) => {
    if (opts.format === "anthropic") {
      return {
        name: tool.name,
        description: tool.description,
        input_schema: tool.inputSchema,
      };
    }

    return {
      type: "function",
      function: {
        name: tool.name,
        description: tool.description,
        parameters: tool.inputSchema,
      },
    };
  });

  return JSON.stringify(output, null, 2);
}
