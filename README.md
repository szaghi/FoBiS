# FoBiS.py
### <a name="top">FoBiS.py, Fortran Building System for poor men
A very simple and stupid tool for automatic building modern Fortran projects.

## <a name="toc">Table of Contents
* [Team Members](#team-members)
    + [Contributors](#contributors)
* [Why?](#why)
    + [Why not use an auto-make-like tool?](#automake)
    + [OK, what can FoBiS.py do? I am a _poor-fortran-man_, I do not understand you...](#fobis-explained)
* [Main features](#main-features)
* [Todos](#todos)
* [Requirements](#requirements)
* [Install](#install)
* [Getting Help](#help)
* [Copyrights](#copyrights)
* [Usage](#usage)
    + [Build all programs found](#build-all)
    + [Build all programs found excluding some files](#build-all-exclude)
    + [Build a specific target](#build-target)
    + [Build a specific target with user-defined flags](#build-user-flags)
    + [Build large projects: maximize building speedup on parallel architectures](#build-parallel)
    + [Build a library](#build-library)
    + [Clean project tree](#clean)
* [fobos: the FoBiS.py makefile](#fobos)
    + [single-building-mode fobos](#single-mode-fobos)
    + [many-building-modes fobos](#many-mode-fobos)
    + [Rules: using fobos file for performing minor (repetitive) tasks](#fobos-rules)
* [Examples](#examples)
* [Tips for non pythonic users](#tips)
* [Version History](#versions)

## <a name="team-members"></a>Team Members
* Stefano Zaghi, aka _szaghi_ <https://github.com/szaghi>

### <a name="contributors"></a>Contributors
* Tomas Bylund, aka _Tobychev_ <https://github.com/Tobychev>
<p style='text-align: right;'>Go to [Top](#top) or [Toc](#toc)</p>
## <a name="why"></a>Why?
GNU Make, CMake, SCons & Co. are fantastic tools, even too much for a _poor-fortran-man_.
However, the support for modern Fortran project is still poor: in particular, it is quite difficult (and boring) to track the inter-module-dependency hierarchy of project using many module files.
Modern Fortran programs can take great advantage of using modules; however their compilations can quickly become a nightmare as the number of modules grows. As  a consequence, an automatic build system able to track (on the fly) any changes on the inter-module-dependency hierarchy can save the life of a _poor-fortran-man_.

### <a name="automake"></a>Why not use an auto-make-like tool?

There are a lot of alternatives for deal with inter-module-dependency hierarchy, but they can be viewed as a pre-processor for the actual building system (such as auto-make tools or even the Fortran compiler itself that, in most cases, can generate a dependency list of a processed file), thus they introduce another level of complexity... but a _poor-fortran-man_ always loves the KISS (Keep It Simple, Stupid) things! FoBiS.py is designed to do just one thing: build a modern Fortran program without boring you to specify a particular compilation hierarchy.

### <a name="fobis-explained"></a>OK, what can FoBiS.py do? I am a _poor-fortran-man_, I do not understand you...

Suppose you have a Fortran project composed of many Fortran modules placed into a complicated nested directories tree. Your goal is to build some (all) of the main programs contained into the project tree, but you have no time (or patience) to write the complicated makefile(s) able to correctly build your programs. In this case FoBiS.py can save your life: just type _python FoBiS.py build_ in the root of your project and FoBis.py will (try to) build all the main programs nested into the current directory. Obviously, FoBiS.py will not (re-)compile unnecessary objects if they are up-to-date (like the "magic" of a makefile). FoBiS.py have many (ok... some) others interesting features: if I have convinced you, please read the following.

<p style='text-align: right;'>Go to [Top](#top) or [Toc](#toc)</p>
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

<p style='text-align: right;'>Go to [Top](#top) or [Toc](#toc)</p>
## <a name="todos"></a>Todos
+ Pythonic pre-processor;
+ add IBM, PGI Fortran Compilers support;
+ ...

<p style='text-align: right;'>Go to [Top](#top) or [Toc](#toc)</p>
## <a name="requirements"></a>Requirements
+ Python 2.7+ (not yet ready for Python 3.x);
    + required modules:
        + sys;
        + os;
        + time;
        + argparse;
        + copy;
        + subprocess;
        + shutil;
        + configparser;
        + operator;
        + re;
    + optional modules:
        + multiprocessing;
+ a lot of patience with the author.

FoBiS.py is developed on a GNU/Linux architecture, and it has also been tested on AIX one. For Windows architecture there is no support, however it should work out-of-the-box.

<p style='text-align: right;'>Go to [Top](#top) or [Toc](#toc)</p>
## <a name="install"></a>Install
The installation is very simple: put FoBiS.py in your path or execute it using full path. See the [requirements](#requirements) section.
<p style='text-align: right;'>Go to [Top](#top) or [Toc](#toc)</p>
## <a name="help"></a>Getting Help]
You are reading the main documentation of FoBiS.py that should be comprehensive. For more help contact directly the [author](stefano.zaghi@gmail.com). 
<p style='text-align: right;'>Go to [Top](#top) or [Toc](#toc)</p>
## <a name="Copyrights"></a>Copyrights
FoBiS.py is an open source project, it is distributed under the [GPL v3](http://www.gnu.org/licenses/gpl-3.0.html) license. A copy of the license should be distributed within FoBiS.py. Anyone interested to use, develop or to contribute to FoBiS.py is welcome. Take a look at the [contributing guidelines](CONTRIBUTING.md) for starting to contribute to the project.

<p style='text-align: right;'>Go to [Top](#top) or [Toc](#toc)</p>
## <a name="usage"></a>Usage
Printing the main help message:
```bash
FoBiS.py -h
```
This will echo:
```bash
usage: FoBiS.py [-h] [-v] {build,clean,rule} ...

FoBiS.py, Fortran Building System for poor men

optional arguments:
  -h, --help          show this help message and exit
  -v, --version       Show version

Commands:
  Valid commands

  {build,clean,rule}
    build             Build all programs found or a specific target
    clean             Clean project: completely remove OBJ and MOD
                      directories... use carefully
    rule              Execute rules defined into a fobos file
```
Printing the _build_ help message:
```bash
FoBiS.py build -h
```
This will echo:
```bash
usage: FoBiS.py build [-h] [-f FOBOS] [-colors] [-l] [-q] [-j JOBS]
                      [-compiler COMPILER] [-fc FC] [-modsw MODSW] [-mpi]
                      [-cflags CFLAGS] [-lflags LFLAGS]
                      [-libs LIBS [LIBS ...]] [-i INCLUDE [INCLUDE ...]]
                      [-inc INC [INC ...]] [-p PREPROC] [-dobj OBJ_DIR]
                      [-dmod MOD_DIR] [-dbld BUILD_DIR] [-s SRC]
                      [-e EXCLUDE [EXCLUDE ...]] [-t TARGET] [-o OUTPUT]
                      [-mklib MKLIB] [-mode MODE] [-m]
optional arguments:
  -h, --help            show this help message and exit
  -f FOBOS, --fobos FOBOS
                        Specify a "fobos" file named differently from "fobos"
  -colors               Activate colors in shell prints [default: no colors]
  -l, --log             Activate the creation of a log file [default: no log
                        file]
  -q, --quiet           Less verbose than default
  -j JOBS, --jobs JOBS  Specify the number of concurrent jobs used for
                        compiling dependencies [default 1]
  -compiler COMPILER    Compiler used: Intel, GNU, IBM, PGI, g95 or Custom
                        [default: Intel]
  -fc FC                Specify the Fortran compiler statement, necessary for
                        custom compiler specification (-compiler Custom)
  -modsw MODSW          Specify the switch for setting the module searching
                        path, necessary for custom compiler specification
                        (-compiler Custom)
  -mpi                  Use MPI enabled version of compiler
  -cflags CFLAGS        Compile flags
  -lflags LFLAGS        Link flags
  -libs LIBS [LIBS ...]
                        List of external libraries used
  -i INCLUDE [INCLUDE ...], --include INCLUDE [INCLUDE ...]
                        List of directories for searching included files
  -inc INC [INC ...]    Add a list of custom-defined file extensions for
                        include files
  -p PREPROC, --preproc PREPROC
                        Preprocessor flags
  -dobj OBJ_DIR, --obj_dir OBJ_DIR
                        Directory containing compiled objects [default:
                        ./obj/]
  -dmod MOD_DIR, --mod_dir MOD_DIR
                        Directory containing .mod files of compiled objects
                        [default: ./mod/]
  -dbld BUILD_DIR, --build_dir BUILD_DIR
                        Directory containing executable objects [default: ./]
  -s SRC, --src SRC     Root-directory of source files [default: ./]
  -e EXCLUDE [EXCLUDE ...], --exclude EXCLUDE [EXCLUDE ...]
                        Exclude a list of files from the building process
  -t TARGET, --target TARGET
                        Specify a target file [default: all programs found]
  -o OUTPUT, --output OUTPUT
                        Specify the output file name is used with -target
                        switch [default: basename of target]
  -mklib MKLIB          Build library instead of program (use with -target
                        switch); usage: -mklib static or -mklib shared
  -mode MODE            Select a mode defined into a fobos file
  -lmodes               List the modes defined into a fobos file
  -m, --makefile        Generate a GNU Makefile for building the project
```
Printing the _clean_ help message:
```bash
FoBiS.py clean -h
```
This will echo:
```bash
usage: FoBiS.py clean [-h] [-f FOBOS] [-colors] [-dobj OBJ_DIR]
                      [-dmod MOD_DIR] [-dbld BUILD_DIR] [-t TARGET]
                      [-o OUTPUT] [-only_obj] [-only_target] [-mklib MKLIB]
                      [-mode MODE]

optional arguments:
  -h, --help            show this help message and exit
  -f FOBOS, --fobos FOBOS
                        Specify a "fobos" file named differently from "fobos"
  -colors               Activate colors in shell prints [default: no colors]
  -dobj OBJ_DIR, --obj_dir OBJ_DIR
                        Directory containing compiled objects [default:
                        ./obj/]
  -dmod MOD_DIR, --mod_dir MOD_DIR
                        Directory containing .mod files of compiled objects
                        [default: ./mod/]
  -dbld BUILD_DIR, --build_dir BUILD_DIR
                        Directory containing executable objects [default: ./]
  -t TARGET, --target TARGET
                        Specify a target file [default: all programs found]
  -o OUTPUT, --output OUTPUT
                        Specify the output file name is used with -target
                        switch [default: basename of target]
  -only_obj             Clean only compiled objects and not also built targets
  -only_target          Clean only built targets and not also compiled objects
  -mklib MKLIB          Build library instead of program (use with -target
                        switch); usage: -mklib static or -mklib shared
  -mode MODE            Select a mode defined into a fobos file
  -lmodes               List the modes defined into a fobos file
```
Printing the _rule_ help message:
```bash
FoBiS.py rule -h
```
This will echo:
```bash
usage: FoBiS.py rule [-h] [-f FOBOS] [-ex RULE] [-ls]

optional arguments:
  -h, --help            show this help message and exit
  -f FOBOS, --fobos FOBOS
                        Specify a "fobos" file named differently from "fobos"
  -ex RULE, --execute RULE
                        Specify a rule (defined into fobos file) to be
                        executed
  -ls, --list           List the rules defined into a fobos file
  -q, --quiet           Less verbose than default
```
This third execution switch of FoBiS.py can only be used with a proper fobos file. For more details read the section dedicated to the [Rules](#fobos-rules).

### <a name="build-all"></a>Build all programs found

```bash
FoBiS.py build
```

FoBiS.py will recursively search for _program_ files in the directories nested in "./". Program files are captured by parsing each file found: a file is a _program-file_ if it contains the Fortran statement _program_.
It is worth noting that the above FoBiS.py call will use the default compilations options.

### <a name="build-all-exclude"></a>Build all programs found excluding some files

```bash
FoBiS.py build -exclude foo.f90 bar.f
```

FoBiS.py will recursively search for _program_ files in the directories nested in "./" and, excluding _foo.f90_ and _bar.f_, all other files will be parsed and, in this case, built.

### <a name="build-target"></a>Build a specific target

```bash
FoBiS.py build -src my_path -target my_path/my_sub_path/foo.f90
```

FoBiS.py will recursively search for "my_path/my_sub_path/foo.f90" and for all its dependency files in the directories nested in "my\_path". FoBiS.py will (re-)compile only the _foo.f90_ file (independently of if it is a program-file or not) and all its dependencies if necessary. In case the target is a program the output name will be the basename without any extension (i.e. _foo_ in the example). If a different output name is preferable it can be specified by the "-o" switch, namely

```bash
FoBiS.py build -src my_path -target my_path/my_sub_path/foo.f90 -o FoO
```

### <a name="build-user-flags"></a>Build a specific target with user-defined flags

```bash
FoBiS.py build -cflags '-c -cpp -O2' -src my_path -target my_path/my_sub_path/foo.f90
```

### <a name="build-parallel"></a>Build large projects: maximize building speedup on parallel architectures

```bash
FoBiS.py build -j #cpus
```

This is an experimental feature not yet completely tested, thus it should be carefully used. Using the switch "-j" enables a pool of concurrent jobs (the number of which should be equal to the number of physical cpus or cores available) for compiling targets dependencies. Presently, the pool is not optimized and balanced accordingly to the number of files that must be (re-)compiled.

### <a name="build-library"></a>Build a library

```bash
FoBiS.py build -target mylib.f90 -mklib static

FoBiS.py build -target mylib.f90 -mklib shared
```

FoBiS.py offers a primitive support for building libraries, both static and shared. Presently, this feature can be used only within -target switch. Notably, this should work only on Unix-like architectures.

Into _examples_ directory there is an example of a _cumbersome_ library building.

### <a name="clean"></a>Clean project tree
```bash
FoBiS.py clean
```

<p style='text-align: right;'>Go to [Top](#top) or [Toc](#toc)</p>
## <a name="fobos"></a>fobos: the FoBiS.py makefile
For dealing with (repetitive) buildings of complex projects, FoBiS.py execution can be driven by means of a configuration file placed into the current working directory and named _fobos_, FOrtran Building OptionS file. The options defined into _fobos_ file override or in the case of _cflags_, _lflags_ and _preproc_ overload, the CLI arguments: this file is designed to act as a makefile, but with a very simple syntax (similar to INI files). _fobos_ file has exactly the same options available for the command line, in particular the options names are identical to the extended switches names (the ones prefixed with '--') or to the abbreviated ones (prefixed with '-') in case they are the only defined. If an option is present it will overrides the default value of CLI. Options can be commented with "#" symbol. 

Note that if the fobos file is placed into the current working directory it is automatically loaded for both _build_ and _clean_ executions of FoBiS.py, however if a _fobos_ file is placed elsewhere and/or it is named differently from _fobos_ it can still be specified by means of "-f" switch
```bash
FoBiS.py build -f /other_path/fobos.other_name

FoBiS.py clean -f /other_path/fobos.other_name
```
Using this feature it is simple to perform context-specific buildings accordingly to different goals, e.g. it is convenient to have concurrently more _fobos_ files, one for debug building, one for release building, one for AIX architecture, one for MPI building and so on. Nevertheless, many programmers prefer to have only one "makefile" into which different building profiles (hereafter defined _modes_) are defined (they being selected by means of defined switches). For this reason two different kind of fobos file can be defined accordingly to the user _modus operandi_:
+ a fobos file with only one default building _mode_;
+ a fobos file with many different building _modes_.

In the following the two kind of fobos files are described. Note that the fobos file can be used also to define _rules_ for performing minor-tasks, see the [rules](#fobos-rules) section.

### <a name="single-mode-fobos"></a>single-building-mode fobos file
This kind of fobos file _should_ have only one building mode defined by the section _[default]_, e.g. 
```ini
[default]
help     = This is the help message...
colors   = True
quiet    = False
jobs     = 1
compiler = custom
fc       = ifort
modsw    = -module
mpi      = False
cflags   = -c -cpp -O2
lflags   = -O2
preproc  = -DPROFILING
libs     = lib/bar.so lib/boo.a
include  = other_include_path another_include_path
inc      = .cmn .icp
dmod     = ./mod/
dobj     = ./obj/
dexe     = ./
src      = ./src/
exclude  = pon.F cin.f90
mklib    = static
log      = False
target   = foo.f90
output   = FoO
```
Note that due to the design-idea of this kind of fobos file, only one default mode should be defined, but if other modes (sections) are defined, only the one named _default_ is used, whereas the others are ignored. Moreover, the default mode can be placed everywhere into the file, it is not requested to be the first mode defined. Finally, if there is no section named default an error message is prompted, e.g.
```bash
Error: fobos file has not "modes" section neither "default" one
```
The fobos files of the provided [examples](#examples) show rules usage.

### <a name="many-mode-fobos"></a>many-building-modes fobos file
This kind of fobos file can have many different building modes, as a consequence it is necessary a mechanism (a switch) to select one mode (in the following indicated as mode) respect to the others. Such a switch mechanism is defined by a particular section defined into the fobos file, namely the section _modes_, that has only one option named again _modes_, which lists the available modes defined into the fobos file, e.g.
```ini
[modes]
modes = debug-gnu realese-gnu dbg-intel

[debug-gnu]
help     = Compile with GNU gfortran in debug mode
compiler = gnu
cflags   = -c -cpp -O0 -C -g
...
 
[realese-gnu]
help     = Compile with GNU gfortran in realese mode
compiler = gnu
cflags   = -c -cpp -O3
...

[dbg-intel]
help     = Compile with Intel Fortran in debug mode
compiler = intel
cflags   = -c -cpp -O0 -debug all -warn all
...

```
The presence of the section and option _modes_ distinguishes a single-building-mode fobos file from a many-building-modes one, as consequence this section should be the first defined into the fobos file. However, it is possible to place the sections in any order, even with the _modes_ one placed at the end of the fobos file. When a many-building-modes fobos file is used, the switch _-mode_ must be used when invoking FoBiS.py for selecting a particular mode, e.g. 

```bash
FoBiS.py build -mode realese-gnu
```
or, if the fobos file has user-defined name
```bash
FoBiS.py build -f fobos.other.name -mode realese-gnu
```
In the case the switch _-mode_ is omitted, the first defined mode is used (in the example above it is the mode _debug-gnu_). It is worth noting that if the switch _-mode_ is used with a mode name not present in the list defined into the fobos file, an error message is prompted, e.g.
```bash
FoBiS.py build -mode unknown-mode

Error: the mode "unknown-mode" is not defined into the fobos file. Defined modes are:
  - "debug-gnu" Compile with GNU gfortran in debug mode
  - "realese-gnu" Compile with GNU gfortran in realese mode
  - "dbg-intel" Compile with Intel Fortran in debug mode
```
There is also a CLI switch, for both _clean_ and _build_ excutions, for listing the modes defined into a fobos file
```bash
FoBiS.py build -lmodes
```
or 
```bash
FoBiS.py clean -lmodes
```
than a list of modes is prompted, e.g.
```bash
FoBiS.py build -lmodes

The fobos file defines the following modes:
  - "debug-gnu" Compile with GNU gfortran in debug mode
  - "realese-gnu" Compile with GNU gfortran in realese mode
  - "dbg-intel" Compile with Intel Fortran in debug mode
```
The fobos files of the provided [examples](#examples) show rules usage.

### <a name="fobos-rules"></a>Rules: using fobos file for performing minor (repetitive) tasks
Among the others, one useful feature of GNU Make is the ability to perform heterogeneous tasks other than the code building. In general, a _makefile_ can contain generic _rules_ designed to perform any kind of tasks (not only to compile and link codes), e.g. it is often useful to define rule for creating documentation or to generate an archive containing the whole project, just to cite the two most common minor-tasks performed. The fobos file has a similar feature.

For both single and many building-modes fobos file, it is possible to define as many _rules_ as you want by means of a special set of fobos sections. The name of such a section _must_ start with the prefix _rule-_ and can have many defined options named with the starting prefix _rule_ containing the commands that must be executed. For example
```ini
...
[rule-makedoc]
help = Rule for building documentation from source files
rule = doxygen doxy.config
...
[rule-maketar]
quiet   = True
help    = Rule for building project archive
rule_rm = rm -f project.tar
rule_mk = tar cf project.tar *
...
```
this defines two (auto explicative) rules. Note that three different options can be defined: _help_ contains the help message describing the aim of the rule, _quiet_ makes less verbose the output of rules execution and list (suppressing the commands printing, it overrides the -q switch of CLI) and _rule_ that actually defines the rule's commands. Note also that if more than one options have the same name, only the last command is executed. In order to use the defined rules, FoBiS.py must be invoked by means of _rule_ execution: the rules are not usable in the _build_ and _clean_ executions switches. The _rule_ execution has the following CLI: 
```bash
FoBiS.py rule -h
```
This will echo:
```bash
usage: FoBiS.py rule [-h] [-f FOBOS] [-ex RULE] [-ls]

optional arguments:
  -h, --help            show this help message and exit
  -f FOBOS, --fobos FOBOS
                        Specify a "fobos" file named differently from "fobos"
  -ex RULE, --execute RULE
                        Specify a rule (defined into fobos file) to be
                        executed
  -ls, --list           List the rules defined into a fobos file
  -q, --quiet           Less verbose than default
```
Assuming to have defined the 2 rules of the example above, to list the defined rules type
```bash
FoBiS.py rule --list
```
This will echo:
```bash
The fobos file defines the following rules:
 - "makedoc" Rule for building the documentation from source files
       Command => doxygen doxy.config
  - "maketar" Rule for building project archive
```
To execute one rule type
```bash
FoBiS.py rule --execute makedoc
```
Note that if a typo is made when selecting the rule, an error message is prompted
```bash
FoBiS.py rule --execute makedocs
```
This will echo:
```bash
Error: the rule "makedocs" is not defined into the fobos file. Defined rules are:
  - "makedoc" Rule for building the documentation from source files
       Command => doxygen doxy.config
  - "maketar" Rule for building project archive
```
The fobos files of the provided [examples](#examples) show rules usage.

<p style='text-align: right;'>Go to [Top](#top) or [Toc](#toc)</p>
## <a name="examples"></a>Examples
Into the directory _examples_ there are some KISS examples, just read their provided _REAMDE.md_. Here is reported only the fobos file of the "cumbersome_dependency_program" example where the main features of fobos file are shown. 

#### Example of features-rich fobos file
```ini
[modes]
modes = gnu custom

[gnu]
compiler  = Gnu
mpi       = False
cflags    = -c
mod_dir   = ./mod/
obj_dir   = ./obj/
build_dir = ./build/
src       = ./src/
colors    = True
quiet     = False
jobs      = 1
inc       = .h .H
target    = cumbersome.f90
output    = Cumbersome
log       = True

[custom]
compiler  = custom
fc        = g95
modsw     = -fmod=
mpi       = False
cflags    = -c
mod_dir   = ./mod/
obj_dir   = ./obj/
build_dir = ./build/
src       = ./src/
colors    = True
quiet     = False
jobs      = 1
inc       = .h .H
target    = cumbersome.f90
output    = Cumbersome
log       = True

[rule-makedoc]
rule = echo "I am making the doc... nope, this is a joke!"

[rule-maketar]
rule = tar cf cum_example.tar *
```

<p style='text-align: right;'>Go to [Top](#top) or [Toc](#toc)</p>
## <a name="tips"></a>Tips for non pythonic users
In the examples above FoBiS.py is supposed to have the executable permissions, thus it is used without an explicit invocation of the Python interpreter. In general, if FoBiS.py is not set to have executable permissions, it must be executed as:

```bash
python FoBiS.py ...
```
<p style='text-align: right;'>Go to [Top](#top) or [Toc](#toc)</p>
## <a name="versions"></a>Version History
In the following the changelog of most important releases is reported.
### 1.0.3
First stable release.
<p style='text-align: right;'>Go to [Top](#top) or [Toc](#toc)</p>
