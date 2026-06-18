EXTRACTION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "openapi": {"type": "string"},
        "info": {"type": "object"},
        "servers": {"type": "array"},
        "paths": {"type": "object"},
        "components": {"type": "object"},
    },
    "required": ["openapi", "info", "paths"],
}

EXTRACTION_USER_TEMPLATE = """GLOBAL CONTEXT (from earlier chunks; may say "unknown")
Base URL(s): {servers_or_unknown}
Authentication: {auth_or_unknown}
Known shared models: {schema_names_or_none}

DOCUMENTATION CHUNK {i} of {n}
{cleaned_chunk_text}

Extract the OpenAPI fragment for the endpoints documented in THIS chunk only.
Follow all rules. Output only the JSON object."""

REPAIR_SYSTEM = """You are fixing validation errors in an OpenAPI 3.1 JSON document. Output only
the corrected single JSON object — no prose, no fences.

RULES
1. Make the MINIMUM changes needed to resolve the listed errors and produce
   valid OpenAPI 3.1.
2. Do NOT add, remove, rename, or change any endpoint, parameter, property,
   type, or value except as strictly necessary to fix a listed error. You are
   correcting structure, not improving content.
3. Never invent data to fill a gap. If an error stems from missing information,
   use an unconstrained schema {} and keep the x-apidiom-unknown marker rather
   than fabricating a value.
4. Preserve all existing x-apidiom-unknown markers and UNVERIFIED notes."""

EXTRACTION_SYSTEM = """You are a precise API-documentation extractor. You read raw API documentation
text and produce a SINGLE OpenAPI 3.1 JSON object describing only the API
surface the text explicitly documents.

ABSOLUTE RULES
1. Output one valid JSON object and nothing else. No prose, no markdown, no code
   fences. The first character must be "{" and the last "}".
2. Extract ONLY what the text explicitly states. Never invent, assume, or infer
   endpoints, paths, methods, parameters, properties, types, formats, status
   codes, authentication, examples, or descriptions. If it is not in the text,
   it does not appear in the output.
3. When a detail is missing or ambiguous, DO NOT GUESS. Instead:
   - Use an unconstrained schema {} for an unstated type (do not default to
     "string").
   - On the nearest object, add a vendor extension "x-apidiom-unknown": a JSON
     array of the field names you could not determine (e.g. ["type","required"]).
   - Prefix a short note in that object's "description" with "UNVERIFIED:"
     stating what was unclear.
4. Never mark a parameter or property "required" unless the text explicitly says
   so. Uncertainty defaults to not-required, with "required" added to
   x-apidiom-unknown.
5. Never fabricate example values. Include "example" only if the text shows one.
6. Use components.schemas for reusable models and $ref them — but only create a
   schema you can ground in the text.
7. If this chunk contains no API endpoint information, return exactly:
   {"openapi":"3.1.0","info":{"title":"untitled","version":"0.0.0"},"paths":{}}

Emit a partial OpenAPI 3.1 document: "openapi", "info", "paths", and
"components.schemas" where applicable. Include "servers" or "securitySchemes"
ONLY if this chunk states them."""
