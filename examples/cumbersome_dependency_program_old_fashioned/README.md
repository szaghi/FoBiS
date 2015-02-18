# FoBiS.py usage example on a cumbersome dependency program

A KISS usage example of FoBiS.py

## Description

This example consists of a very simple program, _cumbersome.f90_ contained into _src_ directory. This program is a cumbersome version of a classical _hello world_. The main program call a subroutine defined into "src/nested-1/first_dep.f" file, that is an old fashioned Fortran fixed form file-library.

For testing the example type `FoBiS.py build`: this will firstly build the non-module old-fashioned library and then will build the main cumbersome program that will stored into `build/Cumbersome`.
