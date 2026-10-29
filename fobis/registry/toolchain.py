"""
The toolchain key: which compiler built an installed package.

A ``.mod`` file works only with the compiler (and version) that wrote it, and flags such as ``-fdefault-real-8``
change the ABI, so an installed library is filed under a key naming its compiler family and version plus a digest of
everything that may change the result: the compiler's resolved path and full ``--version`` line, MPI, the C compiler
and ALL the flags the consumer passed (conservative on purpose: a coarser key would link a library built with other
flags without a word). Example: ``gnu-16.2.0-3fa1c2d9``.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from dataclasses import dataclass

from ..Compiler import C_COMPILERS

FORTRAN_COMMANDS = {
    "gnu": "gfortran",
    "intel": "ifort",
    "intel_nextgen": "ifx",
    "nvfortran": "nvfortran",
    "pgi": "pgfortran",
    "amd": "amdflang",
    "lfortran": "lfortran",
    "nag": "nagfor",
    "ibm": "xlf2008_r",
    "g95": "g95",
    "opencoarrays-gnu": "caf",
}
MPI_COMMAND = "mpif90"


class ToolchainError(Exception):
    """The compiler of a toolchain is not available."""


@dataclass
class Toolchain:
    """A compiler (family, command and its identity), MPI, the C compiler and the consumer's flags."""

    family: str
    fc: str  # the Fortran command as invoked (gfortran, mpif90, a path)
    path: str  # resolved path
    version: str  # first line of --version
    cc: str = ""
    mpi: bool = False
    cflags: str = ""
    lflags: str = ""

    @property
    def version_number(self) -> str:
        match = re.search(r"(\d+\.\d+(?:\.\d+)?)", self.version)
        return match.group(1) if match else "unknown"

    @property
    def digest(self) -> str:
        text = "\n".join((self.family, self.path, self.version, self.cc, str(self.mpi), self.cflags, self.lflags))
        return hashlib.sha256(text.encode()).hexdigest()[:8]

    @property
    def key(self) -> str:
        return f"{self.family}-{self.version_number}-{self.digest}"

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "key": self.key,
            "family": self.family,
            "fc": self.fc,
            "path": self.path,
            "version": self.version,
            "cc": self.cc,
            "mpi": self.mpi,
            "cflags": self.cflags,
            "lflags": self.lflags,
        }


def compiler_version(command: str) -> str:
    """The first line of ``COMMAND --version`` ('' when it prints nothing)."""
    try:
        result = subprocess.run([command, "--version"], capture_output=True, text=True, timeout=60, check=False)
    except OSError:
        return ""
    lines = (result.stdout or result.stderr).strip().splitlines()
    return lines[0].strip() if lines else ""


def detect(
    family: str = "gnu", fc: str | None = None, mpi: bool = False, cflags: str = "", lflags: str = ""
) -> Toolchain:
    """
    The toolchain of a compiler family on this machine: *fc* overrides the family's command, *mpi* uses the MPI
    wrapper (``mpif90``).

    Raises
    ------
    ToolchainError
      unknown family, or the command is not on PATH
    """
    if family not in FORTRAN_COMMANDS and not fc:
        raise ToolchainError(f"unknown compiler family {family} ({', '.join(sorted(FORTRAN_COMMANDS))}, or --fc)")
    command = fc or (MPI_COMMAND if mpi else FORTRAN_COMMANDS[family])
    path = shutil.which(command)
    if path is None:
        raise ToolchainError(f"{command} not found on PATH (load its module, or name it with --fc)")
    cc_entry = C_COMPILERS.get(family, C_COMPILERS["custom"])
    cc = cc_entry[1].split()[0] if mpi else cc_entry[0]
    return Toolchain(
        family=family,
        fc=command,
        path=path,
        version=compiler_version(path),
        cc=cc,
        mpi=mpi,
        cflags=" ".join(cflags.split()),
        lflags=" ".join(lflags.split()),
    )
