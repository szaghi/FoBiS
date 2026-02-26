# Examples

Worked examples demonstrating FoBiS.py features from simple to advanced.

## Examples in this section

| Example | What it shows |
|---|---|
| [Basic Build](/examples/basic) | Auto-discovery, module dependency resolution, custom directories |
| [Library](/examples/library) | Building static and shared Fortran libraries |
| [Interdependent Projects](/examples/interdependent) | Auto-rebuilding dependent libraries with `-dependon` |
| [PreForM Preprocessing](/examples/preform) | Template preprocessing with PreForM.py |

## Structure of each example

Each example follows the same pattern:

1. **Source tree** — the Fortran files involved
2. **Build** — how to invoke FoBiS.py
3. **fobos** — the equivalent fobos file
4. **Result** — what gets built and where

## The *cumbersome* example

Most examples use a deliberately contrived Fortran project called `cumbersome`. It represents a typical project with multiple levels of module and include dependencies:

```
src/
├── cumbersome.f90        ← main program, uses module nested_1
└── nested-1/
    ├── first_dep.f90     ← defines module nested_1, includes second_dep.inc
    └── nested-2/
        └── second_dep.inc
```

The sources:

```fortran
! cumbersome.f90
program cumbersome
  use nested_1
  implicit none
  call print_hello_world
end program cumbersome
```

```fortran
! nested-1/first_dep.f90
module nested_1
  include 'second_dep.inc'
end module nested_1
```

```fortran
! nested-1/nested-2/second_dep.inc
implicit none
character(len=12), parameter :: hello_world = 'Hello World!'
contains
  subroutine print_hello_world()
    print "(A)", hello_world
  end subroutine
```

Building this manually requires compiling `second_dep.inc` (via include), then `first_dep.f90`, then linking `cumbersome.f90` — in exactly that order. FoBiS.py resolves this hierarchy automatically.
