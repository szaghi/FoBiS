# FoBiS.py usage example on a cumbersome dependency program

A KISS usage example of FoBiS.py

## Description

This example consists of a very simple program, _cumbersome.f90_ contained into _src_ directory. This program is a cumbersome version of a classical _hello world_. The main program uses the module "nested_1" contained into "src/nested-1/first_dep.f90" file. The module "nested_1" has included the file "src/nested-1/nested-2/second_dep.f90". Five _fobos_ files are provided for building the example. The _fobos_ file defines 3 modes, _gnu_, _intel_ and _custom_ while the other four fobos files define each one only one default mode, _custom_, _g95_, _gnu_ and _intel_, respectively.

For testing the example type one of the followings

+ `FoBiS.py build -mode gnu` or `FoBiS.py build -mode custom` using modes defined into _fobos_ file;
+ `FoBiS.py build -f fobos.custom` using custom-complier-configuration file;
+ `FoBiS.py build -f fobos.g95` using g95-complier-configuration file;
+ `FoBiS.py build -f fobos.gnu` using gnu-complier-configuration file;
+ `FoBiS.py build -f fobos.intel` using intel-complier-configuration file.

It is worth noting that the module "nested_1" is contained into a file whose name if completely different from the module one (first_dep.f90) and that the inclusion of "second_dep.f90" is done without any paths neither absolute nor relative, i.e. "include 'second_dep.f90'", but FoBiS.f90 can automatically resolves such general dependencies.
