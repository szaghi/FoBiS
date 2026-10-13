# Querying the code

`fobis query` answers questions about a project's code from FoBiS's static analysis — the one behind `fobis lint`
— instead of a text search: a call on a continuation line, a statement after a `;`, a module variable renamed on
`use`, a type-bound call on an array element are all found, and comments, strings and inactive preprocessor
branches (the mode's `-D` flags) are not.

```bash
fobis query callers flux_hllc            # who calls it
fobis query writers solver::residual     # who changes this module variable, and how
fobis query region src/kernels.F90:212   # which OpenMP/OpenACC regions hold this line
fobis query device rho                   # where rho lives on the GPU
fobis query mpi collective               # every collective MPI call
fobis query interface split --json       # the header and dummies, for scripts and agents
```

For an agent, these are facts it does not have to guess: who else breaks when a procedure changes, whether a
variable is written inside a parallel region, what data a kernel needs on the device.

## Queries

| Query | Answers |
|-------|---------|
| `callers NAME` | call sites: `call`, function references, type-bound calls (`obj%run()`, `objs(i)%run()`) |
| `callees NAME` | what a procedure calls, with how each name was resolved |
| `uses MODULE` | the units that use it, with their only-lists |
| `writers VAR` | assignments, `read` input lists, `allocate`/`deallocate`, actual arguments of `intent(out)`/`intent(inout)` dummies |
| `readers VAR` | every other mention, and `intent(in)`/`intent(inout)` actual arguments |
| `defines NAME` | modules, procedures, generics, types, bindings, module variables, parameters |
| `region FILE:LINE` | the directive regions holding the line, with their clauses |
| `device VAR` | data directives naming it (`declare`, `enter/exit data`, `data`, `update`, `present`, map clauses) and compute constructs that use it without naming it |
| `mpi [ROUTINE\|KIND]` | MPI calls by kind: point-to-point, collective, one-sided, io, setup |
| `interface NAME` | the header and dummy declarations; a generic's specifics; the types binding a name |

`NAME` may be qualified (`module::procedure`, `module::host::internal`). `module::VAR` keeps the sites where the
name really is that module's variable — through host association, `use`, or a rename (`use m, only: local => var`):
each site says what the name is there (local, dummy with its intent, host, module variable, use).

How a call is resolved (`how`): `contained` (a procedure of the caller or its hosts), `unique` (the only project
procedure with that name), `generic` (every specific of the generic: the compiler chooses by the argument types; a
generic overloading an intrinsic lists the intrinsic too), `binding` (every procedure bound to that name in any
type: the dynamic type decides), `ambiguous` (several procedures with that name), `unresolved` (nothing in the
analysed sources: an external library, a dependency, an intrinsic). Callers reached through a generic or a binding
with several procedures are marked *candidate*.

## Real output

StringiFor (150 files), the procedures `split` calls and its interface:

```text
callees stringifor_string_t::split: 3 result(s)
src/lib/stringifor_string_t.F90:2928: unique_substring [function, contained] -> stringifor_string_t::unique_substring: uniq = unique_substring(raw=self%raw, substring=sep_)
src/lib/stringifor_string_t.F90:2929: count_substring [function, contained] -> stringifor_string_t::count_substring: No = count_substring(uniq, sep_)
src/lib/stringifor_string_t.F90:2946: index [function, generic] -> stringifor_string_t::sindex_character_string, stringifor_string_t::sindex_string_character, stringifor_string_t::sindex_string_string, intrinsic index: pos(t) = c - 1 + index(uniq(c:), sep_)
```

```text
interface split: 2 result(s)
src/lib/stringifor_string_t.F90:2859: stringifor_string_t::split
    pure subroutine split(self, tokens, sep, max_tokens)
    class(string), intent(in) :: self
    type(string), allocatable, intent(out) :: tokens(:)
    character(kind=ck,len=*), intent(in), optional :: sep
    integer, intent(in), optional :: max_tokens
binding string%split => split
```

`index(uniq(c:), sep_)` has character arguments, so it is the intrinsic: the analysis does not know argument types
and lists every candidate. `callers split` finds its 36 call sites, three of them on a subscripted object
(`call rows(r)%split(...)`).

**Checked against a large code.** On a private 251-file MPI + OpenACC application (2.1 s to analyse), 34 queries
— callers of subroutines and of type-bound procedures, uses of modules, MPI routines, definitions, writers of
module variables, callees, device residency — were compared with `grep` and, where they disagreed, by reading the
code: every disagreement was a site `grep` missed or misplaced (a call on a continuation line, a `use ::` form, an
assignment after a `;`, a directive line), none a wrong answer of the query.

## Limits

- Generics are not resolved on argument types, nor bindings on the dynamic type: those give candidates.
- Pointer aliasing and argument association (a variable written through a dummy of another name) are not
  followed; components (`obj%field`) are not variables for `writers`/`readers`.
- A name reaching a unit through a chain of modules (a module re-exporting another module's variable) is
  attributed to the module the unit uses.
- A statement that only the preprocessor can complete (a macro expanding to code) is seen as written.

`fobis query --json` gives every item (see [JSON output](/advanced/json-output#fobis-query-json)); the MCP server
exposes the queries as the `query` tool, read-only.
