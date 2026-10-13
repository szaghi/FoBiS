# MCP server

`fobis mcp` serves FoBiS to AI agents through the [Model Context Protocol](https://modelcontextprotocol.io).
An agent such as Claude Code can use FoBiS to lint the project and review a change, look up rules and the
knowledge packs, inspect the build, check the dependency graph, build and run the tests with their failures
diagnosed, analyse merge conflicts, collect the facts of a commit, start a test from a compiling skeleton, and see
the user's whole ecosystem of projects.

**What the agent gets are facts and grounded context, not FoBiS's own LLM answers.** The agent is a model
already: a local model answering for it would only be a weaker one. So the tools return what FoBiS computes
deterministically (findings, parsed compiler messages, diagnoses, crash facts, API changes) and the sources it
would ground an answer on, and the agent reasons on them. `ask`, `lint --deep`, the model part of `--explain`,
the `testgen` loop and commit-message generation stay command-line features.

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

Read-only tools (the project is not written):

| Tool | Returns | Arguments |
|------|---------|-----------|
| `lint` | [`fobis lint`](/ai/lint) findings as JSON; with `fix_diff`, the automatic fixes as a diff (nothing written) | `paths`, `select`, `ignore`, `mode`, `compiler_feedback`, `fix_diff`, `max_findings` |
| `review` | [Findings on the changed lines only](/ai/review): uncommitted, `staged`, or since `base` | `paths`, `staged`, `base`, `context`, `select`, `mode`, `max_findings` |
| `list_rules` | The lint rules: id, name, severity, default, summary | `prefix` |
| `explain_rule` | A rule's documentation, with its knowledge-pack references | `id` |
| `kb_search` | Sections of the [knowledge packs](/ai/knowledge-packs), with their resource URI | `query`, `k`, `packs` |
| `kb_show` | A knowledge-pack section, optionally with its neighbours | `id`, `context` |
| `ask_context` | The sections, and with `project` the procedures' facts, most relevant to a question, labelled S1..Sn; no answer | `question`, `project`, `packs`, `k` |
| `introspect` | Build facts: sources, compiler, dependencies, targets, include dirs, options | `mode`, `sections` |
| `check` | The module dependency graph checked without compiling: unresolved modules and includes | `mode` |
| `tree` | The inter-project dependency tree, each dependency with its version | `depth` |
| `merge_conflicts` | During a merge, rebase or cherry-pick: each conflict's base, ours and theirs (named correctly), the [deterministic resolution](/ai/merge-assist) when a rule applies, whether the file compiles | `paths`, `mode` |
| `commit_facts` | [Facts of the staged change](/advanced/commit): scope candidates, type hints, changed lines by kind, procedures | |
| `testgen_skeleton` | A [test skeleton](/ai/testgen) for a module that compiles, built in a scratch copy | `module`, `procedures`, `max`, `mode` |
| `ecosystem_status` | The [ecosystem](/advanced/ecosystem) dashboard: git, releases, CI, drift, pins (runs `git fetch`, queries GitHub) | `config` |
| `ecosystem_impact` | Which dependent projects a change of public interfaces breaks, and where | `project`, `base`, `config` |
| `query` | [Code-graph answers](/advanced/query): callers, callees, uses, writers, readers, defines, region, device, mpi, interface | `kind`, `argument`, `mode` |
| `agents_md` | [Project briefing](/advanced/agents-md): modes, commands, cases, kinds, parallelism, dependencies, and the AGENTS.md block | `mode` |
| `case_list` | The [cases](/advanced/cases) declared in the fobos and the quantities each produces | |
| `provenance` | What a result produced now depends on: commit, pins, compiler and flags, machine | `mode` |

Tools that write:

| Tool | Returns | Arguments |
|------|---------|-----------|
| `build` | `build --json`: on failure the parsed compiler messages and FoBiS's diagnoses (missing module, not linked, wrong runtime, duplicate symbol) | `mode`, `shadow`, `target` |
| `test` | `test --json`: each result with its status; a failed build with its diagnoses, a crash with its location, kind and FoBiS's notes (trusted location, debug mode, known compiler bugs) | `mode`, `shadow`, `suite`, `filter`, `list` |
| `case_run` | Build and run [cases](/advanced/cases): per run its status, quantities, output tails and provenance | `names`, `mode`, `shadow` |
| `verify` | [Cases compared with their references](/advanced/verify): per quantity pass/fail, errors, worst point, provenance changes; `repeat` checks non-determinism; never writes references | `names`, `mode`, `shadow`, `repeat` |
| `matrix` | [Every mode x shadow](/advanced/matrix) built, tested and verified: per cell status, compiler version, first problem, failed tests with crash facts, rechecks; quantities that disagree between cells. Slow: one full build per cell | `modes`, `shadows`, `compilers`, `verify`, `recheck` |
| `assess` | [Numerical error and uncertainty](/advanced/assess) from ensembles: digits per family, non-determinism, elasticities or correlations, observed order and extrapolation, budgets. Slow: one build per variant | `case`, `families`, `mode`, `samples`, `jobs` |
| `diff_run` | [The cases on a revision and on the working tree](/advanced/diff-run), in scratch copies: equivalent, or what differs and where, the procedures changed; `assess` judges a difference against the numerical spread | `ref`, `names`, `mode`, `assess` |
| `clean` | The removed objects and module files | `mode` |
| `fetch` | The dependencies cloned or updated (network) | `update` |

Every tool declares the protocol's behaviour **annotations**: `readOnlyHint` (false only for `build`, `test`,
`case_run`, `verify`, `matrix`, `assess`, `diff_run`, `clean`, `fetch`), `destructiveHint` (`clean`), `idempotentHint` (false for `fetch`) and `openWorldHint`
(`fetch` and `ecosystem_status`, which reach the network). Clients use them to decide what to ask the user before
a call; with Claude Code you approve each call unless you allow the tool.

Results are JSON (the same documents as the commands' [JSON output](/advanced/json-output)), sent as text and, with
protocol 2025-06-18, as `structuredContent`. A failed build or test is a **result**, not a tool error: its JSON
says `"status": "error"` and why. `lint` and `review` return at most `max_findings` findings (default 200), with a
`truncated` note.

## Resources

| URI | Content |
|-----|---------|
| `fobis://rules/{id}` | A lint rule's documentation (listed by `resources/list`) |
| `fobis://kb/{id}` | A knowledge-pack section, its id URL-encoded (a resource template; `kb_search` gives each result's URI) |

## How it works

The server speaks newline-delimited JSON-RPC 2.0 on standard input and output (protocol versions 2025-06-18,
2025-03-26 and 2024-11-05). Tools that read the fobos file or build run `fobis` as a subprocess in the project
directory with its JSON output, so nothing they print can corrupt the protocol stream; rules and knowledge packs
are answered in process. The server was checked with the official MCP Inspector (2.10.1, CLI mode): tool
listing, calls with structured content, resource listing, templates and reads.

## Relation to the Claude Code skill

The [FoBiS Claude Code skill](/guide/claude-skill) teaches an agent how to *use FoBiS* (fobos syntax,
commands, options). The MCP server lets the agent *run* FoBiS and reach the knowledge packs directly. They
complement each other: install both.
