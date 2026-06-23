import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";
import yaml from "js-yaml";
import { parseOpenAPI } from "../../ts/ingest/parse";
import { generateToolSchema } from "../../ts/generate/schema";
import type { APIModel } from "../../ts/model";

const FIXTURE_PATH = path.resolve(__dirname, "../fixtures/petstore.yaml");
const doc = yaml.load(fs.readFileSync(FIXTURE_PATH, "utf-8")) as Record<string, unknown>;
const model = parseOpenAPI(doc);

describe("generateToolSchema", () => {
  it("generates Anthropic tool schemas with endpoint params", () => {
    const output = JSON.parse(
      generateToolSchema(model, { format: "anthropic", include: ["getPet"] })
    );

    expect(output).toEqual([
      {
        name: "get_pet",
        description: "Info for a specific pet. Params: petId (required).",
        input_schema: {
          type: "object",
          properties: {
            petId: { type: "integer", format: "int64" },
          },
          required: ["petId"],
        },
      },
    ]);
  });

  it("generates OpenAI function tool schemas", () => {
    const output = JSON.parse(
      generateToolSchema(model, { format: "openai", include: ["listPets"] })
    );

    expect(output).toEqual([
      {
        type: "function",
        function: {
          name: "list_pets",
          description: "List all pets.",
          parameters: {
            type: "object",
            properties: {
              limit: {
                type: "integer",
                format: "int32",
                description: "Maximum number of pets to return",
              },
            },
            required: [],
          },
        },
      },
    ]);
  });

  it("keeps request bodies as a single body object parameter", () => {
    const output = JSON.parse(
      generateToolSchema(model, { format: "anthropic", include: ["createPet"] })
    );

    expect(output[0].input_schema.properties.body).toEqual({
      type: "object",
      description: "Request body",
    });
    expect(output[0].input_schema.required).toEqual(["body"]);
  });

  it("filters by tag and include", () => {
    const output = JSON.parse(
      generateToolSchema(model, {
        format: "anthropic",
        tags: ["pets"],
        include: ["listPets"],
      })
    );

    expect(output.map((tool: { name: string }) => tool.name)).toEqual(["list_pets"]);
  });

  it("deduplicates normalized tool names like MCP generation", () => {
    const collidingModel: APIModel = {
      title: "Test API",
      version: "1.0",
      serverUrl: "https://api.example.com",
      authSchemes: [],
      endpoints: [
        {
          path: "/pets",
          method: "GET",
          operationId: "GetV1Pets",
          tags: [],
          parameters: [],
        },
        {
          path: "/pets/all",
          method: "GET",
          operationId: "GetV2Pets",
          tags: [],
          parameters: [],
        },
      ],
    };

    const output = JSON.parse(generateToolSchema(collidingModel, { format: "anthropic" }));
    expect(output.map((tool: { name: string }) => tool.name)).toEqual([
      "get_pets",
      "get_pets_2",
    ]);
  });
});
