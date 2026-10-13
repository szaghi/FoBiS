# `query` command

Answer a question about the code from the static analysis of the mode's sources. Guide:
[Querying the code](/advanced/query).

```bash
fobis query KIND [ARGUMENT] [options]
```

| Kind | Argument | Answer |
|------|----------|--------|
| `callers` | `NAME` or `module::NAME` | call sites of a procedure (calls, function references, type-bound calls) |
| `callees` | `NAME` or `module::NAME` | what a procedure calls, resolved, candidate or unresolved |
| `uses` | `MODULE` | the units that use it, with their only-lists |
| `writers` | `VAR` or `module::VAR` | assignments, `read`, `allocate`, actual arguments of `intent(out/inout)` dummies |
| `readers` | `VAR` or `module::VAR` | every other mention, and `intent(in/inout)` actual arguments |
| `defines` | `NAME` | modules, procedures, generics, types, bindings, module variables and parameters |
| `region` | `FILE:LINE` | the OpenMP/OpenACC regions holding the line, with their clauses |
| `device` | `VAR` | data directives naming it, compute constructs using it without naming it |
| `mpi` | `ROUTINE` or kind (optional) | MPI calls by kind: point-to-point, collective, one-sided, io, setup |
| `interface` | `NAME` | header and dummy declarations; generic specifics; type bindings |

| Option | Description |
|--------|-------------|
| `--mode M` | The mode whose sources and `-D` defines are analysed |
| `--src DIR` | Sources to analyse when there is no fobos |
| `--json` | One JSON object: `kind`, `argument`, `items`, `notes`, `files` (see [JSON output](/advanced/json-output#fobis-query-json)) |
| `-f/--fobos`, `--fci` | The fobos file |

Exit code 0, or 2 for an unknown kind or a bad argument.
