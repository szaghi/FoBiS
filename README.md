# FoBiS.py
## FoBiS.py, Fortran Building System for poor men

A very stupid and simple tool for automatic building modern Fortran project

## Features
+ Automatic parsing of files dependency for _use_ and _include_ statements;
+ automatic building of all _programs_ found into the root directory parsed;
+ avoid unnecessary re-compilation (algorithm based on file-timestamp value).
