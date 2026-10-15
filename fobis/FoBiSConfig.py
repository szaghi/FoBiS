#!/usr/bin/env python
"""
FoBiSConfig.py, module definition of FoBiS.py configuration.
"""

# Copyright (C) 2020  Stefano Zaghi
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
import hashlib
import os
import re
import sys
from typing import Any

from typer.testing import CliRunner as _CliRunner

from .Builder import Builder
from .cli_parser import _normalize_args
from .cli_parser import app as _fobis_app
from .Colors import Colors
from .Compiler import Compiler
from .Fobos import Fobos
from .utils import fobis_command, syswork

__appname__ = "FoBiS.py"
__author__ = "Stefano Zaghi"
__author_email__ = "stefano.zaghi@gmail.com"
__license__ = "GNU General Public License v3 (GPLv3)"
__url__ = "https://github.com/szaghi/FoBiS"
__description__ = "a Fortran Building System"
__long_description__ = "FoBiS.py, a Fortran Building System, is a KISS tool for automatic building modern Fortran projects, it being able to automatically resolve inter-modules dependancy hierarchy."


class FoBiSConfig:
    """
    FoBiS configuration class handling.
    """

    def __init__(self, fake_args: list[str] | None = None) -> None:
        """
        Attributes
        ----------
        cliargs : argparse.ArgumentParser()
          CLI arguments, argparse object
        fobos : Fobos()
          Fobos object, the FoBiS.py makefile
        colors : {Colors()}
          Colors object
        """
        _shared = {}
        _args = _normalize_args(fake_args if fake_args is not None else sys.argv[1:])
        _result = _CliRunner().invoke(_fobis_app, _args, obj=_shared)
        if _result.output:
            sys.stdout.write(_result.output)
        if "cliargs" not in _shared:
            sys.exit(_result.exit_code)
        self.cliargs = _shared["cliargs"]
        self.colors = Colors()
        self.fobos = Fobos(cliargs=self.cliargs, print_n=self.print_b, print_w=self.print_r)
        self.colors = Colors(enabled=getattr(self.cliargs, "colors", False))  # reset colors accordingly fobos options
        self._postinit()

    def _update_extensions(self) -> None:
        """Update files extensions"""
        if self.cliargs.which == "build" or self.cliargs.which == "rule":
            for inc in self.cliargs.inc:
                if inc not in self.cliargs.extensions:
                    self.cliargs.extensions.append(inc)
            if len(self.cliargs.preprocessor_ext) > 0:
                self.cliargs.extensions += self.cliargs.preprocessor_ext

    def _sanitize_paths(self) -> None:
        """
        Sanitize paths.
        """
        if self.cliargs.which == "clean" or self.cliargs.which == "build" or self.cliargs.which == "rule":
            self.cliargs.build_dir = os.path.normpath(self.cliargs.build_dir)
            self.cliargs.mod_dir = os.path.normpath(self.cliargs.mod_dir)
            self.cliargs.obj_dir = os.path.normpath(self.cliargs.obj_dir)
        if self.cliargs.which == "build" or self.cliargs.which == "rule":
            for n, src in enumerate(self.cliargs.src):
                self.cliargs.src[n] = os.path.normpath(src)
            for n, inc in enumerate(self.cliargs.include):
                self.cliargs.include[n] = os.path.normpath(inc)
            for n, exc in enumerate(self.cliargs.exclude_dirs):
                self.cliargs.exclude_dirs[n] = os.path.normpath(exc)
        if self.cliargs.which == "install":
            self.cliargs.build_dir = os.path.normpath(self.cliargs.build_dir)
            self.cliargs.prefix = os.path.normpath(self.cliargs.prefix)
            self.cliargs.bin = os.path.normpath(self.cliargs.bin)
            self.cliargs.lib = os.path.normpath(self.cliargs.lib)
            self.cliargs.include = os.path.normpath(self.cliargs.include)

    def _check_cflags_heritage(self) -> None:
        """
        Check the heritage of cflags: if a file named '.cflags.heritage' is found into the root dir FoBiS.py is runned that file
        is sourced and compared with the actual cflags and in case they differ the project is forced to be recompiled. The actual cflags are saved,
        in any case, into that file.
        """
        if self.cliargs.which == "build" or self.cliargs.which == "rule":
            if self.cliargs.cflags_heritage:
                cflags = Builder.get_cflags(cliargs=self.cliargs)
                c_compiler = Compiler(cliargs=self.cliargs)
                if c_compiler.c_explicit:  # the C settings, when the mode has any: a heritage file stays as it was
                    cflags += "\n" + c_compiler.compile_cmd_c()
                if self.cliargs.target:
                    her_file = os.path.join(
                        self.cliargs.build_dir, "." + os.path.basename(self.cliargs.target) + ".cflags.heritage"
                    )
                else:
                    her_file = os.path.join(self.cliargs.build_dir, ".cflags.heritage")
                if os.path.exists(her_file):
                    with open(her_file) as fh:
                        cflags_old = fh.read()
                    if cflags != cflags_old:
                        self.cliargs.force_compile = True
                        self.print_r(
                            "The present cflags are different from the heritages one: forcing to (re-)compile all"
                        )
                if not os.path.exists(self.cliargs.build_dir):
                    os.makedirs(self.cliargs.build_dir)
                with open(her_file, "w") as chf:
                    chf.writelines(cflags)

    def _postinit(self) -> None:
        """
        Post-initialization update of config attributes, after CLI and fobos parsing.
        """
        self._apply_shadow()
        self._apply_variant()
        self._update_extensions()
        self._sanitize_paths()
        self._auto_discover_src()
        self._check_cflags_heritage()
        if self.cliargs.which == "build" or self.cliargs.which == "rule":
            if len(self.cliargs.vlibs) > 0:
                self._check_vlibs_md5sum()
            if len(self.cliargs.ext_vlibs) > 0:
                self._check_ext_vlibs_md5sum()
        self._load_fetched_deps()
        self._check_interdependent_fobos()

    def _apply_shadow(self) -> None:
        """``--shadow NAME``: the mode's flags turned into the shadow's, objects in the shadow's build directory."""
        shadow = getattr(self.cliargs, "shadow", None)
        if not shadow or self.cliargs.which not in ("build", "introspect", "test", "run"):
            return
        from .verification.shadow import ShadowError, apply

        mode = self.fobos.mode if self.fobos is not None else None
        try:
            apply(self.cliargs, shadow, mode)
        except ShadowError as exc:
            self.print_r(f"Error: {exc}")
            sys.exit(2)

    def _apply_variant(self) -> None:
        """``--variant NAME --variant-cflags F``: a build variant of ``fobis assess`` (flags appended, own objects)."""
        name = getattr(self.cliargs, "variant", None)
        if not name or self.cliargs.which not in ("build", "introspect"):
            return
        from .verification.shadow import apply_variant

        mode = self.fobos.mode if self.fobos is not None else None
        apply_variant(self.cliargs, name, self.cliargs.variant_cflags, self.cliargs.variant_lflags, mode)

    def _auto_discover_src(self) -> None:
        """
        Apply convention-based source directory auto-discovery (issue #177).

        When ``src`` is not explicitly set and ``no_auto_discover`` is False,
        scan for ``src/``, ``source/``, and ``app/`` directories.
        """
        if self.cliargs.which not in ("build", "rule"):
            return
        if getattr(self.cliargs, "no_auto_discover", False):
            return
        # If src was explicitly set in the fobos file, honour it as-is
        if (
            self.fobos is not None
            and self.fobos.fobos is not None
            and self.fobos.mode is not None
            and self.fobos.fobos.has_option(self.fobos.mode, "src")
        ):
            return
        # Check if src was explicitly set on the CLI (differs from the default ["./"])
        current_src = getattr(self.cliargs, "src", ["./"])
        if current_src and current_src != ["./"] and current_src != [os.path.normpath("./")]:
            return
        from .utils import auto_discover_src

        discovered = auto_discover_src(root=".")
        if discovered:
            self.print_b("[auto-discover] src not set; scanning: " + ", ".join(discovered))
            self.cliargs.src = [os.path.normpath(d) for d in discovered]

    def _load_fetched_deps(self) -> None:
        """
        Auto-load dependencies previously fetched with 'fetch' command, and the path dependencies.

        Reads .fobis_deps/.deps_config.ini (if present) and appends its dependon
        entries to cliargs.dependon so the existing interdependent build machinery
        picks them up automatically. ``check`` reads it too: without it the fetched modules were unresolved.
        Path dependencies (``path=DIR``) are read from the fobos itself, so they need no fetch: a ``use=fobos`` one
        joins ``dependon``, a ``use=sources`` one the sources (its ``.git``, build and deps directories excluded).
        """
        if self.cliargs.which not in ("build", "check", "doctests"):
            return
        from .Fetcher import Fetcher

        deps_dir = self.fobos.get_deps_dir()
        fetcher = Fetcher(deps_dir=deps_dir, print_n=self.print_b, print_w=self.print_r)
        config_file = os.path.join(deps_dir, ".deps_config.ini")
        config = fetcher.load_config() if os.path.exists(config_file) else {}
        # test-only deps: for the builds of fobis test (hidden --dev-deps), doctests and check (it scans the
        # test programs too); any other build leaves them out, even when its sources contain the deps dir
        with_dev = self.cliargs.which in ("check", "doctests") or getattr(self.cliargs, "dev_deps", False)
        dependon = config.get("dependon", []) + (config.get("dev_dependon", []) if with_dev else [])
        src = config.get("src", []) + (config.get("dev_src", []) if with_dev else [])
        excluded = [] if with_dev else config.get("dev_src", [])
        excluded += [os.path.dirname(e.split(":")[0]) for e in (config.get("dev_dependon", []) if not with_dev else [])]
        try:
            path_deps = fetcher.path_dependencies(self.fobos)
        except ValueError as error:
            self.print_r(f"Error: {error}")
            sys.exit(2)
        for dep in path_deps:
            if not os.path.isdir(dep["path"]):
                self.print_r(f"Error: path dependency '{dep['name']}': directory {dep['path']} not found")
                sys.exit(1)
            if dep["dev"] and not with_dev:
                excluded.append(dep["path"])
            elif dep["use"] == "fobos":
                fobos_file = os.path.join(dep["path"], "fobos")
                dependon.append(fobos_file + (":" + dep["mode"] if dep["mode"] else ""))
            else:
                src.append(dep["path"])
                excluded += fetcher.path_excludes(dep["path"])
        self.cliargs.dependon.extend(dependon)
        for entry in dependon:
            excluded.append(os.path.dirname(entry.split(":")[0]))
        for dep_dir in excluded:
            dep_dir = os.path.normpath(dep_dir)
            if dep_dir not in self.cliargs.exclude_dirs:
                self.cliargs.exclude_dirs.append(dep_dir)
        for src_path in src:
            abs_src = os.path.abspath(
                src_path
            )  # covered: under a source path (whole components: core-utils/ is not core/)
            covered = (os.path.abspath(s) for s in self.cliargs.src)
            if not any(abs_src == base or abs_src.startswith(base.rstrip(os.sep) + os.sep) for base in covered):
                self.cliargs.src.append(src_path)

    @staticmethod
    def _check_md5sum(filename: str, hashfile: str) -> tuple[bool, bool]:
        """
        Check the md5sum hash of a file, compares with an eventual hashfile into which the hash is finally saved.

        Parameters
        ----------
        filename : str
          file name (with path) of file to be hashed
        hashfile : str
          file eventually present containing the hash and into which the hash is finally saved

        Returns
        -------
        2 bools containing the previously existance of the hashfile and the result of hashes comparison
        """
        with open(filename, "rb") as fh:
            md5sum = hashlib.md5(fh.read()).hexdigest()
        hashexist = os.path.exists(hashfile)
        comparison = False
        if hashexist:
            with open(hashfile) as fh:
                md5sum_old = fh.read()
            comparison = md5sum == md5sum_old
        with open(hashfile, "w") as md5:
            md5.writelines(md5sum)
        return hashexist, comparison

    def _check_vlibs_md5sum(self) -> None:
        """
        Check if the md5sum of volatile libraries has changed and, in case, a re-build is triggered.
        """
        for lib in self.cliargs.vlibs:
            if not os.path.exists(lib):
                self.print_r("The volatile library " + lib + " is not found!")
            hashfile, comparison = self._check_md5sum(
                filename=lib, hashfile=os.path.join(self.cliargs.build_dir, "." + os.path.basename(lib) + ".md5")
            )
            if hashfile:
                self.cliargs.force_compile = (not comparison) or self.cliargs.force_compile
                if not comparison:
                    self.print_r(
                        "The volatile library "
                        + lib
                        + " is changed with respect the last building: forcing to (re-)compile all"
                    )

    def _check_ext_vlibs_md5sum(self) -> None:
        """
        Check if the md5sum of volatile external libraries has changed and, in case, a re-build is triggered.
        """
        for lib in self.cliargs.ext_vlibs:
            lib_found = False
            if len(self.cliargs.lib_dir) > 0:
                for dirp in self.cliargs.lib_dir:
                    libpath = os.path.join(dirp, "lib" + lib + ".a")
                    lib_found = os.path.exists(libpath)
                    if lib_found:
                        break
                    libpath = os.path.join(dirp, "lib" + lib + ".so")
                    lib_found = os.path.exists(libpath)
                    if lib_found:
                        break
            else:
                libpath = "lib" + lib + ".a"
                lib_found = os.path.exists(libpath)
                if not lib_found:
                    libpath = "lib" + lib + ".so"
                    lib_found = os.path.exists(libpath)
            if not lib_found:
                self.print_r("The volatile library " + lib + " is not found!")
            hashfile, comparison = self._check_md5sum(
                filename=libpath,
                hashfile=os.path.join(self.cliargs.build_dir, "." + os.path.basename(libpath) + ".md5"),
            )
            if hashfile:
                self.cliargs.force_compile = (not comparison) or self.cliargs.force_compile
                if not comparison:
                    self.print_r(
                        "The volatile library "
                        + lib
                        + " is changed with respect the last building: forcing to (re-)compile all"
                    )

    def _add_include_paths(self, add_paths: list[Any]) -> None:
        """
        Add include files search paths.

        Parameters
        ----------
        add_paths : list
          added paths, each element has 3 elements: path[0] libraries search path, path[1] include files search path, path[2] the library
        """
        self.print_r("Include files search paths (include):")
        for path in add_paths:
            if self.cliargs.include:
                self.cliargs.include.append(path[1])
            else:
                self.cliargs.include = [path[1]]
            self.print_r("- " + path[1])

    def _add_lib_dir_paths(self, add_paths: list[Any]) -> None:
        """
        Add libraries search paths.

        Parameters
        ----------
        add_paths : list
          added paths, each element has 3 elements: path[0] libraries search path, path[1] include files search path, path[2] the library
        """
        self.print_r("Libraries search paths (lib_dir):")
        for path in add_paths:
            if path[2][1].lower() == "indirect":
                if self.cliargs.lib_dir:
                    self.cliargs.lib_dir.append(path[0])
                else:
                    self.cliargs.lib_dir = [path[0]]
                self.print_r("- " + path[0])

    def _add_ext_libs_paths(self, add_paths: list[Any]) -> None:
        """
        Add libraries paths.

        Parameters
        ----------
        add_paths : list
          added paths, each element has 3 elements: path[0] libraries search path, path[1] include files search path, path[2] the library
        """
        self.print_r("Libraries paths:")
        for path in add_paths:
            if path[2][1].lower() == "indirect":
                lib = re.sub(r"^lib", "", os.path.basename(path[2][0]))
                lib = re.sub(r"\.a$", "", lib)
                lib = re.sub(r"\.so$", "", lib)
                if self.cliargs.ext_libs:
                    self.cliargs.ext_libs.append(lib)
                else:
                    self.cliargs.ext_libs = [lib]
                self.print_r("- (ext_libs) " + lib)
            else:
                if self.cliargs.libs:
                    self.cliargs.libs.append(path[2][0])
                else:
                    self.cliargs.libs = [path[2][0]]
                self.print_r("- (libs) " + path[2][0])

    def _add_auxiliary_paths(self, add_paths: list[Any]) -> None:
        """
        Add auxiliary paths to default searched ones.

        Parameters
        ----------
        add_paths : list
          added paths, each element has 3 elements: path[0] libraries search path, path[1] include files search path, path[2] the library
        """
        self.print_r("The following auxiliary paths have been added")
        self._add_include_paths(add_paths=add_paths)
        self._add_lib_dir_paths(add_paths=add_paths)
        self._add_ext_libs_paths(add_paths=add_paths)

    def _check_interdependent_fobos(self) -> None:
        """
        Check interdependency project by its fobos.
        """
        if self.cliargs.which == "build" and not self.cliargs.lmodes:
            if len(self.cliargs.dependon) > 0:
                add_paths = []
                for dependon in self.cliargs.dependon:
                    fobos_path = os.path.dirname(dependon)
                    fobos_file = os.path.basename(dependon)
                    mode = ""
                    linking = ""
                    matching = re.match(r"^.*\(\((?P<link>.*)\)\).*$", fobos_file)
                    if matching:
                        linking = matching.group("link")
                        fobos_file = re.sub(r"\(\(.*\)\)", "", fobos_file)
                    if ":" in fobos_file:
                        mode = os.path.basename(fobos_file).split(":")[1]
                        fobos_file = os.path.basename(fobos_file).split(":")[0]
                    # the dependency is built and queried by this FoBiS (not whatever FoBiS.py is on PATH)
                    fobis = fobis_command()
                    selection = ["-f", fobos_file] + (["--mode", mode] if mode else [])
                    old_pwd = os.getcwd()
                    os.chdir(os.path.join(old_pwd, fobos_path))
                    if mode != "":
                        self.print_b("Building dependency " + fobos_file + " into " + fobos_path + " with mode " + mode)
                    else:
                        self.print_b("Building dependency " + fobos_file + " into " + fobos_path + " with default mode")
                    quiet = ["--quiet"] if getattr(self.cliargs, "quiet", False) else []
                    result = syswork([*fobis, "build", *selection, *quiet])
                    dbld = syswork([*fobis, "rule", *selection, "--get", "build_dir"])
                    dmod = syswork([*fobis, "rule", *selection, "--get", "mod_dir"])
                    output = syswork([*fobis, "rule", *selection, "--get-output-name"])
                    os.chdir(old_pwd)
                    self.print_b(result[1])
                    if result[0] != 0:
                        sys.exit(result[0])
                    # a mode that does not set them uses build's defaults: before, the include path missed the mod/
                    build_dir = dbld[1].strip("\n") or "./"
                    mod_dir = dmod[1].strip("\n") or "./mod/"
                    add_paths.append(
                        [
                            os.path.normpath(os.path.join(fobos_path, build_dir)),
                            os.path.normpath(os.path.join(fobos_path, build_dir, mod_dir)),
                            [os.path.normpath(os.path.join(fobos_path, output[1].strip("\n"))), linking],
                        ]
                    )
                self._add_auxiliary_paths(add_paths)

    @property
    def machine_output(self) -> bool:
        """The command writes one machine-readable document on stdout (``--json``, ``--format json/sarif``):
        messages and warnings must go to stderr, never in front of it."""
        cliargs = self.cliargs
        formats = (getattr(cliargs, "merge_format", ""), getattr(cliargs, "testgen_format", ""))
        return (
            bool(getattr(cliargs, "json_output", False))
            or "json" in formats
            or getattr(cliargs, "lint_format", "") in ("json", "sarif")
            or bool(getattr(cliargs, "agents_print", False))
            or bool(getattr(cliargs, "fpm_print", False))
            or bool(getattr(cliargs, "bindings_print", False))
        )

    def print_b(self, string: str, end: str = "\n") -> None:
        """
        Print string with bold color (on stderr, uncoloured, when stdout carries machine output).

        Parameters
        ----------
        string : str
          string to be printed
        """
        if self.machine_output:
            print(string, end=end, file=sys.stderr)
            return
        self.colors.print_b(string, end=end)

    def print_r(self, string: str, end: str = "\n") -> None:
        """
        Print string with red color (on stderr, uncoloured, when stdout carries machine output).

        Parameters
        ----------
        string : str
          string to be printed
        """
        if self.machine_output:
            print(string, end=end, file=sys.stderr)
            return
        self.colors.print_r(string, end=end)

    def printf(self) -> str:
        """
        Return a pretty formatted printable string of config settings.
        """
        string = ["FoBiS.py settings\n"]
        options = vars(self.cliargs)
        for key, value in list(options.items()):
            string.append(str(key) + ": " + str(value))
        return "".join([s + "\n" for s in string])
