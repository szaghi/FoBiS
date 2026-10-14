---
title: 4. Querying the code
---

# 4. Querying the code

Before changing a procedure you want to know who calls it; before changing a variable, who writes it. `grep` finds
the text; `fobis query` answers from the analysis of the code: calls resolved through generics, renames and
contained procedures, dummy arguments' intents, directive regions.

<<< @/examples/output/4-quality/04/callers.txt{console}

<<< @/examples/output/4-quality/04/defines.txt{console}

<<< @/examples/output/4-quality/04/interface.txt{console}

<<< @/examples/output/4-quality/04/writers.txt{console}

Which directive regions hold a line:

<<< @/examples/output/4-quality/04/region.txt{console}

Every MPI call, by kind:

<<< @/examples/output/4-quality/04/mpi.txt{console}

The other questions: `callees NAME`, `uses MODULE`, `readers VAR`, `device VAR` (where a variable lives on the
GPU). `--json` gives the same answers to scripts and agents.

::: tip What you learned
`fobis query KIND ARGUMENT`. Reference: [`query`](/reference/query).
:::

Next: [5. Verified modernisation](./05-modernize).
