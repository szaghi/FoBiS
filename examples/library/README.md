# FoBiS.py usage example on building a library

A KISS usage example of FoBiS.py

## Description

This example consists of a very simple library, _library.f90_ contained into _src_ directory. This library is a cumbersome module containing a classical _hello world_ procedure. The main module uses the module "nested_1" contained into "src/nested-1/first_dep.f90" file. The module "nested_1" has included the file "src/nested-1/nested-2/second_dep.f90". Two _fobos_ files are provided for building the example.

For testing the example type one of the followings

+ `FoBiS.py build -f fobos.static`;
+ `FoBiS.py build -f fobos.shared`.

It is worth noting that the module "nested_1" is contained into a file whose name if completely different from the module one (first_dep.f90) and that the inclusion of "second_dep.f90" is done without any paths neither absolute nor relative, i.e. "include 'second_dep.f90'", but FoBiS.f90 can automatically resolves such general dependencies.
