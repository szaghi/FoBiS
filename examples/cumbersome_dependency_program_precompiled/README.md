# FoBiS.py usage example on a cumbersome dependency program (with pre-compiled modules directly linked)

A KISS usage example of FoBiS.py

## Description

This example consists of a very simple program, _cumbersome.f90_ contained into _src_ directory. This program is a cumbersome version of a classical _hello world_. The main program uses the module "nested_1" contained into "src/nested-1/first_dep.f90" file. The module "nested_1" has included the file "src/nested-1/nested-2/second_dep.f90". The _fobos_ file defines has only the default mode.

For testing the example type one of the followings

+ `FoBiS.py clean`;
+ `FoBiS.py build`;

It is worth noting that the module "nested_1" is contained into a file whose name if completely different from the module one (first_dep.f90) and that the inclusion of "second_dep.f90" is done without any paths neither absolute nor relative, i.e. "include 'second_dep.f90'", but FoBiS.f90 can automatically resolves such general dependencies.

### What we learn from this example?

This example demonstrate how to build a program using a pre-compiled modules directly linked into the linking phase.  The tree of this example is
```bash
├── fobos
├── precompiled
│   ├── mod
│   │   └── nested_1.mod
│   └── obj
│       └── first_dep.o
├── README.md
└── src
    └── cumbersome.f90
```
The program `cumbersome.f90` depends on the compiled object `first_dep.o`. We want to directly link it with its full path. To this aim 2 fobos options are necessary
```ini
...
libs    = ./precompiled/obj/first_dep.o
include = ./precompiled/mod/
…
```
The `libs` option lists all the external libraries (compiled objects, `.o`, in the present case) that are directly passed (with the full path) to the linker. The `include` option list all the included directories search for including objects (module files, `.mod`, in this case).

It is worth noting that both the 2 above options can be directly passed as Command Line Arguments to FoBiS.py using the corresponding switches.
