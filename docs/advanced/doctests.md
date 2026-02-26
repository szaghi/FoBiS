# Doctests

FoBiS.py doctests let you write micro-unit-tests directly inside Fortran comment docstrings — no separate test harness needed. The idea is inspired by Python's `doctest` module.

## How it works

1. FoBiS.py scans source files for doctest snippets embedded in comments.
2. For each snippet, a *volatile* Fortran program is generated, compiled, and executed.
3. The program's standard output is compared to the expected result.
4. The volatile program is deleted after the test (unless `-keep_volatile_doctests` is set).

## Syntax

The delimiter character can be any character you use for FORD documentation (e.g. `<`, `!`). Using the same delimiter means doctests double as FORD code snippets.

```
!$```fortran
!$ <fortran code>
!$```
!=> <expected output> <<<
```

### Minimal example

```fortran
module simple
contains

  function add(a, b) result(c)
  !< Add two integers.
  !<```fortran
  !< print*, add(a=12, b=33)
  !<```
  !=> 45 <<<
  integer, intent(IN) :: a, b
  integer             :: c
  c = a + b
  end function add

  function sub(a, b) result(c)
  !< Subtract two integers.
  !<```fortran
  !< print*, sub(a=12, b=33)
  !<```
  !=> -21 <<<
  integer, intent(IN) :: a, b
  integer             :: c
  c = a - b
  end function sub

end module simple
```

### Complex test body

The doctest body can contain any valid Fortran: variable declarations, `use` statements, type definitions, etc.

```fortran
  function add(a, b) result(c)
  !< Add two integers.
  !<```fortran
  !< type :: foo
  !<   integer :: a(2)
  !< endtype foo
  !< type(foo) :: bar
  !< bar%a = 1
  !< print*, add(a=bar%a(2), b=bar%a(1))
  !<```
  !=> 2 <<<
```

### Multiple doctests per procedure

```fortran
  subroutine multiply(a, b, c)
  !<```fortran
  !< integer :: c
  !< call multiply(a=3, b=4, c=c)
  !< print*, c
  !<```
  !=> 12 <<<
  !<
  !<```fortran
  !< integer :: c
  !< call multiply(a=-2, b=16, c=c)
  !< print*, c
  !<```
  !=> -32 <<<
```

### Module-level doctests

Doctests can appear anywhere in a module, not just inside procedures:

```fortran
module simple
!< Simple module.
!<### Regression tests
!<```fortran
!< print*, add(a=12, b=33)
!<```
!=> 45 <<<
contains
  ...
end module simple
```

## Running doctests

```bash
# Run all doctests found in the source tree
FoBiS.py doctests

# Keep volatile programs for inspection
FoBiS.py doctests -keep_volatile_doctests

# Store build output in ./build/
FoBiS.py doctests -dbld ./build/

# Use a fobos mode
FoBiS.py doctests -f project.fobos -mode gnu
```

## Output

```
executing doctest simple-doctest-1
doctest failed!
  result obtained: "45"
  result expected: "40"
executing doctest simple-doctest-2
doctest passed
```

## Volatile program structure

With `-keep_volatile_doctests` and `-dbld ./build/`, the generated structure looks like:

```
build/
├── doctests-src/
│   └── simple.f90/
│       ├── simple-doctest-1.f90
│       ├── simple-doctest-1.result
│       ├── simple-doctest-2.f90
│       └── simple-doctest-2.result
├── simple-doctest-1    ← compiled executable
├── simple-doctest-2
├── mod/
│   └── simple.mod
└── obj/
    ├── simple.o
    ├── simple-doctest-1.o
    └── simple-doctest-2.o
```

## Limitations

1. **Output via stdout only** — the test result must be `print*`-ed; FoBiS.py captures only standard output.
2. **Public objects only** — only `public` procedures and types from `module` units can be doc-tested. Private symbols are inaccessible to the generated test programs.

## Command reference

See [`doctests` command](/reference/doctests) for the full option reference.
