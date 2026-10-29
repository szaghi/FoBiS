"""
Recipes: how to build a package that does not describe itself (CMake, make, anything else).

A recipe is a small TOML file::

    schema     = 1
    backend    = "cmake"                  # cmake, make or recipe (explicit steps)
    depends    = ["https://github.com/y/kinds-lib :: semver=^2"]
    externals  = ["hdf5", "lapack"]       # found by the build (and Externals.py), never built
    cmake-args = ["-DENABLE_TESTS=OFF"]
    make-args  = ["-f", "Makefile.gnu"]
    steps      = ["./configure FC={fc} --prefix={prefix}", "make -j{jobs}", "make install"]
    env        = { OMP_NUM_THREADS = "1" }

It lives in the package's repository (``fortran-recipe.toml``, preferred), or in an index (``recipe = PATH``,
relative to the index) from where ``fobis add`` copies it into the project: builds never depend on an index.

Placeholders of ``steps``: ``{fc}`` ``{cc}`` ``{fflags}`` ``{lflags}`` ``{prefix}`` ``{jobs}`` ``{src}`` ``{build}``.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

from .backends import BackendError, Log, _quiet, run
from .toolchain import Toolchain

RECIPE_FILE = "fortran-recipe.toml"
BACKENDS = ("cmake", "make", "recipe")
_KEYS = {"schema", "backend", "depends", "externals", "cmake-args", "make-args", "steps", "env"}
PLACEHOLDERS = ("fc", "cc", "fflags", "lflags", "prefix", "jobs", "src", "build")


class RecipeError(BackendError):
    """A recipe is not valid."""


@dataclass
class Recipe:
    backend: str
    depends: list[str] = field(default_factory=list)
    externals: list[str] = field(default_factory=list)
    cmake_args: list[str] = field(default_factory=list)
    make_args: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    origin: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}


def _strings(value, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise RecipeError(f"{where} must be a list of strings")
    return list(value)


def parse_recipe(text: str, origin: str = "") -> Recipe:
    """Parse and validate a recipe; RecipeError names the problem."""
    from ..fpm import FpmError, load_toml

    where = f"recipe {origin}: " if origin else "recipe: "
    try:
        data = load_toml(text)
    except (FpmError, ValueError) as error:
        raise RecipeError(where + f"not valid TOML: {error}") from error
    unknown = sorted(set(data) - _KEYS)
    if unknown:
        raise RecipeError(where + f"unknown key(s) {', '.join(unknown)}")
    if data.get("schema", 1) != 1:
        raise RecipeError(where + f"schema {data.get('schema')} is not 1: upgrade FoBiS")
    backend = data.get("backend", "")
    if backend not in BACKENDS:
        raise RecipeError(where + f"backend must be one of {', '.join(BACKENDS)}, not {backend!r}")
    try:
        recipe = Recipe(
            backend=backend,
            depends=_strings(data.get("depends", []), "depends"),
            externals=_strings(data.get("externals", []), "externals"),
            cmake_args=_strings(data.get("cmake-args", []), "cmake-args"),
            make_args=_strings(data.get("make-args", []), "make-args"),
            steps=_strings(data.get("steps", []), "steps"),
            env={str(k): str(v) for k, v in (data.get("env") or {}).items()},
            origin=origin,
        )
    except RecipeError as error:
        raise RecipeError(where + str(error)) from None
    if backend == "recipe" and not recipe.steps:
        raise RecipeError(where + "backend 'recipe' needs steps")
    for step in recipe.steps:
        try:
            step.format(**{p: "" for p in PLACEHOLDERS})
        except (KeyError, IndexError, ValueError) as error:
            raise RecipeError(
                where + f"step {step!r}: unknown placeholder {error} ({', '.join(PLACEHOLDERS)})"
            ) from None
    return recipe


def load_recipe(path: str) -> Recipe:
    with open(path, encoding="utf-8") as fh:
        return parse_recipe(fh.read(), origin=path)


def recipe_in(src: str) -> Recipe | None:
    """The recipe a source ships (``fortran-recipe.toml`` at its root), or None."""
    path = os.path.join(src, RECIPE_FILE)
    return load_recipe(path) if os.path.isfile(path) else None


def _jobs() -> str:
    return str(max(1, (os.cpu_count() or 2) // 2))


def _env(recipe: Recipe | None, toolchain: Toolchain, prefixes: list[str]) -> dict[str, str]:
    env = dict(os.environ)
    env.update({"FC": toolchain.path, "F77": toolchain.path, "F90": toolchain.path})
    if toolchain.cc and shutil.which(toolchain.cc):
        env["CC"] = shutil.which(toolchain.cc) or toolchain.cc
    if toolchain.cflags:
        env["FFLAGS"] = env["FCFLAGS"] = toolchain.cflags
    if toolchain.lflags:
        env["LDFLAGS"] = toolchain.lflags
    if prefixes:
        pc = [os.path.join(p, "lib", "pkgconfig") for p in prefixes]
        env["PKG_CONFIG_PATH"] = os.pathsep.join([*pc, env.get("PKG_CONFIG_PATH", "")]).strip(os.pathsep)
        env["CMAKE_PREFIX_PATH"] = os.pathsep.join([*prefixes, env.get("CMAKE_PREFIX_PATH", "")]).strip(os.pathsep)
    env.update(recipe.env if recipe else {})
    return env


def install_cmake(src, toolchain: Toolchain, prefix, recipe=None, prefixes=(), log: Log = _quiet) -> None:
    """Configure, build and install a CMake project with the toolchain."""
    if shutil.which("cmake") is None:
        raise BackendError("cmake is not on PATH")
    build = os.path.join(src, "_fobis_build")
    configure = [
        "cmake", "-S", src, "-B", build, "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_Fortran_COMPILER={toolchain.path}", f"-DCMAKE_INSTALL_PREFIX={os.path.abspath(prefix)}",
        "-DCMAKE_INSTALL_LIBDIR=lib",
    ]  # fmt: skip
    if toolchain.cc and shutil.which(toolchain.cc):
        configure.append(f"-DCMAKE_C_COMPILER={shutil.which(toolchain.cc)}")
    if toolchain.cflags:
        configure.append(f"-DCMAKE_Fortran_FLAGS={toolchain.cflags}")
    if toolchain.lflags:
        configure += [f"-DCMAKE_EXE_LINKER_FLAGS={toolchain.lflags}", f"-DCMAKE_SHARED_LINKER_FLAGS={toolchain.lflags}"]
    if prefixes:
        configure.append(f"-DCMAKE_PREFIX_PATH={';'.join(prefixes)}")
    configure += recipe.cmake_args if recipe else []
    env = _env(recipe, toolchain, list(prefixes))
    log(run(configure, src, log, env).strip()[-2000:])
    log(run(["cmake", "--build", build, "-j", _jobs()], src, log, env).strip()[-2000:])
    log(run(["cmake", "--install", build], src, log, env).strip()[-2000:])
    harvest_modules(build, prefix, log)


def install_make(src, toolchain: Toolchain, prefix, recipe=None, prefixes=(), log: Log = _quiet) -> None:
    """``./configure`` (when present), ``make``, ``make install`` with the toolchain; harvest when no install rule."""
    env = _env(recipe, toolchain, list(prefixes))
    args = recipe.make_args if recipe else []
    variables = [f"FC={toolchain.path}", f"F90={toolchain.path}", f"F77={toolchain.path}"]
    if toolchain.cflags:
        variables += [f"FFLAGS={toolchain.cflags}", f"FCFLAGS={toolchain.cflags}"]
    if os.path.isfile(os.path.join(src, "configure")):
        log(run(["sh", "./configure", f"--prefix={os.path.abspath(prefix)}"], src, log, env).strip()[-2000:])
    log(run(["make", f"-j{_jobs()}", *args, *variables], src, log, env).strip()[-2000:])
    install = ["make", *args, "install", f"PREFIX={os.path.abspath(prefix)}", f"prefix={os.path.abspath(prefix)}"]
    try:
        log(run(install, src, log, env).strip()[-2000:])
    except BackendError as error:  # most Makefiles of scientific codes have no install rule
        log(f"make install failed ({str(error).splitlines()[-1]}): harvesting what the build produced")
        harvest(src, prefix, log)
    harvest_modules(src, prefix, log)


def install_steps(src, toolchain: Toolchain, prefix, recipe: Recipe, prefixes=(), log: Log = _quiet) -> None:
    """Run the recipe's steps (bash, in the source directory) with the placeholders filled."""
    build = os.path.join(src, "_fobis_build")
    os.makedirs(build, exist_ok=True)
    values = {
        "fc": toolchain.path,
        "cc": shutil.which(toolchain.cc) or toolchain.cc if toolchain.cc else "cc",
        "fflags": toolchain.cflags,
        "lflags": toolchain.lflags,
        "prefix": os.path.abspath(prefix),
        "jobs": _jobs(),
        "src": src,
        "build": build,
    }
    env = _env(recipe, toolchain, list(prefixes))
    for step in recipe.steps:
        log(run(["bash", "-c", step.format(**values)], src, log, env).strip()[-2000:])
    if not any(os.scandir(prefix)):
        log("the steps installed nothing: harvesting what they built")
        harvest(src, prefix, log)


