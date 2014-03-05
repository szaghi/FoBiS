# FoBiS.py
### FoBiS.py, Fortran Building System for poor men

A very simple and stupid tool for automatic building modern Fortran project.

## Why?

GNU Make, CMake, SCons & Co. are fantastic tools, even too much for a _poor-fortran-man_.
However, the support for modern Fortran project is still poor: in particular, it is quite difficult (and boring) to track the inter-module-dependency hierarchy of project using many module files.
Modern Fortran programs can take great advantages of module using, however their compilations can become quickly a nightmare as the number of modules grows. As consequence, an automatic building system able to track (on the fly) any changes on the inter-module-dependency hierarchy can save the life of a _poor-fortran-man_.

## Why not use an auto-make-like tool?

There are a lot of alternatives for deal with inter-module-dependency hierarchy, but they can be viewed as a pre-processor for the actual building system (such as auto-make tools or even the Fortran compiler itself that, in most cases, can generate a dependency list of a processed file), thus they introduce another level of complexity... but a _poor-fortran-man_ always loves the KISS (Keep It Simple, Stupid) things! FoBiS.py is designed to do just one thing: build a modern Fortran program without boring you to specify a particular compilation hierarchy.

## OK, what can FoBiS.py do? I am a _poor-fortran-man_, I do not understand you...

Suppose you have a Fortran project composed of many Fortran modules placed into a complicated nested directories tree. Your goal is to build some (all) of the main programs contained into the project tree, but you have no time (or patience) to write the complicated makefile(s) able to correctly build your programs. In this case FoBiS.py can save your life: just type _python FoBiS.py build_ into the root of your project and FoBis.py will (try to) build all the main programs nested into the current directory. Obviously, FoBiS.py will not (re-)compile unnecessary objects if they are up-to-date (like the "magic" of a makefile). FoBiS.py have many (ok... some) others interesting features: if I have convinced you, please read the following.

## Features
+ Automatic parsing of files for dependency-hierarchy creation in case of _use_ and _include_ statements;
+ automatic building of all _programs_ found into the root directory parsed or only a specific selected target;
+ avoid unnecessary re-compilation (algorithm based on file-timestamp value);
+ simple command line interface;
+ Intel and GNU Fortran Compilers support;
+ configuration-files-free;
+ ... but also configuration-file driven building for complex buildings;
+ easy-extensible: FoBis.py is just a less-than 500 lines of Python statements... no bad for a poor-make-replacement;
+ ...

## Todos
+ Add support for building libraries;
+ add IBM, PGI, g95 Fortran Compilers support;
+ ...
+ GUI... nooooooooooo, we are _poor-fortran-men_!
+ ...
+ pythonic pre-processor;
+ ...

## Requirements
+ Python 2.7+;
+ a lot of patience with the author.

FoBiS.py is developed on a GNU/Linux architecture, and it has been tested also on AIX one. For Windows architecture there is no support, however it should be work out-of-the-box.

## Copyrights

