# MCP server

`fobis mcp` serves FoBiS to AI agents through the [Model Context Protocol](https://modelcontextprotocol.io):
an agent such as Claude Code can lint the project, read why a rule matters, search the knowledge packs,
inspect the build configuration, check the dependency graph, build and run the tests, all through FoBiS.
FoBiS runs no language model for this: the agent brings its own.

## Setup

Claude Code, for the current project:

```bash
claude mcp add fobis -- fobis mcp
```

Any MCP client that launches stdio servers: the command is `fobis mcp` (or `python3 fobis.pyz mcp` with the
standalone archive), started in the project directory or given `--root <project>`. In a JSON client
configuration:

```json
{
  "mcpServers": {
    "fobis": { "command": "fobis", "args": ["mcp", "--root", "/path/to/project"] }
  }
}
```

## Tools

| Tool | Does | Arguments |
|------|------|-----------|
| `lint` | Run [`fobis lint`](/ai/lint); findings as JSON | `paths`, `select`, `ignore`, `mode`, `compiler_feedback` |
| `list_rules` | Every lint rule: id, name, severity, default, summary | |
| `explain_rule` | A rule's documentation, with its knowledge-pack references | `id` |
| `kb_search` | Search the [knowledge packs](/ai/knowledge-packs) | `query`, `k`, `packs` |
| `kb_show` | A knowledge-pack section, optionally with its neighbours | `id`, `context` |
| `introspect` | Build facts as JSON: sources, compiler, dependencies, targets, include dirs, options | `mode`, `sections` |
| `check` | Validate the module dependency graph without compiling | `mode` |
| `build` | Build the project | `mode` |
| `test` | Discover, build and run the tests, or only list them | `mode`, `suite`, `filter`, `list` |

The agent decides when to call a tool; with Claude Code you approve each call unless you allow the tool.
`build` and `test` compile and run code in the project, as the same commands do from the terminal.

## How it works

The server speaks newline-delimited JSON-RPC 2.0 on standard input and output (protocol versions
2025-06-18, 2025-03-26 and 2024-11-05). Tools that read the fobos file or build (`lint`, `introspect`,
`check`, `build`, `test`) run `fobis` as a subprocess in the project directory and return its output, so
nothing they print can corrupt the protocol stream; rules and knowledge packs are answered in process.
Outputs longer than 60 000 characters are truncated, with a note.

## Relation to the Claude Code skill

The [FoBiS Claude Code skill](/guide/claude-skill) teaches an agent how to *use FoBiS* (fobos syntax,
commands, options). The MCP server lets the agent *run* FoBiS and reach the knowledge packs directly. They
complement each other: install both.
