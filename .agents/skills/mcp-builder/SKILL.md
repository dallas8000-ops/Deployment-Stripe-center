---
name: mcp-builder
description: >-
  Scaffolds MCP (Model Context Protocol) servers to connect Claude to external
  APIs, databases, or services. Use when building an integration between Claude
  and an external system — REST APIs, databases, file systems, third-party
  services. Triggers on: "build an MCP server", "connect Claude to X", "create
  an MCP tool for", "scaffold an integration", or any request to expose
  external data/actions as Claude tools.
metadata:
  short-description: Scaffold MCP servers for external API/database integrations

---

## What is MCP?

Model Context Protocol (MCP) lets Claude call tools exposed by a local or remote server. You build a server; Claude calls it. The server can wrap any API, database, filesystem, or service.

## Quickstart

```bash
# TypeScript (recommended)
npm create @modelcontextprotocol/server my-server
cd my-server && npm install

# Python
pip install mcp
```

## Minimal TypeScript MCP server

```ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const server = new McpServer({ name: "my-server", version: "1.0.0" });

server.tool(
  "tool_name",
  "One-line description of what this tool does",
  { param: z.string().describe("What this param is for") },
  async ({ param }) => ({
    content: [{ type: "text", text: `Result: ${param}` }],
  })
);

const transport = new StdioServerTransport();
await server.connect(transport);
```

## Scaffold process

1. **Identify the integration target** — REST API, database, filesystem, or service.
2. **List the tools** — each tool is one action (get, create, update, delete, search). Name tools as `verb_noun` (e.g., `get_user`, `list_orders`, `search_products`).
3. **Define input schemas with Zod** — be precise; Claude uses these to understand what to pass.
4. **Handle auth** — read credentials from environment variables, never hardcode.
5. **Return structured content** — `{ content: [{ type: "text", text: "..." }] }` for simple text; use `type: "resource"` for binary/large data.
6. **Register in Claude Code** — add to `~/.claude/settings.json` under `mcpServers`.

## Register in Claude Code settings

```json
{
  "mcpServers": {
    "my-server": {
      "command": "node",
      "args": ["path/to/my-server/build/index.js"],
      "env": {
        "API_KEY": "${MY_API_KEY}"
      }
    }
  }
}
```

## Common patterns

```ts
// Wrapping a REST API
const res = await fetch(`https://api.example.com/items/${id}`, {
  headers: { Authorization: `Bearer ${process.env.API_KEY}` }
});
const data = await res.json();
return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };

// Returning an error
return { content: [{ type: "text", text: `Error: ${err.message}` }], isError: true };

// Pagination
server.tool("list_items", "List items with pagination", 
  { page: z.number().default(1), limit: z.number().default(20) },
  async ({ page, limit }) => { /* ... */ }
);
```

## Rules

- Each tool must do exactly one thing — keep tools atomic and composable.
- Always validate inputs with Zod; never trust raw user input in shell commands or SQL.
- Use `process.env` for all secrets; document required env vars in a `.env.example`.
- Prefer `stdio` transport for local tools; use `http` (SSE) only for remote/shared servers.
- Test every tool with `mcp dev path/to/server.js` before registering.
