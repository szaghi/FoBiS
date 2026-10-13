# Asking questions

`fobis ask` answers questions about Fortran, OpenMP, OpenACC, MPI, HPC practice and your project from the
[knowledge packs](/ai/knowledge-packs) and, with `--project`, from the procedures of your sources. Every
statement of the answer cites the sections it comes from; a statement that cites nothing is dropped, and the
answer says so.

```bash
fobis ask "why does my MPI code hang when every rank sends first?"
fobis ask --project src "where is the halo exchange done and which MPI calls does it use?"
```

The answer has this shape (the wording depends on the model; the sources are the ones retrieved for this
question):

```text
- Standard-mode mpi_send may not return until the matching receive starts, so ranks that all send first can deadlock. [1]
- Exchange with mpi_sendrecv, or with non-blocking calls completed by mpi_waitall. [1][2]

Sources:
  [1] Cheatsheet — MPI 5.0 > Decision rules > Avoid deadlock - MPI 5.0: distilled reference  (mpi:cheatsheet#avoid-deadlock)
  [2] Chapter 3: Point-to-Point Communication > Code Examples - MPI 5.0: distilled reference  (mpi:ch03-point-to-point#code-examples)
```

Read a cited section in full with `fobis kb show <id>`.

## How an answer is built

1. **Retrieval, no model.** The question is matched against the packs as by `fobis kb search`. A question
   that names a programming model (`omp`, `!$acc`, `MPI_Isend` ...) is matched against that standard's pack
   and the general ones (Fortran standard, HPC practice, the project), so OpenMP and OpenACC sections do not
   compete on words they share. With `--project DIR`, each module and procedure of the sources in `DIR`
   becomes an entry: its header, arguments, used modules, calls, MPI calls, OpenMP/OpenACC directives and
   location.
2. **The model sees only those sections**, numbered, and must answer with claims that cite them. With the
   managed runtime and llama-server the citations are constrained by a JSON Schema: the model cannot cite a
   section it was not given.
3. **FoBiS checks every claim**: a claim that cites nothing or an unknown section is dropped (`--verbose`
   shows the dropped statements). When nothing is left, the answer is "the sources found do not answer this
   question", not an answer from the model's memory.

`--show-context` prints exactly what the model would receive (system prompt, question, sections) and stops,
without running a model: use it to see why an answer is what it is, or to check retrieval.

## Limits

Retrieval matches words, not meanings. When your wording differs from the packs' wording, the right section
may not be found, and the answer is "the sources found do not answer this question". For example the OpenMP
pack states the rule for loop variables as "predetermined attributes: loop iteration variables are private";
a question about "the index of a sequential loop" does not reach that section among the first ones. Rephrase
with the terms of the standard, raise `-k`, or look with `fobis kb search` first.

The answer is as good as the model: use `coder-7b` or larger (see [Local models](/ai/models)).

## Options

| Option | Description |
|--------|-------------|
| `QUESTION` | The question; `-` reads it from standard input |
| `--project DIR`, `-p DIR` | Also search the modules and procedures of the sources in `DIR` (repeatable) |
| `--pack NAME` | Search only this pack (repeatable) |
| `-k N` | Number of sections given to the model [default: 6] |
| `--show-context` | Print what the model would receive and stop (no model is run) |
| `--verbose` | Also print the statements dropped as uncited |
| `--json` | Claims with their source ids, dropped statements, sources; with `--show-context`, the retrieved sections only (label, id, title, text), no model |
| `--provider`, `--model`, `-m` | Override the configured LLM provider and model |
