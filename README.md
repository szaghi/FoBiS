# FoBiS.py
### FoBiS.py, Fortran Building System for poor men

A very simple and stupid tool for automatic building modern Fortran project.

## Why?

GNU Make, CMake, SCons & Co. are fantastic tools, even too much for a _poor-fortran-man_.
However, the support for modern Fortran project is still poor: in particular, it is quite difficult (and boring) to track the inter-module-dependency hierarchy of project using many module files.
Modern Fortran programs can take great advantages of module using, however their compilations can become quickly a nightmare as the number of module grows. As consequence, an automatic building system able to track (on the fly) any changes on the inter-module-dependency hierarchy can save the life of a _poor-fortran-man_.

## Why not use an auto-make-like tool?

There are a lot of alternatives for deal with inter-module-dependency hierarchy, but they can be viewed as a pre-processor for the actual building system (such as auto-make tools or even the Fortran compiler itself that, in most cases, can generate a dependency list of a processed file), thus they introduce another level of complexity... but a _poor-fortran-man_ always loves the KISS (Keep It Simple, Stupid) things! FoBiS.py is designed to do just one thing: build a modern Fortran program without boring you to specify a particular compilation hierarchy.

## Features
+ Automatic parsing of files for dependency-hierarchy creation in case of _use_ and _include_ statements;
+ automatic building of all _programs_ found into the root directory parsed;
+ avoid unnecessary re-compilation (algorithm based on file-timestamp value);
+ simple command line interface;
+ Intel and GNU Fortran Compilers support;
+ configuration-files-free.

## Todos
+ Add support for Fortran projects using non-module-contained libraries (a little modification to the present FoBiS.py, but I do not use such a bad-programming-style, thus this feature will be implemented only is someone ask to do);
+ add pre-processing switches support to the CLI;
+ add support for libraries;
+ add support for configuration file (for complex building-configurations);
+ add MPI and OpenMP support;
+ add IBM, PGI, g95 Fortran Compilers support;
+ ...

## Usage

Printing the main help message:

      FoBiS.py -h

This will echo:

      usage: FoBiS.py [-h] [-v] {build,clean} ...

      FoBiS.py, Fortran Building System for poor men

      optional arguments:
        -h, --help     show this help message and exit
        -v, --version  Show version

      Commands:
        Valid commands

        {build,clean}
          build        Build all programs found or a specific target
          clean        Clean project: completely remove DOBJ and DMOD directories...
                       use carefully

Printing the _build_ help message:

      FoBiS.py build -h

This will echo:

      usage: FoBiS.py build [-h] [-target TARGET] [-compiler COMPILER]
                      [-cflags CFLAGS] [-lflags LFLAGS]
                      [-libs LIBS [LIBS ...]] [-dobj DOBJ] [-dmod DMOD]
                      [-dexe DEXE] -src SRC

      optional arguments:
        -h, --help            show this help message and exit
        -target TARGET        Build a specific file [default: all programs found]
        -compiler COMPILER    Compiler used: Intel, GNU, IBM, PGI or g95 [default:
                              Intel]
        -cflags CFLAGS        Compilation flags [default: -c -cpp]
        -lflags LFLAGS        Linking flags
        -libs LIBS [LIBS ...]
                              List of external libraries used
        -dobj DOBJ            Directory containing compiled objects [default:
                              ./obj/]
        -dmod DMOD            Directory containing .mod files of compiled objects
                              [default: ./mod/]
        -dexe DEXE            Directory containing executable objects [default: ./]
        -src SRC              Root-directory of source files

Printing the _clean_ help message:

      FoBiS.py clean -h

This will echo:

      usage: FoBiS.py clean [-h] [-dobj DOBJ] [-dmod DMOD]

      optional arguments:
        -h, --help  show this help message and exit
        -dobj DOBJ  Directory containing compiled objects [default: ./obj/]
        -dmod DMOD  Directory containing .mod files of compiled objects [default:
                    ./mod/]

### Compile all programs found

      FoBiS.py bluid -src my_path

FoBiS.py will recursively search for _program_ files into the directories nested into "my\_path". Program files are captured parsing each file found: a file is a _program-file_ if it contains the Fortran statement _program_.
It is worth noting that the above FoBiS.py call will use the default compilations options.

### Compile a specific target

      FoBiS.py bluid -src my_path -target my_path/my_sub_path/foo.f90

FoBiS.py will recursively search for "my_path/my_sub_path/foo.f90" and for all its dependency files into the directories nested into "my\_path". FoBiS.py will (re-)compile only _foo.f90_ file (independently if it is a program-file or not) and all its dependencies if necessary.

### Compile a specific target with user-defined flags

      FoBiS.py bluid -cflags '-c -cpp -O2' -src my_path -target my_path/my_sub_path/foo.f90

### Clean project tree

      FoBiS.py clean
