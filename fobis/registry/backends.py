"""
Build backends: build a package's source with the consumer's toolchain and install it into a prefix.

Every backend has two roles. *Build*: configure, build and install with the CONSUMER's compiler (a ``.mod`` file works
only with the compiler that wrote it). *Consume*: one contract whatever the build system, `Artifacts` = an install
prefix with ``lib/`` (libraries), ``include/`` (module files), ``bin/`` (applications), a ``.pc`` file per library
(``lib/pkgconfig``) and the list of modules provided, so a FoBiS, CMake or make consumer links it the same way.

Backends: ``fobis`` (the package's fobos, the mode matching the compiler family), ``fpm`` (fpm itself, required on
PATH: a package without a fobos is built by its own manifest, never by FoBiS), ``cmake`` and ``recipe`` (see `recipe`),
``make``.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field

from .toolchain import Toolchain

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
LIB_SUFFIXES = (".a", ".so", ".dylib")


class BackendError(Exception):
    """A package cannot be built or installed."""


@dataclass
class Artifacts:
    """What an install produced (paths absolute)."""

    prefix: str
    libraries: list[str] = field(default_factory=list)
    executables: list[str] = field(default_factory=list)
    include_dir: str = ""
    modules: list[str] = field(default_factory=list)
    pc_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


Log = Callable[[str], None]


def _quiet(_: str) -> None:
    pass


def run(cmd: list[str], cwd: str, log: Log = _quiet, env: dict[str, str] | None = None) -> str:
    """Run *cmd* in *cwd*; its output (stdout + stderr) is returned, a failure raises BackendError with its tail."""
    log("$ " + " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
            timeout=7200,
            stdin=subprocess.DEVNULL,
        )
    except OSError as error:
        raise BackendError(f"{cmd[0]}: {error}") from error
    output = _ANSI.sub("", result.stdout + result.stderr)
    if result.returncode != 0:
        tail = "\n".join(output.strip().splitlines()[-25:])
        raise BackendError(f"{' '.join(cmd[:3])} failed (exit {result.returncode}):\n{tail}")
    return output


def collect(prefix: str, name: str, version: str, description: str = "", log: Log = _quiet) -> Artifacts:
    """
    The `Artifacts` of an install prefix: libraries in ``lib/``, applications in ``bin/``, module files anywhere under
    ``include/`` (their directory is the include directory), and a ``.pc`` file written for every library that has
    none.
    """
    from ..PkgConfig import PkgConfigSpec, library_stem, write_pc

    artifacts = Artifacts(prefix=os.path.abspath(prefix))
    lib = os.path.join(prefix, "lib")
    pc_found: list[str] = []
    for dirpath, _dirs, files in os.walk(prefix):  # any layout: some CMake projects install into a subdirectory
        for filename in sorted(files):
            path = os.path.abspath(os.path.join(dirpath, filename))
            if filename.startswith("lib") and filename.endswith(LIB_SUFFIXES) and os.path.basename(dirpath) != "bin":
                artifacts.libraries.append(path)
            elif filename.endswith(".pc") and os.path.basename(dirpath) == "pkgconfig":
                pc_found.append(path)
    bin_dir = os.path.join(prefix, "bin")
    if os.path.isdir(bin_dir):
        for filename in sorted(os.listdir(bin_dir)):
            path = os.path.join(bin_dir, filename)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                artifacts.executables.append(os.path.abspath(path))
    mod_dirs = set()
    for dirpath, _dirs, files in os.walk(prefix):
        for filename in files:
            if filename.endswith(".mod"):
                mod_dirs.add(dirpath)
                artifacts.modules.append(filename[:-4].lower())
    artifacts.modules.sort()
    if mod_dirs:
        artifacts.include_dir = os.path.abspath(sorted(mod_dirs, key=len)[0])
    elif os.path.isdir(os.path.join(prefix, "include")):
        artifacts.include_dir = os.path.abspath(os.path.join(prefix, "include"))
    pc_dir = os.path.join(lib, "pkgconfig")
    valid = [p for p in pc_found if pc_is_valid(p)]
    for broken in sorted(set(pc_found) - set(valid)):
        log(f"{broken}: its directories do not exist (a broken .pc of the package): FoBiS writes its own")
    existing = {os.path.basename(p)[:-3] for p in valid}
    described = {library_stem(p) for p in valid}  # a valid .pc names the package, not always the library
    for library in artifacts.libraries:
        stem = library_stem(library)
        if stem in existing or stem in described or (library.endswith((".so", ".dylib")) and _static_twin(library)):
            continue
        if valid and os.path.dirname(library) != os.path.abspath(lib):
            continue  # a library elsewhere that the package's own valid .pc describes
        os.makedirs(pc_dir, exist_ok=True)
        include_rel = os.path.relpath(artifacts.include_dir or os.path.join(prefix, "include"), prefix)
        lib_rel = os.path.relpath(os.path.dirname(library), prefix)
        spec = PkgConfigSpec(name=stem, version=version.lstrip("v"), description=description or name)
        path = write_pc(spec, library, prefix, lib_rel, include_rel, pc_dir)
        existing.add(stem)
        log(f"wrote {path}")
    ours = sorted(os.path.abspath(os.path.join(pc_dir, f)) for f in os.listdir(pc_dir)) if os.path.isdir(pc_dir) else []
    artifacts.pc_files = ours + sorted(p for p in valid if p not in ours)  # lib/pkgconfig first
    return artifacts


def pc_is_valid(path: str) -> bool:
    """Whether the directories a ``.pc`` file points to (``-L``, ``-I`` after variable expansion) exist."""
    values: dict[str, str] = {}
    flags = []
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return False
    expand = re.compile(r"\$\{(\w+)\}")
    for line in lines:
        if "=" in line and ":" not in line.split("=", 1)[0]:
            key, _, value = line.partition("=")
            values[key.strip()] = expand.sub(lambda m: values.get(m.group(1), ""), value.strip())
        elif line.startswith(("Libs:", "Cflags:")):
            flags += expand.sub(lambda m: values.get(m.group(1), ""), line.split(":", 1)[1]).split()
    dirs = [f[2:] for f in flags if f.startswith(("-L", "-I"))]
    return all(d and os.path.isdir(d) for d in dirs)


def _static_twin(library: str) -> bool:
    stem = library.rsplit(".", 1)[0]
    return os.path.isfile(stem + ".a")


# ── fobis ─────────────────────────────────────────────────────────────────────


def _fobis(*args: str) -> list[str]:
    from ..utils import fobis_command

    return [*fobis_command(), *args]


def fobos_modes(src: str, fobos: str = "fobos") -> list[str]:
    """The modes of a fobos (``fobis build --lmodes``); a fobos without modes has the single mode ''."""
    output = run(_fobis("build", "--lmodes", "-f", fobos), src)
    modes = re.findall(r'-\s+"([^"]+)"', output)
    return modes or [""]


def mode_facts(src: str, mode: str, fobos: str = "fobos") -> dict:
    """Compiler name and library kind of a mode (``fobis introspect --compiler --buildoptions``)."""
    args = ["introspect", "--compiler", "--buildoptions", "-f", fobos] + (["--mode", mode] if mode else [])
    output = run(_fobis(*args), src)
    try:
        data = json.loads(output[output.index("{") :])
    except ValueError as error:
        raise BackendError(f"cannot read the modes of {src}: {error}") from error
    return {
        "compiler": data.get("compiler", {}).get("name", "").lower(),
        "mklib": data.get("buildoptions", {}).get("mklib", ""),
    }


def choose_mode(src: str, family: str, fobos: str = "fobos", log: Log = _quiet) -> str:
    """
    The mode a package is built in for compiler *family*: a mode of that compiler building a library (a static one
    first), else one building a program; a mode's compiler wins over the command line in FoBiS, so a package with no
    mode for the family cannot be built for it (BackendError naming its modes).
    """
    modes = fobos_modes(src, fobos)
    facts = {mode: mode_facts(src, mode, fobos) for mode in modes}
    matching = [m for m in modes if facts[m]["compiler"] == family.lower()]
    if not matching:
        listed = ", ".join(f"{m or '(default)'} ({facts[m]['compiler']})" for m in modes)
        raise BackendError(
            f"no mode of the package's fobos uses the {family} compiler: {listed} (choose one with --mode)"
        )
    ranked = sorted(matching, key=lambda m: {"static": 0, "shared": 1}.get(facts[m]["mklib"], 2))
    log(f"mode {ranked[0] or '(default)'} ({facts[ranked[0]]['compiler']}, {facts[ranked[0]]['mklib'] or 'program'})")
    return ranked[0]


def install_fobis(
    src: str, toolchain: Toolchain, prefix: str, mode: str | None = None, fobos: str = "fobos", log: Log = _quiet
) -> None:
    """Build a FoBiS package in *src* with *toolchain* and copy its tracked artifacts into *prefix*."""
    from ..Fetcher import Fetcher

    if _has_dependencies(os.path.join(src, fobos)):  # the package's own dependencies, as its users would fetch them
        log(run(_fobis("fetch", "-f", fobos), src).strip())
    chosen = mode if mode is not None else choose_mode(src, toolchain.family, fobos, log)
    args = ["build", "--track-build", "-f", fobos, "--fc", toolchain.path, "--force-compile", "--quiet"]
    args += ["--mode", chosen] if chosen else []
    if toolchain.mpi:
        args.append("--mpi")
    if toolchain.cflags or toolchain.lflags:  # appended to the mode's flags (a --cflags would replace them)
        args += ["--variant", "pkg", "--variant-cflags", toolchain.cflags, "--variant-lflags", toolchain.lflags]
    log(run(_fobis(*args), src).strip())
    drop_test_programs(src, log)
    messages: list[str] = []
    fetcher = Fetcher(deps_dir=src, print_n=log, print_w=messages.append)
    if not fetcher._install_artifacts(src, prefix, "bin", "lib", "include"):
        raise BackendError(f"the build of {src} produced nothing to install ({'; '.join(messages)})")


def _has_dependencies(fobos: str) -> bool:
    import configparser

    config = configparser.RawConfigParser(strict=False)
    try:
        config.read(fobos, encoding="utf-8")
    except configparser.Error:
        return False
    return config.has_section("dependencies") and any(
        k not in ("deps_dir", "transitive") for k in config.options("dependencies")
    )


def drop_test_programs(src: str, log: Log = _quiet) -> None:
    """
    Forget the tracked programs whose source lies under a test or example directory (`NOT_PROVIDED_DIRS`): a mode
    building every program of a package builds its tests too, and they are not applications to install.
    """
    from .sources import FORTRAN_SUFFIXES, NOT_PROVIDED_DIRS

    sources: dict[str, list[str]] = {}
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for filename in filenames:
            if filename.lower().endswith(FORTRAN_SUFFIXES):
                sources.setdefault(filename, []).append(os.path.relpath(os.path.join(dirpath, filename), src))
    for dirpath, _dirnames, filenames in os.walk(src):
        for filename in filenames:
            if not (filename.startswith(".") and filename.endswith(".track_build")):
                continue
            program = filename[1 : -len(".track_build")]
            paths = sources.get(program, [])
            if paths and all(set(p.lower().split(os.sep)[:-1]) & NOT_PROVIDED_DIRS for p in paths):
                os.remove(os.path.join(dirpath, filename))
                log(f"not installed: {paths[0]} (a test or example)")


# ── fpm ───────────────────────────────────────────────────────────────────────


# position-independent code, so a fetched fpm library also links into a shared library of the project
PIC_FLAGS = {"gnu": "-fPIC", "intel": "-fPIC", "intel_nextgen": "-fPIC", "nvfortran": "-fPIC", "pgi": "-fPIC",
             "amd": "-fPIC", "opencoarrays-gnu": "-fPIC"}  # fmt: skip


def install_fpm(
    src: str,
    toolchain: Toolchain,
    prefix: str,
    log: Log = _quiet,
    applications: bool = True,
    warn: Log = _quiet,
    name: str = "",
) -> None:
    """
    Build an fpm package with fpm itself (its manifest is the build: flags, preprocessing, C sources, its own
    dependencies) and the consumer's compiler; fpm missing is an error: FoBiS never compiles an fpm package itself.

    The library is built first, alone: a copy of the package whose manifest drops executables and examples (fpm
    compiles every program it finds, and a demo that does not compile, as in M_CLI2 1.0.0, must not stop a library
    that does; tests are not built without ``--tests``). Every library archive and module file of its build tree is
    installed (fpm puts the objects of the package's dependencies in the package's archive). With *applications*,
    ``fpm install`` then installs the programs of the manifest without its examples; a failure there is a warning.
    """
    fpm = shutil.which("fpm")
    if not fpm:
        raise BackendError(
            "it is an fpm package and fpm is not on PATH: install fpm (https://fpm.fortran-lang.org) to build it"
        )
    flags = " ".join(f for f in (PIC_FLAGS.get(toolchain.family, ""), toolchain.cflags) if f)
    options = ["--compiler", toolchain.path, "--profile", "release"]
    options += ["--flag", flags] if flags else []
    options += ["--c-compiler", toolchain.cc] if toolchain.cc and shutil.which(toolchain.cc) else []
    with tempfile.TemporaryDirectory(prefix="fobis-fpm-") as scratch:
        work = os.path.join(scratch, os.path.basename(os.path.normpath(src)))
        shutil.copytree(
            src, work, symlinks=True, ignore=lambda d, names: {".git", "build"} & set(names) if d == src else []
        )
        with open(os.path.join(work, "fpm.toml"), encoding="utf-8") as fh:
            original = fh.read()
        _write_manifest(work, original, programs=False)
        log(run([fpm, "build", *options], work).strip())
        _install_build_tree(os.path.join(work, "build"), prefix)
        if not applications:
            return
        _write_manifest(work, original, programs=True)
        # fpm 0.12 cannot read back the build/cache.toml it wrote (a git dependency's rev): it resolves again
        with contextlib.suppress(FileNotFoundError):
            os.remove(os.path.join(work, "build", "cache.toml"))
        try:
            log(run([fpm, "install", "--prefix", os.path.abspath(prefix), *options], work).strip())
        except BackendError as error:
            warn(f"warning: the applications of {name or os.path.basename(src)} were not installed: {error}")


def _write_manifest(root: str, text: str, programs: bool) -> None:
    """The package's fpm.toml without its examples and, unless *programs*, without its executables."""
    from ..fpm import FpmError, dump_toml, load_toml

    try:
        manifest = load_toml(text)
    except (FpmError, ValueError) as error:
        raise BackendError(f"{os.path.join(root, 'fpm.toml')}: {error}") from error
    build = manifest.get("build") if isinstance(manifest.get("build"), dict) else {}
    manifest["build"] = {**build, "auto-examples": False} | ({} if programs else {"auto-executables": False})
    manifest.pop("example", None)
    if not programs:
        manifest.pop("executable", None)
    with open(os.path.join(root, "fpm.toml"), "w", encoding="utf-8") as fh:
        fh.write(dump_toml(manifest))


