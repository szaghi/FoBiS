"""
utils.py, module definition of FoBiS.py util functions.
"""

# Copyright (C) 2015  Stefano Zaghi
#
# This file is part of FoBiS.py.
#
# FoBiS.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FoBiS.py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with FoBiS.py. If not, see <http://www.gnu.org/licenses/>.
# from builtins import *
import contextlib
import os
import re
import shlex
import subprocess
import sys


class CircularDependency(SystemExit):
    """Files depend on each other in a cycle (modules using each other): no compile order exists. Exits with status 1.

    Attributes
    ----------
    cycles : list of list of str
        Each cycle as the file names along it, the first repeated at the end.
    """

    def __init__(self, cycles: list[list[str]]) -> None:
        super().__init__(1)
        self.cycles = cycles


def dependency_cycles(pfiles) -> list[list[str]]:
    """The cycles of the direct dependencies of *pfiles* (``pfile_dep``), each as file names, the first repeated at the
    end; one cycle per set of files."""
    cycles: list[list[str]] = []
    seen: set[frozenset[str]] = set()
    state: dict[int, int] = {}  # id -> 1 on the current path, 2 done
    stack: list = []

    def visit(pfile) -> None:
        state[id(pfile)] = 1
        stack.append(pfile)
        for dep in pfile.pfile_dep:
            if dep is pfile:
                continue
            if state.get(id(dep)) == 1:
                cycle = [f.name for f in stack[stack.index(dep) :]]
                if frozenset(cycle) not in seen:
                    seen.add(frozenset(cycle))
                    cycles.append([*cycle, dep.name])
            elif id(dep) not in state:
                visit(dep)
        stack.pop()
        state[id(pfile)] = 2

    for pfile in pfiles:
        if id(pfile) not in state:
            visit(pfile)
    return cycles


class BuildFailed(SystemExit):
    """A compile or link step failed: exits with status 1 (as before) and keeps the failing outputs.

    Attributes
    ----------
    outputs : list of str
        Output of each failed command, for ``fobis build --explain``.
    """

    def __init__(self, outputs: list[str]) -> None:
        super().__init__(1)
        self.outputs = outputs


def print_fake(input_obj, end="\n"):
    """Rename print."""
    print(input_obj, end=end)


C_SOURCE_EXTENSIONS = (".c",)


def is_c_source(path: str) -> bool:
    """A C source file (``.c``): compiled with the C compiler, never parsed as Fortran."""
    return os.path.splitext(path)[1] in C_SOURCE_EXTENSIONS


_C_MARKERS_RE = re.compile(r"/\*|\btypedef\b|\bextern\b|^\s*#\s*include\s*<", re.MULTILINE)


def is_c_header(path: str) -> bool:
    """A ``.h``/``.H`` file written in C (a comment, ``typedef``, ``extern``, ``#include <...>``), not a Fortran include
    file: FoBiS scans ``.h`` files as includes, and the words of a C header became dependencies."""
    if not path.endswith((".h", ".H")):
        return False
    try:
        with open(path, errors="replace") as handle:
            return bool(_C_MARKERS_RE.search(handle.read()))
    except OSError:
        return False


def fobis_command() -> list[str]:
    """Command line running this FoBiS: ``python -m fobis``, or ``python fobis.pyz`` from the zipapp."""
    package = os.path.dirname(os.path.abspath(__file__))
    if os.path.isdir(package):
        return [sys.executable, "-m", "fobis"]
    archive = package
    while archive and not os.path.isfile(archive):
        archive = os.path.dirname(archive)
    return [sys.executable, archive]


