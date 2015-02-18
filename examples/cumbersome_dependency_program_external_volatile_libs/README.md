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
│   ├── first_dep.a
│   └── nested_1.mod
├── README.md
└── src
    └── cumbersome.f90
```
The program `cumbersome.f90` depends on the library `first_dep.a`.

```ini
...
vlibs   = ./lib/first_dep
include = ./lib/
...
```
The `vlibs` option lists all the external libraries (compiled objects, `.a`, in the present case) that are passed to the linker via full path. The `include` option list all the included directories search for including objects (module files, `.mod`, in this case). The library is indicated as *volatile*: this means that it assumed that it can change *imminently*, thus its changes must trigger a re-building of the program. To track this changes (triggering a re-building) FoBiS.py tracks the `md5sum` hash of each volatile library. These hashes are saved into the root build directory and named as `.libraryname.md5` (hidden files, in this example `.first_dep.a.md5`). When FoBiS.py is executed in building mode the hashes of volatile libraries are checked against the actual `md5sum` of the libraries (computed on-the-fly) and if they differ a rebuild is triggered and the new hashes saved for the future buildings.

To trigger a re-building there is a rule into the provided fobos file
```bash
FoBiS.py rule -ex triggering
```
This will build the example 2 times: first with `first_dep.a.1` and then with `first_dep.a.2` that is slightly different from the first. The md5sum hash changes between the 2 building thus FoBiS.py should be triggered to recompile all (`cumbersome.f90` in this case) and you should see something like
```bash
...
The volatile library ./lib/first_dep.a is changed with respect the last building: forcing to (re-)compile all
...
```

It is worth noting that both the 3 above options can be directly passed as Command Line Arguments to FoBiS.py using the corresponding switches.
