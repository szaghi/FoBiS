# FoBiS.py
### FoBiS.py, Fortran Building System for poor men

A very simple and stupid tool for automatic building modern Fortran project.

## Table of Contents

* [Team Members](#team-members)
* [Why?](#why)
* [OK, what can FoBiS.py do? I am a _poor-fortran-man_, I do not understand you...](#fobis-explained)
* [Main features](#main-features)
* [Todos](#todos)
* [Requirements](#requirements)
* [Copyrights](#copyrights)
* [Usage](#usage)
* [fobos: the FoBiS.py makefile](#fobos)
* [Examples](#examples)
* [Tips for non pythonic users](#tips)

## <a name="team-members"></a>Team Members
* Stefano Zaghi <stefano.zaghi@gmail.com>

## <a name="why"></a>Why?

GNU Make, CMake, SCons & Co. are fantastic tools, even too much for a _poor-fortran-man_.
However, the support for modern Fortran project is still poor: in particular, it is quite difficult (and boring) to track the inter-module-dependency hierarchy of project using many module files.
Modern Fortran programs can take great advantages of module using, however their compilations can become quickly a nightmare as the number of modules grows. As consequence, an automatic building system able to track (on the fly) any changes on the inter-module-dependency hierarchy can save the life of a _poor-fortran-man_.

## <a name="automake"></a>Why not use an auto-make-like tool?

There are a lot of alternatives for deal with inter-module-dependency hierarchy, but they can be viewed as a pre-processor for the actual building system (such as auto-make tools or even the Fortran compiler itself that, in most cases, can generate a dependency list of a processed file), thus they introduce another level of complexity... but a _poor-fortran-man_ always loves the KISS (Keep It Simple, Stupid) things! FoBiS.py is designed to do just one thing: build a modern Fortran program without boring you to specify a particular compilation hierarchy.

## <a name="fobis-explained"></a>OK, what can FoBiS.py do? I am a _poor-fortran-man_, I do not understand you...

Suppose you have a Fortran project composed of many Fortran modules placed into a complicated nested directories tree. Your goal is to build some (all) of the main programs contained into the project tree, but you have no time (or patience) to write the complicated makefile(s) able to correctly build your programs. In this case FoBiS.py can save your life: just type _python FoBiS.py build_ into the root of your project and FoBis.py will (try to) build all the main programs nested into the current directory. Obviously, FoBiS.py will not (re-)compile unnecessary objects if they are up-to-date (like the "magic" of a makefile). FoBiS.py have many (ok... some) others interesting features: if I have convinced you, please read the following.

## <a name="main-features"></a>Main features
+ Automatic parsing of files for dependency-hierarchy creation in case of _use_ and _include_ statements;
+ automatic building of all _programs_ found into the root directory parsed or only a specific selected target;
+ avoid unnecessary re-compilation (algorithm based on file-timestamp value);
+ simple command line interface;
+ Intel, GNU and g95 Fortran Compilers support;
+ custom compiler support;
+ configuration-files-free;
+ ... but also configuration-file driven building for complex buildings;
+ parallel compiling enabled by means of concurrent multiprocesses jobs;
+ easy-extensible: FoBis.py is just a less-than 1000 lines of Python statements... no bad for a poor-make-replacement;
+ ...

## <a name="todos"></a>Todos
+ Pythonic pre-processor;
+ add IBM, PGI Fortran Compilers support;
+ ...
+ GUI... nooooooooooo, we are _poor-fortran-men_!
+ ...

## <a name="requirements"></a>Requirements
+ Python 2.7+;
+ a lot of patience with the author.

FoBiS.py is developed on a GNU/Linux architecture, and it has been tested also on AIX one. For Windows architecture there is no support, however it should be work out-of-the-box.

## <a name="Copyrights"></a>Copyrights

FoBiS.py is an open source project, it is distributed under the [GPL v3](http://www.gnu.org/licenses/gpl-3.0.html). Anyone is interest to use, to develop or to contribute to FoBiS.py is welcome.

## <a name="usage"></a>Usage

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

      usage: FoBiS.py build [-h] [-f F] [-colors] [-log] [-quiet] [-j J]
                            [-compiler COMPILER] [-fc FC] [-modsw MODSW] [-mpi]
                            [-cflags CFLAGS] [-lflags LFLAGS]
                            [-libs LIBS [LIBS ...]] [-I I [I ...]]
                            [-inc INC [INC ...]] [-dobj DOBJ] [-dmod DMOD]
                            [-dexe DEXE] [-src SRC] [-exclude EXCLUDE [EXCLUDE ...]]
                            [-target TARGET] [-o O] [-mklib MKLIB]

      optional arguments:
        -h, --help            show this help message and exit
        -f F                  Specify a "fobos" file named differently from "fobos"
        -colors               Activate colors in shell prints [default: no colors]
        -log                  Activate the creation of a log file [default: no log
                              file]
        -quiet                Less verbose than default
        -j J                  Specify the number of concurrent jobs used for
                              compiling dependencies [default 1]
        -compiler COMPILER    Compiler used: Intel, GNU, IBM, PGI, g95 or Custom
                              [default: Intel]
        -fc FC                Specify the Fortran compiler statement, necessary for
                              custom compiler specification (-compiler Custom)
        -modsw MODSW          Specify the switch for setting the module searching
                              path, necessary for custom compiler specification
                              (-compiler Custom)
        -mpi                  Use MPI enabled version of compiler
        -cflags CFLAGS        Compilation flags [default: -c -cpp]
        -lflags LFLAGS        Linking flags
        -libs LIBS [LIBS ...]
                              List of external libraries used
        -I I [I ...]          List of directories for searching included files
        -inc INC [INC ...]    Add a list of custom-defined file extensions for
                              include files
        -dobj DOBJ            Directory containing compiled objects [default:
                              ./obj/]
        -dmod DMOD            Directory containing .mod files of compiled objects
                              [default: ./mod/]
        -dexe DEXE            Directory containing executable objects [default: ./]
        -src SRC              Root-directory of source files [default: ./]
        -exclude EXCLUDE [EXCLUDE ...]
                              Exclude a list of files from the building process
        -target TARGET        Specify a target file [default: all programs found]
        -o O                  Specify the output file name is used with -target
                              switch [default: basename of target]
        -mklib MKLIB          Build library instead of program (use with -target
                              switch); usage: -mklib static or -mklib shared

Printing the _clean_ help message:

      FoBiS.py clean -h

This will echo:

      usage: FoBiS.py clean [-h] [-f F] [-colors] [-dobj DOBJ] [-dmod DMOD]
                            [-dexe DEXE] [-target TARGET] [-o O] [-mklib MKLIB]

      optional arguments:
        -h, --help      show this help message and exit
        -f F            Specify a "fobos" file named differently from "fobos"
        -colors         Activate colors in shell prints [default: no colors]
        -dobj DOBJ      Directory containing compiled objects [default: ./obj/]
        -dmod DMOD      Directory containing .mod files of compiled objects
                        [default: ./mod/]
        -dexe DEXE      Directory containing executable objects [default: ./]
        -target TARGET  Specify a target file [default: all programs found]
        -o O            Specify the output file name is used with -target switch
                        [default: basename of target]
        -mklib MKLIB    Build library instead of program (use with -target switch);
                        usage: -mklib static or -mklib shared

### Compile all programs found

      FoBiS.py build

FoBiS.py will recursively search for _program_ files into the directories nested into "./". Program files are captured parsing each file found: a file is a _program-file_ if it contains the Fortran statement _program_.
It is worth noting that the above FoBiS.py call will use the default compilations options.

### Compile all programs found excluding some files

      FoBiS.py build -exclude foo.f90 bar.f

FoBiS.py will recursively search for _program_ files into the directories nested into "./" and, excluding _foo,f90_ and _bar.f_, all other files will be parsed and, in case, built.

### Compile a specific target

      FoBiS.py build -src my_path -target my_path/my_sub_path/foo.f90

FoBiS.py will recursively search for "my_path/my_sub_path/foo.f90" and for all its dependency files into the directories nested into "my\_path". FoBiS.py will (re-)compile only _foo.f90_ file (independently if it is a program-file or not) and all its dependencies if necessary. In case the target is a program is output name will be the basename without any extension (i.e. _foo_ in the example). If a different output name is preferable it can be specified by the "-o" switch, namely

      FoBiS.py build -src my_path -target my_path/my_sub_path/foo.f90 -o FoO

### Compile a specific target with user-defined flags

      FoBiS.py build -cflags '-c -cpp -O2' -src my_path -target my_path/my_sub_path/foo.f90

### Compile large projects: maximize building speedup on parallel architectures

      FoBiS.py build -j #cpus

This is an experimental feature not yet completely tested, thus it should be carefully used. Using the switch "-j" enables a pool of concurrent jobs (the number of which should be equal to the number of physical cpus or cores available) for compiling targets dependencies. Presently, the pool is not optimized and balanced accordingly to the number of files that must be (re-)compiled.

### Build a library

      FoBiS.py build -target mylib.f90 -mklib static

      FoBiS.py build -target mylib.f90 -mklib shared

FoBiS.py offers a primitive support for building libraries, both static and shared. Presently, this feature can be used only within -target switch. Notably, this should work only on Unix-like architectures.

Into _examples_ directory there is an example of a _cumbersome_ library building.

### Clean project tree

      FoBiS.py clean

## <a name="fobos"></a>fobos: the FoBiS.py makefile

For dealing with (repetitive) buildings of complex projects, FoBiS.py execution can be driven by means of a configuration file placed into the current working directory and named _fobos_: FOrtran Building OptionS file. The options defined into _fobos_ file completely override the CLI arguments: this file is designed to act as a makefile, but with a very simple syntax (similar to INI files). Presently, _fobos_ file has, at most, the following options

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
      src=./src/
      colors=True
      quiet=False
      j=1
      exclude=pon.F cin.f90
      I=other_include_path another_include_path
      inc=.cmn .icp
      mklib=static
      [files]
      log=False
      target=foo.f90
      o=FoO

There are two sections: _builder_ specifying builder options used for each parsed file and _general_ specifying global options. If an option is present it will overrides the default value of CLI. Options can be commented with "#" symbol. For both _build_ and _clean_ executions of FoBiS.py a _fobos_ file placed elsewhere and having different name can be specified by means of "-f" switch

      FoBiS.py build -f /other_path/fobos.other_name

      FoBiS.py clean -f /other_path/fobos.other_name

Using this feature it is simple to perform context-specific buildings accordingly to different goals, e.g. it is convenient to have concurrently more _fobos_ files, one for debug building, one for release building, one for AIX architecture, one for MPI building and so on.

## <a name="examples"></a>Examples

Into the directory _examples_ there are some KISS examples, just read their provided _REAMDE.md_.

## <a name="tips"></a>Tips for non pythonic users

In the examples above FoBiS.py is supposed to have the executable permissions, thus it is used without an explicit invocation of the Python interpreter. In general, if FoBiS.py is not set to have executable permissions, it must be executed as:

      python FoBiS.py ...