FoBiS.py is an open source project, it is distributed under the [GPL v3](http://www.gnu.org/licenses/gpl-3.0.html). Anyone is interest to use, to develop or to contribute to FoBiS.py is welcome.

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

      usage: FoBiS.py build [-h] [-f F] [-colors] [-log] [-quiet]
                            [-exclude EXCLUDE [EXCLUDE ...]] [-target TARGET]
                            [-compiler COMPILER] [-fc FC] [-modsw MODSW] [-mpi]
                            [-cflags CFLAGS] [-lflags LFLAGS]
                            [-libs LIBS [LIBS ...]] [-I I [I ...]] [-dobj DOBJ]
                            [-dmod DMOD] [-dexe DEXE] [-src SRC]

      optional arguments:
        -h, --help            show this help message and exit
        -f F                  Specify a "fobos" file named differently from "fobos"
        -colors               Activate colors in shell prints [default: no colors]
        -log                  Activate the creation of a log file [default: no log
                              file]
        -quiet                Less verbose than default
        -exclude EXCLUDE [EXCLUDE ...]
                              Exclude a list of files from the building process
        -target TARGET        Build a specific file [default: all programs found]
        -compiler COMPILER    Compiler used: Intel, GNU, IBM, PGI, g95 or Custom
                              [default: Intel]
        -fc FC                Specify the Fortran compiler statement, necessary for
                              custom compiler specification (-compiler Custom)
        -modsw MODSW          Specify the switch for specifing the module searching
                              path, necessary for custom compiler specification
                              (-compiler Custom)
        -mpi                  Use MPI enabled version of compiler
        -cflags CFLAGS        Compilation flags [default: -c -cpp]
        -lflags LFLAGS        Linking flags
        -libs LIBS [LIBS ...]
                              List of external libraries used
        -I I [I ...]          List of directories for searching included files
        -dobj DOBJ            Directory containing compiled objects [default:
                              ./obj/]
        -dmod DMOD            Directory containing .mod files of compiled objects
                              [default: ./mod/]
        -dexe DEXE            Directory containing executable objects [default: ./]
        -src SRC              Root-directory of source files [default: ./]

Printing the _clean_ help message:

      FoBiS.py clean -h

This will echo:

      usage: FoBiS.py clean [-h] [-f F] [-colors] [-dobj DOBJ] [-dmod DMOD]

      optional arguments:
        -h, --help  show this help message and exit
        -f F        Specify a "fobos" file named differently from "fobos"
        -colors     Activate colors in shell prints [default: no colors]
        -dobj DOBJ  Directory containing compiled objects [default: ./obj/]
        -dmod DMOD  Directory containing .mod files of compiled objects [default:
                    ./mod/]

### Compile all programs found

      FoBiS.py bluid

FoBiS.py will recursively search for _program_ files into the directories nested into "./". Program files are captured parsing each file found: a file is a _program-file_ if it contains the Fortran statement _program_.
It is worth noting that the above FoBiS.py call will use the default compilations options.

### Compile all programs found excluding some files

      FoBiS.py bluid -exclude foo.f90 bar.f

FoBiS.py will recursively search for _program_ files into the directories nested into "./" and, excluding _foo,f90_ and _bar.f_, all other files will be parsed and, in case, built.

### Compile a specific target

      FoBiS.py bluid -src my_path -target my_path/my_sub_path/foo.f90

FoBiS.py will recursively search for "my_path/my_sub_path/foo.f90" and for all its dependency files into the directories nested into "my\_path". FoBiS.py will (re-)compile only _foo.f90_ file (independently if it is a program-file or not) and all its dependencies if necessary.

### Compile a specific target with user-defined flags

      FoBiS.py bluid -cflags '-c -cpp -O2' -src my_path -target my_path/my_sub_path/foo.f90

### Clean project tree

      FoBiS.py clean

## fobos: the FoBiS.py makefile

For dealing with (repetitive) buildings of complex projects, FoBiS.py execution can be driven by means of a configuration file placed into the current working directory and named _fobos_: FOrtran Building OptionS file. The options defined into _fobos_ file completely override the CLI arguments: this file is designed to act as a makefile, but with a very simple syntax (similar to INI files). Presently, _fobos_ file has, at most, the following options

      [general]
      src=./src/
      colors=True
      log=False
      quiet=False
      target=foo.f90
      [builder]
      compiler=custom
      fc=ifort
      modsw=-module
      mpi=False
      cflags=-c -cpp -O2
      lflags=-O2
      libs=lib/bar.so lib/boo.a
      dmod=./mod/
      dobj=./obj/
      dexe=./

There are two sections: _builder_ specifying builder options used for each parsed file and _general_ specifying global options. If an option is present it will overrides the default value of CLI. Options can be commented with "#" symbol. For both _build_ and _clean_ executions of FoBiS.py a _fobos_ file placed elsewhere and having different name can be specified by means of "-f" switch

      FoBiS.py build -f /other_path/fobos.other_name

      FoBiS.py clean -f /other_path/fobos.other_name

Using this feature it is simple to perform context-specific buildings accordingly to different goals, e.g. it is convenient to have concurrently more _fobos_ files, one for debug building, one for release building, one for AIX architecture, one for MPI building and so on.

## Example

Into the _example_ directory there is an example of how FoBiS.py can be useful. This example consists of a very simple program, _cumbersome.f90_ contained into _src_ directory. This program is a cumbersome version of a classical _hello world_. The main program uses the module "nested_1" contained into "src/nested-1/first_dep.f90" file. The module "nested_1" has included the file "src/nested-1/nested-2/second_dep.f90". A _fobos_ file is provided for building the example.

For testing the example type

      FoBiS.py build

It is worth noting that the module "nested_1" is contained into a file whose name if completely different from the module one (first_dep.f90) and that the inclusion of "second_dep.f90" is done without any paths neither absolute nor relative, i.e. "include 'second_dep.f90'", but FoBiS.f90 can automatically resolves such general dependencies.

## Tips for non pythonic users

In the example above FoBiS.py is supposed to have the executable permissions, thus it is used without an explicit invocation of the Python interpreter. In general, if FoBiS.py is not set to have executable permissions, it must be executed as:

      python FoBiS.py ...