def harvest(tree: str, prefix: str, log: Log = _quiet) -> None:
    """Copy the libraries (``lib/``), module files (``include/``) and new executables (``bin/``) built in *tree*."""
    for dirpath, dirnames, filenames in os.walk(tree):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            if filename.startswith("lib") and filename.endswith((".a", ".so", ".dylib")):
                dest = "lib"
            elif filename.endswith(".mod"):
                dest = "include"
            elif os.access(path, os.X_OK) and _is_elf(path):
                dest = "bin"
            else:
                continue
            os.makedirs(os.path.join(prefix, dest), exist_ok=True)
            shutil.copy2(path, os.path.join(prefix, dest, filename))
            log(f"harvested {os.path.relpath(path, tree)} -> {dest}/")


def harvest_modules(tree: str, prefix: str, log: Log = _quiet) -> None:
    """Copy module files of the build tree when the install put none in the prefix (CMake installs none by default)."""
    for _dirpath, _dirs, files in os.walk(prefix):
        if any(f.endswith(".mod") for f in files):
            return
    for dirpath, dirnames, filenames in os.walk(tree):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for filename in filenames:
            if filename.endswith(".mod"):
                os.makedirs(os.path.join(prefix, "include"), exist_ok=True)
                shutil.copy2(os.path.join(dirpath, filename), os.path.join(prefix, "include", filename))
                log(f"module {filename} -> include/")