def syswork(cmd, shell=False):
    """
    Function for executing system command 'cmd': for compiling and linking files.

    Parameters
    ----------
    cmd : str or list
      command to execute
    shell : {False}
      execute the command through the system shell, so that globs, pipes, redirections and command chains are
      interpreted; to be used only for commands written by the user, like the fobos rules
    """
    error = 0
    args = cmd if shell or not isinstance(cmd, str) else shlex.split(cmd)
    try:
        output = subprocess.check_output(args, shell=shell, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as err:
        error = err.returncode
        output = err.output
    except FileNotFoundError:  # the compiler is not on PATH (icx, nvc of another toolchain): the shell's status
        error = 127
        output = f"{args[0]}: command not found (is its toolchain loaded?)\n".encode()
    output = str(output, encoding="UTF-8")
    return [error, str(output)]


def syswork_steps(steps):
    """
    Run a sequence of compile steps for a single source file.

    Each step is a (cmd, cleanup_path_or_None) tuple. Steps are run in order;
    execution stops on the first non-zero exit code. If cleanup_path is set on
    a step, the file is removed with os.remove() after that step completes
    (regardless of success/failure).

    Returns [error, combined_output] matching the syswork contract.
    """
    combined_output = ""
    for cmd, cleanup in steps:
        error, output = syswork(cmd)
        combined_output += output
        if cleanup:
            with contextlib.suppress(OSError):
                os.remove(cleanup)
        if error:
            return [error, combined_output]
    return [0, combined_output]


def traverse_recursive(parsed_file, path=None):
    """
    The function traverse_recursive performs a yield-recursive traversing of pfile direct dependencies.
    """
    if path is None:
        path = list()
    path.append(parsed_file)
    yield path
    for dep in parsed_file.pfile_dep:
        if dep not in path:  # a cycle (reported by dependency_cycles) would recurse forever
            for path in traverse_recursive(dep, path):
                yield path
    if path:
        path.pop()


def unique_seq(seq):
    """
    The function unique_seq returns the input sequence removing duplicated elements but peserving the original order.
    """
    seen = set()
    seen_add = seen.add
    return [x for x in seq if x not in seen and not seen_add(x)]


def module_is_in(pfiles, module):
    """
    Find the parsed file containing the desidered module.

    Parameters
    ----------
    pfiles : list
      list of parsed files
    module : str
      module name

    Returns
    -------
    file_name : str
      name of file containing the module
    number : int
      number of file containing the module
    """
    file_name = ""
    number = -1
    for fnum, parsed_file in enumerate(pfiles):
        if parsed_file.module:
            for module_name in parsed_file.module_names:
                if module_name.lower() == module.lower():
                    file_name = parsed_file.name
                    number = fnum
                    break
    return file_name, number


def include_is_in(pfiles, include):
    """
    Function finding the parsed file containing the desidered include-file.

    Parameters
    ----------
    pfiles : list
      list of parsed files
    include : str
      include-file name

    Returns
    -------
    file_name : str
      name of file containing the include-file
    number : int
      number of file containing the include-file
    """
    file_name = ""
    number = -1
    # "sub/x.h" (a C include with a directory) matches a file whose path ends with it
    suffix = os.sep + os.path.normpath(include) if os.sep in include or "/" in include else None
    for fnum, parsed_file in enumerate(pfiles):
        if os.path.basename(parsed_file.name) == include or (
            suffix and (os.sep + os.path.normpath(parsed_file.name)).endswith(suffix)
        ):
            file_name = parsed_file.name
            number = fnum
            break
    return file_name, number


def dependency_hiearchy(builder, pfiles, print_w=None, force_compile=False):
    """
    Build parsed files hierarchy.

    Paramters
    ---------
    builder : Builder object
    pfiles : list
      list of ParsedFile objects
    print_w : function
      function for printing emphized warning message
    force_compile : {False}
      flag for forcing (re-)compiling of all dependency
    """
    if print_w is None:
        print_wm = print_fake
    else:
        print_wm = print_w

    # direct dependencies list used after for building indirect (complete) dependencies list
    for parsed_file in pfiles:
        parsed_file.pfile_dep = []
        for dep in parsed_file.dependencies:
            if dep.type == "module":
                dep.file, fnum = module_is_in(pfiles=pfiles, module=dep.name)
                if fnum > -1:
                    if pfiles[fnum] not in parsed_file.pfile_dep:
                        parsed_file.pfile_dep.append(pfiles[fnum])
                else:
                    # there is no source containg the searched module, try to find it into a precompiled mod file into eventually included paths
                    for dinc in builder.dinc:
                        for _, _, files in os.walk(dinc):
                            for filename in files:
                                if (
                                    os.path.splitext(os.path.basename(filename))[0].lower() == dep.name.lower()
                                    and os.path.splitext(os.path.basename(filename))[1].lower() == ".mod"
                                ):
                                    fnum = 0
                                    break
                            if fnum == 0:
                                break
                        if fnum == 0:
                            break
                    dep.external = fnum == 0
                    if fnum != 0:
                        print_wm(
                            "warning: the file '"
                            + parsed_file.name
                            + "' depends on '"
                            + dep.name
                            + "' that is unreachable"
                        )
                        # sys.exit(1)
            if dep.type == "include":
                dep.file, fnum = include_is_in(pfiles=pfiles, include=dep.name)
                if fnum > -1:
                    if pfiles[fnum] not in parsed_file.pfile_dep:
                        pfiles[fnum].program = False
                        pfiles[fnum].module = False
                        pfiles[fnum].nomodlib = False
                        pfiles[fnum].include = True
                        parsed_file.pfile_dep.append(pfiles[fnum])
                        # the directory the include is relative to: "sub/x.h" found as src/sub/x.h -> src
                        directory = os.path.dirname(pfiles[fnum].name)
                        for _ in range(os.path.normpath(dep.name).count(os.sep)):
                            directory = os.path.dirname(directory)
                        if directory not in builder.dinc:
                            builder.dinc.append(directory)
                else:
                    print_wm(
                        "warning: the file '" + parsed_file.name + "' depends on '" + dep.name + "' that is unreachable"
                    )
                    # sys.exit(1)
    cycles = dependency_cycles(pfiles)
    if cycles:
        for cycle in cycles:
            print_wm("error: circular dependency: " + " -> ".join(cycle))
        raise CircularDependency(cycles)
    object_names(pfiles, print_w=print_w)
    # indirect dependency list
    for parsed_file in pfiles:
        parsed_file.create_pfile_dep_all()
    # using the just created hiearchy for checking which files must be (re-)compiled
    external_mods = external_module_times(pfiles, builder.dinc)
    for parsed_file in pfiles:
        parsed_file.check_compile(obj_dir=builder.obj_dir, force_compile=force_compile, external_mods=external_mods)


def external_module_times(pfiles, include_dirs):
    """Modification times of the ``.mod`` files, found in *include_dirs*, of the modules the project uses but does not
    define (an installed library, a ``dependon`` project): {lower-case module name: newest mtime}.

    gfortran rewrites a ``.mod`` only when the module's interface changes, so a ``.mod`` newer than an object means
    the object was compiled against another interface.
    """
    names = {
        dep.name.lower() for pfile in pfiles for dep in pfile.dependencies if dep.type == "module" and not dep.file
    }
    times = {}
    for directory in include_dirs or []:
        for name in names:
            path = os.path.join(directory, name + ".mod")
            if os.path.isfile(path):
                times[name] = max(times.get(name, 0.0), os.path.getmtime(path))
    return times


# what a compiler compiles to an object (any case): another file FoBiS compiles (an .inc not listed as include
# extension) gives no object (gfortran takes it for linker input), so its name is left as it was
COMPILED_SUFFIXES = (
    ".f",
    ".for",
    ".fpp",
    ".fortran",
    ".f77",
    ".f90",
    ".f95",
    ".f03",
    ".f08",
    ".f2k",
    *C_SOURCE_EXTENSIONS,
)


def object_names(pfiles, print_w=None):
    """Give files named alike in several directories (``say_hello.f90`` in three dependencies) objects named after
    their path, ``crate_utils1_src_say_hello.f90.o``: an object is ``<obj_name>.o`` in one directory, and two files
    with one name compiled to the same object (each build overwrote the other's, and the second was taken for up to
    date). Only the files that collide are renamed, so every other object, and FoBiS's outputs, keep their names.
    Called by `dependency_hiearchy` once the included files are known (an ``x.inc`` is one only when a file includes
    it): ``x.F90`` and the ``x.inc`` it includes do not collide."""
    groups = {}
    for pfile in pfiles:
        if not pfile.include and pfile.extension.lower() in COMPILED_SUFFIXES:
            groups.setdefault(pfile.obj_name.lower(), []).append(pfile)  # lower: the Makefile export lowercases them
    for group in groups.values():
        if len(group) < 2:
            continue
        for pfile in group:
            relative = os.path.normpath(os.path.relpath(pfile.name)).replace(os.sep, "_").replace("..", "up")
            pfile.obj_name = relative.lstrip("._") or pfile.obj_name
        programs = [p for p in group if p.program]
        if len(programs) > 1 and print_w is not None and not getattr(programs[0], "named_alike_warned", False):
            programs[0].named_alike_warned = True  # dependency_hiearchy runs once per target
            print_w(
                "warning: programs "
                + ", ".join(p.name for p in programs)
                + " are named alike: built without a target or an output, the last overwrites the others"
            )


def remove_other_main(builder, pfiles, myself):
    """
    The function remove_other_main removes all compiled objects of other program than the current target under building.
    """
    for parsed_file in pfiles:
        if parsed_file.program and parsed_file.name != myself.name:
            if os.path.exists(builder.obj_dir + parsed_file.obj_name + ".o"):
                os.remove(builder.obj_dir + parsed_file.obj_name + ".o")


def check_results(results, log=None, print_w=None):
    """
    Check the result of system commands exectution.

    Parameters
    ----------
    results : list
      list of exectuions results
    log : {False}
      bool for activate errors log saving
    print_w : {None}
      function for printing emphized warning message
    """
    if print_w is None:
        print_wm = print_fake
    else:
        print_wm = print_w

    if not all(v[1] == "" for v in results):
        for result in results:
            if result[1] != "":
                print_wm(result[1])
    if not all(v[0] == 0 for v in results):
        for result in results:
            if result[0] != 0:
                if print_w is None:  # with a printer it was printed above: written again, every error appeared twice
                    sys.stderr.write(result[1])
                if log:
                    with open(log, "a") as logerror:
                        logerror.writelines(result[1])
        raise BuildFailed([result[1] for result in results if result[0] != 0])


def auto_discover_src(root: str = ".") -> list[str]:
    """
    Apply convention-based source directory discovery.

    Checks ``src/``, ``source/``, and ``app/`` under *root* for Fortran source files.
    Returns a list of directories to use as scan roots, or an empty list if none found
    (caller should fall back to the current directory).

    Parameters
    ----------
    root : str
        Project root to search under [default: ``'.'``].

    Returns
    -------
    list[str]
        Directories containing Fortran sources (may be empty).
    """
    candidates = ["src", "source", "app"]
    found: list[str] = []
    for name in candidates:
        path = os.path.join(root, name)
        if os.path.isdir(path) and _has_fortran_sources(path):
            found.append(path)
    return found


def _has_fortran_sources(directory: str) -> bool:
    """Return True if *directory* contains at least one Fortran source file."""
    fortran_exts = {".f90", ".F90", ".f", ".F", ".f95", ".F95", ".f03", ".F03", ".f08", ".F08"}
    for _, _, files in os.walk(directory):
        for f in files:
            if os.path.splitext(f)[1] in fortran_exts:
                return True
    return False


def safe_mkdir(directory, print_w=None):
    """
    Create directory via safe checkings.

    Parameters
    ----------
    directory: str
      path of the directory to be created
    print_w : {None}
      function for printing emphized warning message
    """
    if print_w is None:
        print_wm = print_fake
    else:
        print_wm = print_w

    if os.path.exists(directory):
        if not os.path.isdir(directory):
            print_wm('Error: cannot create directory "' + directory + '", a file with the same name already exists!')
            sys.exit(1)
    else:
        os.makedirs(directory)
    return
