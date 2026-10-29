"""
Build backends: build a package's source with the consumer's toolchain and install it into a prefix.

Every backend has two roles. *Build*: configure, build and install with the CONSUMER's compiler (a ``.mod`` file works
only with the compiler that wrote it). *Consume*: one contract whatever the build system, `Artifacts` = an install
prefix with ``lib/`` (libraries), ``include/`` (module files), ``bin/`` (applications), a ``.pc`` file per library
(``lib/pkgconfig``) and the list of modules provided, so a FoBiS, CMake or make consumer links it the same way.

Backends: ``fobis`` (the package's fobos, the mode matching the compiler family), ``fpm`` (``fpm install`` when fpm is
on PATH, else the fpm.toml imported as a fobos and built by FoBiS).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
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
            cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=7200, stdin=subprocess.DEVNULL
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
    for dirpath, _dirs, files in os.walk(lib):
        for filename in sorted(files):
            if filename.endswith(LIB_SUFFIXES) and not filename.endswith(".pc"):
                artifacts.libraries.append(os.path.abspath(os.path.join(dirpath, filename)))
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
    existing = {f[:-3] for f in os.listdir(pc_dir)} if os.path.isdir(pc_dir) else set()
    for library in artifacts.libraries:
        stem = library_stem(library)
        if stem in existing or os.path.dirname(library) != os.path.abspath(lib):
            continue
        os.makedirs(pc_dir, exist_ok=True)
        include_rel = os.path.relpath(artifacts.include_dir or os.path.join(prefix, "include"), prefix)
        spec = PkgConfigSpec(name=stem, version=version.lstrip("v"), description=description or name)
        path = write_pc(spec, library, prefix, "lib", include_rel, pc_dir)
        existing.add(stem)
        log(f"wrote {path}")
    if os.path.isdir(pc_dir):
        artifacts.pc_files = sorted(os.path.abspath(os.path.join(pc_dir, f)) for f in os.listdir(pc_dir))
    return artifacts


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
    args = ["build", "--track-build", "-f", fobos, "--fc", toolchain.path, "--force-compile"]
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
    return config.has_section("dependencies") and any(k not in ("deps_dir", "transitive") for k in config.options("dependencies"))


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


def install_fpm(src: str, toolchain: Toolchain, prefix: str, log: Log = _quiet) -> None:
    """``fpm install`` with the toolchain when fpm is on PATH, else the manifest imported as a fobos (FoBiS builds)."""
    fpm = shutil.which("fpm")
    if fpm:
        flags = " ".join(f for f in (toolchain.cflags,) if f)
        cmd = [
            fpm,
            "install",
            "--prefix",
            os.path.abspath(prefix),
            "--compiler",
            toolchain.path,
            "--profile",
            "release",
        ]
        cmd += ["--flag", flags] if flags else []
        cmd += ["--c-compiler", toolchain.cc] if toolchain.cc and shutil.which(toolchain.cc) else []
        log(run(cmd, src).strip())
        # fpm installs a library only when the manifest says [install] library = true: the import builds it
        if collect(prefix, "", "").modules or not os.path.isdir(os.path.join(src, "src")):
            return
        log("fpm installed no library ([install] library is false): building it from the imported manifest")
    install_fpm_imported(src, toolchain, prefix, log)


def install_fpm_imported(src: str, toolchain: Toolchain, prefix: str, log: Log = _quiet) -> None:
    """
    Build an fpm package without fpm: its manifest imported as ``fobos.fpm-import`` (FoBiS's import reproduces fpm's
    flags), the release mode built, then the package assembled as fpm installs it: ``lib<name>.a`` from the objects
    of the library's source directory, the module files it defines, and the programs of its executable directories
    (never tests or examples).
    """
    from ..fpm import load_toml
    from .sources import FORTRAN_SUFFIXES, scan_modules

    with open(os.path.join(src, "fpm.toml"), encoding="utf-8") as fh:
        manifest = load_toml(fh.read())
    name = str(manifest.get("name") or os.path.basename(src))
    fobos = "fobos.fpm-import"
    run(_fobis("fpm", "import", "--compiler", toolchain.family, "-o", fobos, "--force"), src)
    modes = fobos_modes(src, fobos)
    if "lib-static" in modes:  # a module named after the package: the import made a library mode
        install_fobis(src, toolchain, prefix, mode="lib-static", fobos=fobos, log=log)
        _fpm_applications(src, manifest, prefix, modes, toolchain, fobos, log)
        return
    mode = next((m for m in modes if m.endswith("-release")), modes[0])
    library = manifest.get("library", {}) if isinstance(manifest.get("library"), dict) else {}
    lib_src = os.path.join(src, str(library.get("source-dir", "src")))
    # no library mode: a program using every module of the library makes FoBiS compile them all
    stub = os.path.join(lib_src, "fobis_pkg_all_modules.f90")
    modules = scan_modules(lib_src, provided=False) if os.path.isdir(lib_src) else []
    if modules:
        with open(stub, "w", encoding="utf-8") as fh:
            fh.write("program fobis_pkg_all_modules\n" + "".join(f"use {m}\n" for m in modules) + "end program\n")
    args = ["build", "-f", fobos, "--mode", mode, "--fc", toolchain.path, "--force-compile"]
    args += ["--target", os.path.relpath(stub, src)] if modules else []
    if toolchain.cflags or toolchain.lflags:
        args += ["--variant", "pkg", "--variant-cflags", toolchain.cflags, "--variant-lflags", toolchain.lflags]
    log(run(_fobis(*args), src).strip())
    facts = json.loads(_after_brace(run(_fobis("introspect", "--buildoptions", "-f", fobos, "--mode", mode), src)))
    options = facts["buildoptions"]
    build_dir = os.path.normpath(os.path.join(src, options["build_dir"]))
    obj_dir = os.path.join(build_dir, options["obj_dir"])
    mod_dir = os.path.join(build_dir, options["mod_dir"])
    if os.path.isdir(lib_src):
        objects = []
        for dirpath, _dirnames, filenames in os.walk(lib_src):
            for filename in sorted(filenames):
                if filename.lower().endswith((*FORTRAN_SUFFIXES, ".c")) and filename != os.path.basename(stub):
                    stem = filename if filename.endswith(".c") else os.path.splitext(filename)[0]
                    qualified = os.path.relpath(os.path.join(dirpath, filename), src).replace(os.sep, "_")
                    for candidate in (stem + ".o", qualified + ".o"):
                        if os.path.isfile(os.path.join(obj_dir, candidate)):
                            objects.append(os.path.join(obj_dir, candidate))
                            break
        if objects:
            os.makedirs(os.path.join(prefix, "lib"), exist_ok=True)
            archive = os.path.join(prefix, "lib", f"lib{name}.a")
            run(["ar", "rcs", archive, *objects], src, log)
        os.makedirs(os.path.join(prefix, "include"), exist_ok=True)
        for module in scan_modules(lib_src, provided=False):
            mod = os.path.join(mod_dir, module + ".mod")
            if os.path.isfile(mod):
                shutil.copy2(mod, os.path.join(prefix, "include"))
    if modules:
        os.remove(stub)
    _fpm_applications(src, manifest, prefix, modes, toolchain, fobos, log)


def _fpm_applications(src, manifest, prefix, modes, toolchain, fobos, log) -> None:
    """Build and copy the programs of the fpm executable directories (``app/`` by default): never tests or examples."""
    app_dirs = [
        os.path.join(src, str(e.get("source-dir", "app")))
        for e in (manifest.get("executable") or [{"source-dir": "app"}])
        if isinstance(e, dict)
    ]
    mode = next((m for m in modes if m.endswith("-release")), modes[0])
    build_dir = None
    for app_dir in sorted({d for d in app_dirs if os.path.isdir(d)}):
        for filename in sorted(os.listdir(app_dir)):
            if not filename.lower().endswith(FORTRAN_PROGRAM_SUFFIXES):
                continue
            target = os.path.relpath(os.path.join(app_dir, filename), src)
            log(
                run(
                    _fobis("build", "-f", fobos, "--mode", mode, "--fc", toolchain.path, "--target", target), src
                ).strip()
            )
            if build_dir is None:
                facts = json.loads(
                    _after_brace(run(_fobis("introspect", "--buildoptions", "-f", fobos, "--mode", mode), src))
                )
                build_dir = os.path.normpath(os.path.join(src, facts["buildoptions"]["build_dir"]))
            binary = os.path.join(build_dir, os.path.splitext(filename)[0])
            if os.path.isfile(binary) and os.access(binary, os.X_OK):
                os.makedirs(os.path.join(prefix, "bin"), exist_ok=True)
                shutil.copy2(binary, os.path.join(prefix, "bin"))


FORTRAN_PROGRAM_SUFFIXES = (".f90", ".f", ".f95", ".f03", ".f08", ".fpp", ".for")


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
    log: Log = _quiet,
) -> Artifacts:
    """Build and install a package with *backend*; the `Artifacts` of the prefix (``.pc`` files written)."""
    os.makedirs(prefix, exist_ok=True)
    if backend == "fobis":
        install_fobis(src, toolchain, prefix, mode=mode, log=log)
    elif backend == "fpm":
        install_fpm(src, toolchain, prefix, log=log)
    elif backend in ("cmake", "make"):
        raise BackendError(f"{name} is built with {backend}: not supported yet (fobis and fpm packages only)")
    else:
        raise BackendError(f"no backend can build {src}: no fobos, fpm.toml, CMakeLists.txt or Makefile, and no recipe")
    artifacts = collect(prefix, name, version, description, log)
    if not (artifacts.libraries or artifacts.executables or artifacts.modules):
        raise BackendError(f"the {backend} build of {name} installed nothing into {prefix}")
    return artifacts
