import type { APIEndpoint, APIModel, AuthConfig } from "../model";
import { buildToolMetadata, type ToolMetadata } from "./tools";

interface MCPGenOptions {
  tags?: string[];
  include?: string[];
  groupByTag?: boolean;
  mode?: "flat" | "search";
}

export function generateMCPServer(
  model: APIModel,
  auth: AuthConfig[],
  opts: MCPGenOptions = {}
): string {
  const tools = buildToolMetadata(model.endpoints, opts);
  const serverName = toSlug(model.title);

  tools.forEach((tool) => {
    if (tool.name !== tool.rawName) {
      process.stderr.write(
        `Warning: duplicate tool name "${tool.rawName}" renamed to "${tool.name}"\n`
      );
    }
  });

  const parts: (string | null)[] = [
    `"use strict";`,
    `// ${model.title} v${model.version}`,
    ``,
    `const https = require("https");`,
    `const http = require("http");`,
    ``,
    generateAuthSection(auth),
    generateRequestHelper(),
    generateToolsArray(tools, model.serverUrl, auth),
    opts.mode === "search"
      ? generateSearchHandler(serverName, model.version)
      : generateMCPHandler(serverName, model.version),
  ];

  return parts.filter((s) => s !== null).join("\n");
}

function generateAuthSection(auth: AuthConfig[]): string | null {
  if (auth.length === 0) return null;
  const lines: string[] = [];
  for (const a of auth) {
    lines.push(
      `const ${a.envVar} = process.env.${a.envVar};`,
      `if (!${a.envVar}) { process.stderr.write("Missing required env var: ${a.envVar}\\n"); process.exit(1); }`
    );
  }
  lines.push(``);
  return lines.join("\n");
}

function generateRequestHelper(): string {
  return `function _request(method, url, headers, body) {
  return new Promise(function(resolve, reject) {
      var u = new URL(url);
      var lib = u.protocol === "https:" ? https : http;
      var opts = {
        hostname: u.hostname,
        port: u.port || undefined,
        path: u.pathname + u.search,
        method: method,
        headers: Object.assign({}, body !== undefined ? { "Content-Type": "application/json" } : {}, headers)
      };
      var req = lib.request(opts, function(res) {
        var d = "";
        res.on("data", function(c) { d += c; });
        res.on("error", reject);
        res.on("end", function() {
          var result;
          try { result = JSON.parse(d); } catch(e) { result = d; }
          var status = res.statusCode || 0;
          if (status < 200 || status >= 300) {
            var detail = typeof result === "string" ? result : JSON.stringify(result);
            reject(new Error("HTTP " + status + (detail ? ": " + detail : "")));
            return;
          }
          resolve(result);
        });
      });
      req.on("error", reject);
      if (body !== undefined) req.write(JSON.stringify(body));
      req.end();
    });
  }`;
}

function generateToolsArray(tools: ToolMetadata[], serverUrl: string, auth: AuthConfig[]): string {
  const rendered = tools.map((tool) => generateTool(tool, serverUrl, auth));
  return `var _TOOLS = [\n${rendered.join(",\n")}\n];\n`;
}

function generateTool(tool: ToolMetadata, serverUrl: string, auth: AuthConfig[]): string {
  const ep = tool.endpoint;
  const pathParams = ep.parameters.filter((p) => p.in === "path");
  const queryParams = ep.parameters.filter((p) => p.in === "query");
  const headerParams = ep.parameters.filter((p) => p.in === "header");

  const headerAuth = auth.filter((a) => typeof a.queryParam !== "string");
  const queryAuth = auth.filter((a) => typeof a.queryParam === "string");

  const authHeaderEntries = headerAuth.map((a) => {
    const headerValue = buildHeaderValue(a);
    return `      ${JSON.stringify(a.headerName)}: ${headerValue}`;
  });
  const authHeadersStr =
    authHeaderEntries.length > 0
      ? `{\n${authHeaderEntries.join(",\n")}\n    }`
      : "{}";

  const urlParts = buildUrlParts(serverUrl, ep.path, pathParams);

  const queryLines: string[] = [];
  queryLines.push(`    var _q = new URLSearchParams();`);
  for (const p of queryParams) {
    queryLines.push(
      `    if (args[${JSON.stringify(p.name)}] !== undefined) _q.set(${JSON.stringify(p.name)}, String(args[${JSON.stringify(p.name)}]));`
    );
  }
  for (const a of queryAuth) {
    queryLines.push(`    _q.set(${JSON.stringify(a.queryParam)}, ${a.envVar});`);
  }
  queryLines.push(`    var _qs = _q.toString() ? "?" + _q.toString() : "";`);

  const headerLines: string[] = [`    var _headers = ${authHeadersStr};`];
  for (const p of headerParams) {
    headerLines.push(
      `    if (args[${JSON.stringify(p.name)}] !== undefined) _headers[${JSON.stringify(p.name)}] = String(args[${JSON.stringify(p.name)}]);`
    );
  }

  const bodyArg = ep.requestBody ? `args["body"]` : "undefined";
  const urlExpr = `(${urlParts}) + _qs`;

  return `  {
    name: ${JSON.stringify(tool.name)},
    description: ${JSON.stringify(tool.description)},
    inputSchema: ${JSON.stringify(tool.inputSchema)},
    _tags: ${JSON.stringify(ep.tags)},
    call: function(args) {
      ${queryLines.join("\n")}
      ${headerLines.join("\n")}
      return _request(${JSON.stringify(ep.method)}, ${urlExpr}, _headers, ${bodyArg});
    }
  }`;
}

