# FoBiS.py usage example on a cumbersome dependency program (with external volatile library linked via linker paths-extended)

A KISS usage example of FoBiS.py

## Description

This example consists of a very simple program, _cumbersome.f90_ contained into _src_ directory. This program is a cumbersome version of a classical _hello world_. The main program uses the module "nested_1" contained into `first_dep.a`.

For testing the example type one of the followings

+ `FoBiS.py clean`;
+ `FoBiS.py build`;

### What we learn from this example?
This example demonstrates how to build a program using an external library linked via extending the linker search-paths.  The tree of this example is
```bash
├── fobos
├── lib
│   ├── libfirst_dep.a
│   └── nested_1.mod
├── README.md
└── src
    └── cumbersome.f90
```
The program `cumbersome.f90` depends on the library `first_dep.a`. Note that all the external libraries that are liked without the full path must have the prefix `lib`, thus the actual name of the library is `libfirst_dep.a`. The linker must be aware of the new path for searching external libraries. To this aim 3 fobos options are necessary

```ini
...
ext_libs = first_dep
lib_dir  = ./lib/
include  = ./lib/
...
```
The `ext_libs` option lists all the external libraries (compiled objects, `.a`, in the present case) that are passed to the linker via `-l` switch. The `lib_dir` option lists all the directories where the linker must search for linked libraries: this extends the linker path via `-L` switch. The `include` option list all the included directories search for including objects (module files, `.mod`, in this case).

It is worth noting that both the 3 above options can be directly passed as Command Line Arguments to FoBiS.py using the corresponding switches.
