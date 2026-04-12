"""
Externals.py — Automatic external system library detection.

Implements issue #169: probe system for MPI, BLAS, LAPACK, HDF5, NetCDF,
FFTW via pkg-config, compiler wrapper scripts, or explicit prefix paths.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field

from .utils import print_fake, syswork


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ExternalFlags:
    """Compiler and linker flags resolved for one or more external libraries."""

    cflags: str = ""
    lflags: str = ""
    includes: list[str] = field(default_factory=list)
    lib_dirs: list[str] = field(default_factory=list)

    def merge(self, other: "ExternalFlags") -> "ExternalFlags":
        """Return a new ExternalFlags that is the union of self and other."""
        return ExternalFlags(
            cflags=" ".join(filter(None, [self.cflags, other.cflags])).strip(),
            lflags=" ".join(filter(None, [self.lflags, other.lflags])).strip(),
            includes=list(dict.fromkeys(self.includes + other.includes)),
            lib_dirs=list(dict.fromkeys(self.lib_dirs + other.lib_dirs)),
        )

    def is_empty(self) -> bool:
        return not any([self.cflags, self.lflags, self.includes, self.lib_dirs])


# ---------------------------------------------------------------------------
# Probe helpers
# ---------------------------------------------------------------------------


def _pkg_config(package: str) -> ExternalFlags | None:
    """Run pkg-config for *package* and return flags, or None on failure."""
    if not shutil.which("pkg-config"):
        return None
    cflags_result = syswork(f"pkg-config --cflags {package}")
    libs_result = syswork(f"pkg-config --libs {package}")
    if cflags_result[0] != 0 or libs_result[0] != 0:
        return None
    cflags = cflags_result[1].strip()
    lflags = libs_result[1].strip()
    includes = [f[2:] for f in cflags.split() if f.startswith("-I")]
    lib_dirs = [f[2:] for f in lflags.split() if f.startswith("-L")]
    return ExternalFlags(cflags=cflags, lflags=lflags, includes=includes, lib_dirs=lib_dirs)


def _probe_mpi() -> ExternalFlags | None:
    """Detect MPI via mpifort --showme or mpif90 --showme."""
    for wrapper in ("mpifort", "mpif90", "mpiifort", "mpiifx"):
        if not shutil.which(wrapper):
            continue
        comp = syswork(f"{wrapper} --showme:compile")
        link = syswork(f"{wrapper} --showme:link")
        if comp[0] == 0 and link[0] == 0:
            cflags = comp[1].strip()
            lflags = link[1].strip()
            includes = [f[2:] for f in cflags.split() if f.startswith("-I")]
            lib_dirs = [f[2:] for f in lflags.split() if f.startswith("-L")]
            return ExternalFlags(cflags=cflags, lflags=lflags, includes=includes, lib_dirs=lib_dirs)
        # Intel MPI style: -show
        show = syswork(f"{wrapper} -show")
        if show[0] == 0:
            tokens = show[1].strip().split()
            cflags_parts = [t for t in tokens if t.startswith("-I") or t.startswith("-D")]
            lflags_parts = [t for t in tokens if t.startswith("-L") or t.startswith("-l")]
            cflags = " ".join(cflags_parts)
            lflags = " ".join(lflags_parts)
            includes = [f[2:] for f in cflags_parts if f.startswith("-I")]
            lib_dirs = [f[2:] for f in lflags_parts if f.startswith("-L")]
            return ExternalFlags(cflags=cflags, lflags=lflags, includes=includes, lib_dirs=lib_dirs)
    # fallback: pkg-config
    return _pkg_config("ompi-fort")


def _probe_hdf5() -> ExternalFlags | None:
    """Detect HDF5 Fortran via pkg-config or h5fc -show."""
    flags = _pkg_config("hdf5_fortran")
    if flags:
        return flags
    for wrapper in ("h5pfc", "h5fc"):
        if not shutil.which(wrapper):
            continue
        result = syswork(f"{wrapper} -show")
        if result[0] == 0:
            tokens = result[1].strip().split()
            cflags = " ".join(t for t in tokens if t.startswith("-I") or t.startswith("-D"))
            lflags = " ".join(t for t in tokens if t.startswith("-L") or t.startswith("-l"))
            includes = [t[2:] for t in tokens if t.startswith("-I")]
            lib_dirs = [t[2:] for t in tokens if t.startswith("-L")]
            return ExternalFlags(cflags=cflags, lflags=lflags, includes=includes, lib_dirs=lib_dirs)
    return None


def _probe_netcdf() -> ExternalFlags | None:
    """Detect NetCDF Fortran via nc-config or nf-config."""
    for tool in ("nf-config", "nc-config"):
        if not shutil.which(tool):
            continue
        ff = syswork(f"{tool} --fflags")
        fl = syswork(f"{tool} --flibs")
        if ff[0] == 0 and fl[0] == 0:
            cflags = ff[1].strip()
            lflags = fl[1].strip()
            includes = [f[2:] for f in cflags.split() if f.startswith("-I")]
            lib_dirs = [f[2:] for f in lflags.split() if f.startswith("-L")]
            return ExternalFlags(cflags=cflags, lflags=lflags, includes=includes, lib_dirs=lib_dirs)
    return _pkg_config("netcdf")


def _probe_prefix(prefix: str, lib_names: list[str]) -> ExternalFlags:
    """Probe an explicit prefix directory for include/ and lib/."""
    includes = []
    lib_dirs = []
    inc_dir = os.path.join(prefix, "include")
    lib_dir = os.path.join(prefix, "lib")
    if os.path.isdir(inc_dir):
        includes.append(inc_dir)
    if os.path.isdir(lib_dir):
        lib_dirs.append(lib_dir)
    cflags = " ".join(f"-I{i}" for i in includes)
    lflags = " ".join(f"-L{d}" for d in lib_dirs)
    lflags += " " + " ".join(f"-l{n}" for n in lib_names)
    lflags = lflags.strip()
    return ExternalFlags(cflags=cflags, lflags=lflags, includes=includes, lib_dirs=lib_dirs)


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

_PROBERS: dict[str, Callable[[], ExternalFlags | None]] = {
    "mpi": _probe_mpi,
    "hdf5": _probe_hdf5,
    "netcdf": _probe_netcdf,
    "blas": lambda: _pkg_config("blas") or _pkg_config("openblas"),
    "lapack": lambda: _pkg_config("lapack"),
    "fftw": lambda: _pkg_config("fftw3"),
    "fftw3": lambda: _pkg_config("fftw3"),
    "openblas": lambda: _pkg_config("openblas"),
}

_LIB_NAMES: dict[str, list[str]] = {
    "blas": ["blas"],
    "openblas": ["openblas"],
    "lapack": ["lapack"],
    "fftw": ["fftw3"],
    "fftw3": ["fftw3"],
    "hdf5": ["hdf5_fortran", "hdf5"],
    "netcdf": ["netcdff", "netcdf"],
    "mpi": ["mpi_usempif08", "mpi_mpifh", "mpi"],
}


class ExternalResolver:
    """
    Resolve external system library flags by probing the environment.

    Parameters
    ----------
    print_n : callable, optional
    print_w : callable, optional
    """

    def __init__(
        self,
        print_n: Callable[..., None] | None = None,
        print_w: Callable[..., None] | None = None,
    ) -> None:
        self.print_n = print_n if print_n is not None else print_fake
        self.print_w = print_w if print_w is not None else print_fake

    def resolve(self, name: str, spec: str) -> ExternalFlags:
        """
        Probe system for *name* using *spec* (path or 'auto').

        Parameters
        ----------
        name : str
            Library name (e.g. 'mpi', 'blas', 'hdf5').
        spec : str
            Either ``'auto'`` or an explicit prefix path.

        Returns
        -------
        ExternalFlags
        """
        name_lower = name.lower()

        if spec.lower() != "auto":
            # explicit prefix
            lib_names = _LIB_NAMES.get(name_lower, [name_lower])
            flags = _probe_prefix(spec, lib_names)
            self.print_n(f"[externals] {name}: using explicit prefix {spec}")
            return flags

        # auto-probe
        prober = _PROBERS.get(name_lower)
        if prober:
            flags = prober()
            if flags and not flags.is_empty():
                self.print_n(f"[externals] {name}: auto-detected")
                return flags
            self.print_w(f"Warning: could not auto-detect external '{name}'")
            return ExternalFlags()

        self.print_w(
            f"Warning: no probe strategy for external '{name}'. "
            f"Known libraries: {', '.join(sorted(_PROBERS))}. "
            "Use an explicit prefix or install the library."
        )
        return ExternalFlags()

    def resolve_all(self, names: list[str], externals_map: dict[str, str]) -> ExternalFlags:
        """
        Resolve a list of external names and merge their flags.

        Parameters
        ----------
        names : list[str]
            External names to activate (subset of externals_map keys).
        externals_map : dict[str, str]
            Full {name: spec} mapping from the [externals] fobos section.

        Returns
        -------
        ExternalFlags
        """
        merged = ExternalFlags()
        for name in names:
            spec = externals_map.get(name, "auto")
            flags = self.resolve(name, spec)
            if flags is None:
                if self.print_w:
                    self.print_w(
                        f"Warning: external '{name}' could not be resolved. "
                        "Flags skipped. Check that the library is installed."
                    )
                continue
            merged = merged.merge(flags)
        return merged
