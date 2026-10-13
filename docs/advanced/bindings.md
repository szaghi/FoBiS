# C and Python bindings

A Fortran library is called from C, C++ or Python through `bind(c)` interfaces — which most Fortran code does not
have: its procedures take kinds like `real(R8P)`, assumed-shape arrays, generic names. `fobis bindings` writes
the missing layer from the analysis of the modules:

```bash
fobis bindings                 # every module of the mode's sources -> bindings/
fobis bindings m_morton -o c   # one module, into ./c
fobis bindings --print         # what would be bound, and why the rest is not; write nothing
```

Three files, named after the project (`--name`):

| File | What |
|------|------|
| `NAME_c.f90` | a module of `bind(c)` shims, one per bound procedure, named `<module>_<procedure>` |
| `NAME.h` | the C prototypes (`stdint.h` / `stdbool.h` types), each with the Fortran signature it calls |
| `NAME.py` | a `ctypes` wrapper: `load(path)` then one function per procedure taking numbers and lists |

Build the shims with the library (a shared library mode, or `gfortran -shared -fPIC sources... NAME_c.f90`).

## How a shim is written

- Every argument crosses as an interoperable type (`integer(c_int64_t)`, `real(c_double)`, `logical(c_bool)`),
  chosen from what the procedure's kind **resolves to** in the sources: `selected_int_kind(15)` -> 64-bit integer,
  `selected_real_kind(15, 307)` (PENF's `R8P`) -> `double`, `iso_fortran_env` and `iso_c_binding` names, literal
  kinds. Default kinds are taken as `int`, `float`, `double` — what gfortran, ifx and nvfortran use without
  `-i8`/`-r8`.
- The shim converts **explicitly** into temporaries declared with the procedure's own type spec
  (`x_f = real(x, R8P)`) and back (`intent(out)`/`inout`, results): the values are right whatever the kinds are.
- Assumed-shape arrays (`v(:)`) get an extent argument per dimension; explicit-shape arrays keep their extents
  (literal, or other dummy arguments); a function returning an array of literal shape returns it through an output
  argument.
- The specifics of a public generic are bound one by one; when a specific is private (the usual style: only
  `byte_size` public, its specifics private) the shim calls the generic, which resolves to that specific because
  the temporaries have the specific's own types.

**Not bound**, with the reason in the report: character and complex arguments, derived types, procedure arguments,
optional, allocatable and pointer dummies, assumed-size and assumed-rank arrays, kinds without a portable C type
(quad precision) or that cannot be resolved, array results whose shape is not literal, procedures already `bind(c)`.

## Real runs

**m_morton** (Morton codes, 8 public procedures): all 8 bound — fixed-shape arguments `ix(2)`, array results,
`int64 = selected_int_kind(15)`, an assumed-shape `list(:)`, a subroutine with an output array. Built with gfortran
into a shared library and called from C (gcc) and from Python:

```text
            Fortran          C                Python
from_ix2    147              147              147
to_ix2      5 9              5 9              [5, 9]
from_ix3    2239             2239             2239
to_ix3      3 7 11           3 7 11           [3, 7, 11]
bsearch     4                4                4
rank        2 4 3 1 5        2 4 3 1 5        [2, 4, 3, 1, 5]
```

**PENF** (170 public procedures and generic specifics): 15 bound (`digit`, `byte_size`, `bit_size` for each
kind, `check_endian`, `penf_init`, `get_memory_info`), the rest reported — 98 have allocatable arguments, 35
character ones, 17 optional ones, 5 use the 33-digit `R16P`. The first build failed: the specifics are private and
the shims called them by name; they now call the public generic. Python and Fortran give the same digits and sizes
(`digit(123456789012_I8P)` 12, `byte_size(1._R8P)` 8, `bit_size(1._R4P)` 32).

The MCP server's `bindings` tool reports what would be bound (read-only).