def _is_elf(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(4) == b"\x7fELF"
    except OSError:
        return False


def read_index_recipe(index_url: str, relpath: str) -> str:
    """The text of a recipe an index names (``recipe = PATH``, relative to the index)."""
    import tempfile
    import urllib.parse

    from .index import RegistryError, http_get, local_path, provider_of, run_git

    provider = provider_of(index_url)
    if provider in ("dir", "file"):
        base = local_path(index_url) or index_url
        root = base if provider == "dir" else os.path.dirname(base)
        path = os.path.normpath(os.path.join(root, relpath))
        if not os.path.isfile(path):
            raise RecipeError(f"the index {index_url} names recipe {relpath}, not found ({path})")
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    if provider == "http":
        try:
            return http_get(urllib.parse.urljoin(index_url, relpath)).decode("utf-8")
        except RegistryError as error:
            raise RecipeError(str(error)) from error
    with tempfile.TemporaryDirectory(prefix="fobis-recipe-") as scratch:
        result = run_git("clone", "--depth", "1", "--quiet", index_url, scratch)
        path = os.path.join(scratch, relpath)
        if result.returncode != 0 or not os.path.isfile(path):
            raise RecipeError(f"the index {index_url} names recipe {relpath}, not found in the repository")
        with open(path, encoding="utf-8") as fh:
            return fh.read()


def install_with(backend, src, toolchain: Toolchain, prefix, recipe=None, prefixes=(), log: Log = _quiet) -> None:
    """Dispatch to the cmake, make or recipe backend."""
    if backend == "cmake":
        install_cmake(src, toolchain, prefix, recipe, prefixes, log)
    elif backend == "make":
        install_make(src, toolchain, prefix, recipe, prefixes, log)
    elif backend == "recipe":
        if recipe is None:
            raise RecipeError("backend 'recipe' without a recipe")
        install_steps(src, toolchain, prefix, recipe, prefixes, log)
    else:
        raise BackendError(f"unknown backend {backend}")