def _install_build_tree(build: str, prefix: str) -> None:
    """Every library archive and module file fpm made (its fetched dependencies' sources aside)."""
    for directory in sorted(os.listdir(build)) if os.path.isdir(build) else []:
        if directory == "dependencies" or not os.path.isdir(os.path.join(build, directory)):
            continue
        for dirpath, _dirnames, filenames in os.walk(os.path.join(build, directory)):
            for filename in sorted(filenames):
                if filename.startswith("lib") and filename.endswith(".a"):
                    target = os.path.join(prefix, "lib")
                elif filename.endswith((".mod", ".smod")):
                    target = os.path.join(prefix, "include")
                else:
                    continue
                os.makedirs(target, exist_ok=True)
                shutil.copy2(os.path.join(dirpath, filename), target)


def _after_brace(text: str) -> str:
    return text[text.index("{") :] if "{" in text else "{}"


BACKENDS = {"fobis": install_fobis, "fpm": install_fpm}


def install(
    backend: str,
    src: str,
    toolchain: Toolchain,
    prefix: str,
    name: str,
    version: str,
    description: str = "",
    mode: str | None = None,
    recipe: object = None,
    prefixes: tuple[str, ...] = (),
    log: Log = _quiet,
    applications: bool = True,
    warn: Log = _quiet,
) -> Artifacts:
    """Build and install a package with *backend*; the `Artifacts` of the prefix (``.pc`` files written)."""
    os.makedirs(prefix, exist_ok=True)
    if backend == "fobis":
        install_fobis(src, toolchain, prefix, mode=mode, log=log)
    elif backend == "fpm":
        install_fpm(src, toolchain, prefix, log=log, applications=applications, warn=warn, name=name)
    elif backend in ("cmake", "make", "recipe"):
        from .recipe import install_with

        install_with(backend, src, toolchain, prefix, recipe=recipe, prefixes=prefixes, log=log)
    else:
        raise BackendError(f"no backend can build {src}: no fobos, fpm.toml, CMakeLists.txt or Makefile, and no recipe")
    artifacts = collect(prefix, name, version, description, log)
    if not (artifacts.libraries or artifacts.executables or artifacts.modules):
        raise BackendError(f"the {backend} build of {name} installed nothing into {prefix}")
    return artifacts
