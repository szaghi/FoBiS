# FoBiS.py usage example on a cumbersome dependency program (with external interdependency project/fobos)

A KISS usage example of FoBiS.py

## Description

This example consists of a very simple program, _cumbersome.f90_ contained into _src_ directory. This program is a cumbersome version of a classical _hello world_. The main program depends on an external library contained into `dependency_lib`. The building of the main program depends on the up-to-date status of the dependency library.

For testing the example type one of the followings

+ `FoBiS.py clean`;
+ `FoBiS.py build`;

### What we learn from this example?
This example demonstrates how to set an interdependent *project*, meaning a project that *depends on* another by means of its fobos file.
```bash
├── fobos
├── dependency_lib
    └── fobos_lib
├── README.md
└── src
    └── cumbersome.f90
```
The building of the main program depends on the up-to-date status of the dependency library. To establish this interdependency use the `dependon` option
```ini
...
dependon = ./dependency_lib/fobos_lib:static
...
```
For more details on the `dependon` syntax see the [wiki](https://github.com/szaghi/FoBiS/wiki/Autorebuild-with-interdependent-projects).

It is worth noting that both the above option can be directly passed as Command Line Arguments to FoBiS.py using the corresponding switch.
