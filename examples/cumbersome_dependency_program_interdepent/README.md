# FoBiS.py usage example on a cumbersome dependency program (with external interdependency projects)

A KISS usage example of FoBiS.py

## Description

This example consists of a very simple program, _cumbersome.f90_ contained into _src_ directory. This program is a cumbersome version of a classical _hello world_. The main program depends on 3 external libraries contained into `dependency_lib_1`, `dependency_lib_2` and `dependency_lib_3`. The building of the main program depends on the up-to-date status of the dependency libraries.

For testing the example type one of the followings

+ `FoBiS.py clean`;
+ `FoBiS.py build`;

### What we learn from this example?
This example demonstrates how to set-up an interdependent *project*, meaning a project that *depends on* others (by means of thier fobos files).

Our example has the following structure
```bash
├── dependency_lib_1
│   ├── fobos_lib
│   └── src
├── dependency_lib_2
│   ├── fobos_lib
│   └── src
├── dependency_lib_3
│   ├── fobos_lib
│   └── src
├── fobos
├── README.md
└── src
    └── cumbersome.f90
```
The building of the main program depends on the up-to-date status of the dependency libraries. To establish this interdependency we use the `dependon` option
```ini
...
dependon = ./dependency_lib_1/fobos_lib:static((direct))
           ./dependency_lib_2/fobos_lib:static((Indirect))
           ./dependency_lib_3/fobos_lib
...
```
Note that the buildings of dependencies are done following the sequence of their definition. For more details on the `dependon` syntax see the [wiki](https://github.com/szaghi/FoBiS/wiki/Autorebuild-with-interdependent-projects).

Once the `dependon` options has been set, the building of the main program automatically checks the others 3 buildings status producing an output similar to:

```bash
FoBiS.py build

Building dependency fobos_lib into ./dependency_lib_1 with mode static
Builder options
  Building directory:                       build/
  Compiled-objects .o   directory:          build/obj/
  Compiled-objects .mod directory:          build/mod/
  Included paths:                           src/nested-1/nested-2
  Compiler class:                           Gnu
  Compiler:                                 gfortran
  Compiler module switch:                   -J
  Compilation flags:                        -c
  Linking     flags:
  Preprocessing flags:
  PreForM.py used:                          False
  PreForM.py output directory:              None
  PreForM.py extensions processed:          []

Building src/library.f90
Nothing to compile, all objects are up-to-date
Linking build/libdep1.a
Target src/library.f90 has been successfully built

Building dependency fobos_lib into ./dependency_lib_2 with mode static
Builder options
  Building directory:                       build/
  Compiled-objects .o   directory:          build/obj/
  Compiled-objects .mod directory:          build/mod/
  Compiler class:                           Gnu
  Compiler:                                 gfortran
  Compiler module switch:                   -J
  Compilation flags:                        -c
  Linking     flags:
  Preprocessing flags:
  PreForM.py used:                          False
  PreForM.py output directory:              None
  PreForM.py extensions processed:          []

Building src/library.f90
Nothing to compile, all objects are up-to-date
Linking build/libdep2.a
Target src/library.f90 has been successfully built

Building dependency fobos_lib into ./dependency_lib_3 with default mode
Builder options
  Building directory:                       build/
  Compiled-objects .o   directory:          build/obj/
  Compiled-objects .mod directory:          build/mod/
  Compiler class:                           Gnu
  Compiler:                                 gfortran
  Compiler module switch:                   -J
  Compilation flags:                        -c
  Linking     flags:
  Preprocessing flags:
  PreForM.py used:                          False
  PreForM.py output directory:              None
  PreForM.py extensions processed:          []

Building src/library.f90
Nothing to compile, all objects are up-to-date
Linking build/libdep3.a
Target src/library.f90 has been successfully built

The following auxiliary paths have been added
Include files search paths (include):
- dependency_lib_1/build/mod/
- dependency_lib_2/build/mod/
- dependency_lib_3/build/mod/
Libraries search paths (lib_dir):
- dependency_lib_2/build/
Libraries paths:
- (libs) dependency_lib_1/build/libdep1.a
- (ext_libs) dep2
- (libs) dependency_lib_3/build/libdep3.a
Builder options
  Building directory:                       build/
  Compiled-objects .o   directory:          build/obj/
  Compiled-objects .mod directory:          build/mod/
  External libraries directories:           dependency_lib_2/build/
  Included paths:                           dependency_lib_1/build/mod/ dependency_lib_2/build/mod/ dependency_lib_3/build/mod/
  Linked libraries with full path:          dependency_lib_1/build/libdep1.a dependency_lib_3/build/libdep3.a
  Linked libraries in path:                 dep2
  Compiler class:                           Gnu
  Compiler:                                 gfortran
  Compiler module switch:                   -J
  Compilation flags:                        -c
  Linking     flags:
  Preprocessing flags:
  PreForM.py used:                          False
  PreForM.py output directory:              None
  PreForM.py extensions processed:          []

Building src/cumbersome.f90
Nothing to compile, all objects are up-to-date
Linking build/Cumbersome
Target src/cumbersome.f90 has been successfully built
```

Note that the using the `dependon` option the dependency libraries are automatically added to linking-phase dependencies of the main program, thus the user is no longer obligated to explicitly define them.

It is worth noting that both the above option can be directly passed as Command Line Arguments to FoBiS.py using the corresponding switch.

### Screencast

![Screencast](cumbersome-cast.gif)