function buildUrlParts(
  serverUrl: string,
  path: string,
  pathParams: APIEndpoint["parameters"]
): string {
  if (pathParams.length === 0) {
    return JSON.stringify(serverUrl + path);
  }

  const segments: string[] = [];
  let remaining = serverUrl + path;
  const paramPattern = /\{([^}]+)\}/;
  let match: RegExpExecArray | null;

  while ((match = paramPattern.exec(remaining)) !== null) {
    const before = remaining.slice(0, match.index);
    const paramName = match[1];
    if (before) segments.push(JSON.stringify(before));
    segments.push(`(args[${JSON.stringify(paramName)}] !== undefined ? encodeURIComponent(String(args[${JSON.stringify(paramName)}])) : (function(){ throw new Error("Missing required path parameter: ${paramName}"); })())`);
    remaining = remaining.slice(match.index + match[0].length);
  }
  if (remaining) segments.push(JSON.stringify(remaining));

  return segments.join(" + ");
}

function buildHeaderValue(auth: AuthConfig): string {
  const format = auth.headerFormat;
  if (format === "{value}") {
    return auth.envVar;
  }
  const parts = format.split("{value}");
  const result: string[] = [];
  for (let i = 0; i < parts.length; i++) {
    if (parts[i]) result.push(JSON.stringify(parts[i]));
    if (i < parts.length - 1) result.push(auth.envVar);
  }
  return result.join(" + ");
}

function generateMCPProtocol(
  serverName: string,
  version: string,
  toolsListBody: string,
  toolsCallBody: string
): string {
  return `var _buf = "";
  process.stdin.setEncoding("utf8");
  function _processLine(line) {
    if (!line.trim()) return;
    var msg;
    try { msg = JSON.parse(line); } catch(e) { return; }
    _handle(msg).catch(function(e) { process.stderr.write((e instanceof Error ? e.message : String(e)) + "\\n"); });
  }
  process.stdin.on("data", function(chunk) {
    _buf += chunk;
    var lines = _buf.split("\\n");
    _buf = lines.pop() || "";
    for (var i = 0; i < lines.length; i++) { _processLine(lines[i]); }
  });
  process.stdin.on("end", function() {
    if (_buf.trim()) _processLine(_buf);
  });

  function _send(obj) { process.stdout.write(JSON.stringify(obj) + "\\n"); }

  function _handle(msg) {
    var id = msg.id;
    var method = msg.method;
    var params = msg.params;
    if (method === "initialize") {
      _send({ jsonrpc: "2.0", id: id, result: { protocolVersion: "2024-11-05", capabilities: { tools: {} }, serverInfo: { name: ${JSON.stringify(serverName)}, version: ${JSON.stringify(version)} } } });
      return Promise.resolve();
    } else if (method === "notifications/initialized") {
      return Promise.resolve();
    } else if (method === "tools/list") {
      ${toolsListBody}
    } else if (method === "tools/call") {
      ${toolsCallBody}
    } else if (id !== undefined) {
      _send({ jsonrpc: "2.0", id: id, error: { code: -32601, message: "Method not found: " + method } });
      return Promise.resolve();
    }
    return Promise.resolve();
  }`;
}

