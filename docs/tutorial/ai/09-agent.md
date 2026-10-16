---
title: 9. An agent under the gate
---

# 9. An agent under the gate

The previous chapters used a model inside FoBiS. An agent (Claude Code, Codex, any client of the Model Context
Protocol) works the other way round: the agent is the model, and FoBiS is a tool it calls. `fobis mcp` serves
FoBiS's facts and checks over MCP:

```bash
claude mcp add fobis -- fobis mcp       # Claude Code; other clients take the same command
```

A minimal client, in Python, speaks the protocol the way an agent does, one JSON-RPC request per line:

::: details tools/mcp_client.py
<<< @/examples/tutorial/6-ai/09-agent/files/tools/mcp_client.py{python}
:::

<<< @/examples/output/6-ai/09/tools.txt{console}

The read-only tools give facts: where `simpson` is called, from the code graph rather than a text search:

<<< @/examples/output/6-ai/09/callers.txt{console}

## The agent's edit

The agent "simplifies" Simpson's even-node loop, and gets the bound wrong:

<<< @/examples/output/6-ai/09/edit.txt{console}

Before it says it is done, it calls the gate:

<<< @/examples/output/6-ai/09/gate.txt{console}

The build passes and the test fails, with the location: `test_exactness.F90:10`, Simpson's rule on a cubic. The
reference of `area` passes: the bug adds `2 f(b)` to the sum, and for `sin(x)` on `[0, pi]` `f(b) = sin(pi)` is
zero to rounding. One check rarely sees everything; the gate runs all of them and the agent gets the first
failing fact.

`fobis agents-md` (track 4) writes the project's facts into `AGENTS.md`, so the agent knows the modes, the cases
and the commands before it starts.

::: tip What you learned
`fobis mcp`, the read-only and the writing tools, an agent calling `gate`. Reference: [MCP server](/cookbook/ai-setup#an-mcp-server-for-your-agent),
[the gate](/cookbook/verification#one-command-for-all-of-it).
:::

This is the end of the tutorials. The [guides](/cookbook/) and the [reference](/reference/build) cover every
command and option.