function generateMCPHandler(serverName: string, version: string): string {
  const toolsListBody = `_send({ jsonrpc: "2.0", id: id, result: { tools: _TOOLS.map(function(t) { return { name: t.name, description: t.description, inputSchema: t.inputSchema }; }) } });
    return Promise.resolve();`;

  const toolsCallBody = `var toolName = params && params.name;
    var tool = null;
    for (var i = 0; i < _TOOLS.length; i++) {
      if (_TOOLS[i].name === toolName) { tool = _TOOLS[i]; break; }
    }
    if (!tool) {
      _send({ jsonrpc: "2.0", id: id, error: { code: -32601, message: "Unknown tool: " + toolName } });
      return Promise.resolve();
    }
    return Promise.resolve(tool.call((params && params.arguments) || {})).then(function(result) {
      _send({ jsonrpc: "2.0", id: id, result: { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] } });
    }).catch(function(e) {
      _send({ jsonrpc: "2.0", id: id, result: { content: [{ type: "text", text: "Error: " + (e instanceof Error ? e.message : String(e)) }], isError: true } });
    });`;

  return generateMCPProtocol(serverName, version, toolsListBody, toolsCallBody);
}

function generateSearchHandler(serverName: string, version: string): string {
  const scorer = `function _tokenize(text) {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().split(/\\s+/).filter(Boolean);
  }
  function _scoreTools(query) {
    var qt = _tokenize(query);
    if (!qt.length) return [];
    var scored = [];
    for (var i = 0; i < _TOOLS.length; i++) {
      var tool = _TOOLS[i];
      var nameTokens = _tokenize(tool.name);
      var descTokens = _tokenize(tool.description);
      var tagTokens = [].concat.apply([], (_TOOLS[i]._tags || []).map(_tokenize));
      var score = 0; var covered = 0;
      for (var j = 0; j < qt.length; j++) {
        var q = qt[j]; var ts = 0;
        if (nameTokens.indexOf(q) !== -1) ts += 10;
        else if (tool.name.toLowerCase().indexOf(q) !== -1) ts += 5;
        if (descTokens.indexOf(q) !== -1) ts += 2;
        else if (tool.description.toLowerCase().indexOf(q) !== -1) ts += 1;
        if (tagTokens.indexOf(q) !== -1) ts += 3;
        if (ts > 0) covered++;
        score += ts;
      }
      if (score > 0) {
        scored.push({ tool: tool, score: score * (0.5 + 0.5 * covered / qt.length) });
      }
    }
    return scored.sort(function(a, b) { return b.score - a.score; });
  }

  var _META_TOOLS = [
    {
      name: "search_tools",
      description: "Search available API tools by keyword. Returns up to 5 matching tools with full schemas. Use this before calling any tool.",
      inputSchema: { type: "object", properties: { query: { type: "string", description: "Keywords describing the operation (e.g. 'create customer', 'list payments')" } }, required: ["query"] }
    },
    {
      name: "call_tool",
      description: "Call a specific API tool by name with arguments. Use search_tools first to find the tool name and required arguments.",
      inputSchema: { type: "object", properties: { name: { type: "string", description: "Tool name from search_tools results" }, arguments: { type: "object", description: "Tool arguments matching the tool's inputSchema" } }, required: ["name"] }
    }
  ];`;

  const toolsListBody = `_send({ jsonrpc: "2.0", id: id, result: { tools: _META_TOOLS } });
    return Promise.resolve();`;

  const toolsCallBody = `var toolName = params && params.name;
    var args = (params && params.arguments) || {};
    if (toolName === "search_tools") {
      var query = args.query || "";
      var scored = _scoreTools(query);
      var top = scored.slice(0, 5);
      var result = {
        matches: top.map(function(s) { return { name: s.tool.name, description: s.tool.description, inputSchema: s.tool.inputSchema }; }),
        total_matched: scored.length
      };
      if (scored.length > 5) result.hint = "Refine your query to narrow results (" + scored.length + " matched).";
      _send({ jsonrpc: "2.0", id: id, result: { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] } });
      return Promise.resolve();
    }
    if (toolName === "call_tool") {
      toolName = args.name;
      args = args.arguments || {};
    }
    var tool = null;
    for (var i = 0; i < _TOOLS.length; i++) {
      if (_TOOLS[i].name === toolName) { tool = _TOOLS[i]; break; }
    }
    if (!tool) {
      _send({ jsonrpc: "2.0", id: id, error: { code: -32601, message: "Unknown tool: " + toolName } });
      return Promise.resolve();
    }
    return Promise.resolve(tool.call(args)).then(function(result) {
      _send({ jsonrpc: "2.0", id: id, result: { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] } });
    }).catch(function(e) {
      _send({ jsonrpc: "2.0", id: id, result: { content: [{ type: "text", text: "Error: " + (e instanceof Error ? e.message : String(e)) }], isError: true } });
    });`;

  return `${scorer}\n${generateMCPProtocol(serverName, version, toolsListBody, toolsCallBody)}`;
}

function toSlug(title: string): string {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}
