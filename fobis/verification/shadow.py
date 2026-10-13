"""shadow.py — shadow modes: any fobos mode rebuilt with checking flags, in its own build directory.

A shadow keeps everything of the mode (sources, includes, libraries, preprocessor flags, MPI/OpenMP settings) and
changes only the compiler flags: it removes the mode's flags that would defeat it (optimisation, fast math,
conflicting checks or standards) and adds its own. Its objects go to ``.fobis/shadow/<mode>-<shadow>/``, never to
the mode's build directory.

- ``checks``: unoptimised, debug information, runtime checks (bounds, pointers, ...), floating-point traps
  (invalid, division by zero, overflow), reals initialised to a signalling NaN where the compiler can.
- ``sanitize``: AddressSanitizer (+ UndefinedBehaviorSanitizer with gfortran).
- ``strict``: standard conformance (Fortran 2018), warnings as errors.
- ``none``: the mode's own flags, in its own build directory (the baseline cells of ``fobis matrix``: the user's
  build directory is never touched).

The flags are a table per compiler family, each entry checked on a real build of small programs holding one
defect each (an index out of bounds, an uninitialised real, a division by zero, a heap overflow through an
assumed-size dummy, a ``real*8`` declaration): what each family catches is recorded in ``CAUGHT`` and documented.
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

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass

SHADOW_ROOT = os.path.join(".fobis", "shadow")
NONE = "none"
SHADOWS = ("checks", "sanitize", "strict", NONE)

# compiler name of the fobos -> flag family
FAMILIES = {
    "gnu": "gnu",
    "opencoarrays-gnu": "gnu",
    "intel_nextgen": "intel",
    "intel": "intel",
    "nvfortran": "nvfortran",
    "pgi": "nvfortran",
}

# flags taking their value as the next word
_WITH_VALUE = {"-fp-model", "-stand", "-check", "-warn", "-init"}

_OPTIMISATION = (r"-O\S*", r"-Ofast", r"-fast", r"-flto\S*", r"-ipo\S*", r"-ip")
_FAST_MATH = (r"-ffast-math", r"-funsafe-math-optimizations", r"-fp-model", r"-Mfprelaxed\S*", r"-fno-protect-parens")


class ShadowError(Exception):
    """An unknown shadow, or a shadow not available for the mode's compiler."""


@dataclass(frozen=True)
class ShadowFlags:
    """The flags of one shadow for one compiler family.

    ``compile`` and ``link`` are added to the mode's cflags and lflags; the mode's flags matching a ``drop``
    pattern (whole words) are removed first, a flag in ``_WITH_VALUE`` together with its value.
    """

    compile: str
    link: str = ""
    drop: tuple[str, ...] = ()


_CHECKS_DROP = (*_OPTIMISATION, *_FAST_MATH)

TABLE: dict[tuple[str, str], ShadowFlags] = {
    ("checks", "gnu"): ShadowFlags(
        "-O0 -g -fcheck=all -ffpe-trap=invalid,zero,overflow -finit-real=snan -finit-integer=-9999 -finit-derived "
        "-fbacktrace",
        drop=(*_CHECKS_DROP, r"-fcheck\S*", r"-fno-check\S*", r"-ffpe-trap\S*", r"-finit-\S+", r"-fno-backtrace"),
    ),
    ("checks", "intel"): ShadowFlags(
        "-O0 -g -check all -fpe0 -init=snan,arrays -traceback",
        drop=(*_CHECKS_DROP, r"-check", r"-nocheck", r"-fpe\S*", r"-init\S*", r"-notraceback"),
    ),
    ("checks", "nvfortran"): ShadowFlags(
        "-O0 -g -Mbounds -Mchkptr -Ktrap=fp -Minit-real=snan -traceback",
        drop=(*_CHECKS_DROP, r"-Mnobounds", r"-Ktrap\S*", r"-Minit-real\S*", r"-Mnoframe"),
    ),
    ("sanitize", "gnu"): ShadowFlags(
        "-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined",
        "-fsanitize=address,undefined",
        drop=(*_OPTIMISATION, r"-fsanitize\S*", r"-fomit-frame-pointer"),
    ),
    ("sanitize", "intel"): ShadowFlags(
        "-O1 -g -fsanitize=address",
        "-fsanitize=address",
        drop=(*_OPTIMISATION, r"-fsanitize\S*"),
    ),
    ("strict", "gnu"): ShadowFlags("-std=f2018 -pedantic -Werror", drop=(r"-std=\S+", r"-pedantic\S*", r"-w")),
    ("strict", "intel"): ShadowFlags(
        "-stand f18 -warn stderrors -warn errors", drop=(r"-stand", r"-nostand", r"-std\S*", r"-w")
    ),
    ("strict", "nvfortran"): ShadowFlags("-Mstandard -Werror", drop=(r"-Mstandard", r"-w", r"-Minform=\S+")),
}

# what was verified, on real builds: the reason a shadow is missing, and what each family catches
UNAVAILABLE = {  # by family
    ("sanitize", "nvfortran"): "nvfortran has no sanitizer (nvfortran 26.1: 'Unknown switch: -fsanitize=address')",
}
UNAVAILABLE_FOR = {  # by fobos compiler name, when one compiler of a family lacks what the others have
    (
        "sanitize",
        "intel",
    ): "ifort ignores -fsanitize=address (ifort 2024.2: 'warning #10006: ignoring unknown option'): "
    "use ifx (compiler = intel_nextgen)",
}
CAUGHT = {
    ("checks", "gnu"): "bounds (located), uninitialised real (SIGFPE), division by zero (SIGFPE)",
    ("checks", "intel"): "bounds (located), uninitialised real (located), division by zero (ifx and ifort)",
    ("checks", "nvfortran"): "bounds (located), division by zero (SIGFPE); an uninitialised real becomes a quiet "
    "NaN (-Minit-real=snan writes 7FC00000), not a trap",
    ("sanitize", "gnu"): "stack and heap overflows, including through an assumed-size dummy",
    ("sanitize", "intel"): "ifx: stack and global overflows; a heap overflow through an assumed-size dummy is missed",
    ("strict", "gnu"): "extensions as errors (real*8)",
    ("strict", "intel"): "extensions as errors (real*8)",
    ("strict", "nvfortran"): "extensions as errors (real*8)",
}
VERIFIED_WITH = "gfortran 16.0.1, ifx 2025.3.3, ifort 2024.2 (checks, strict), nvfortran 26.1"


def family(compiler: str | None) -> str | None:
    """The flag family of a fobos ``compiler`` value (None: no shadow table for it)."""
    return FAMILIES.get((compiler or "gnu").lower())


def flags_for(shadow: str, compiler: str | None) -> ShadowFlags:
    """The flags of *shadow* for *compiler*; `ShadowError` when there are none."""
    if shadow not in SHADOWS:
        raise ShadowError(f"unknown shadow {shadow!r} (available: {', '.join(SHADOWS)})")
    if shadow == NONE:
        return ShadowFlags("")
    fam = family(compiler)
    if fam is None:
        raise ShadowError(
            f"no shadow flags for compiler {compiler!r} (known: {', '.join(sorted(FAMILIES))}): "
            "set the compiler of the mode, or add the flags to a mode of your own"
        )
    reason = UNAVAILABLE.get((shadow, fam)) or UNAVAILABLE_FOR.get((shadow, (compiler or "gnu").lower()))
    if reason:
        raise ShadowError(f"shadow {shadow} is not available: {reason}")
    return TABLE[shadow, fam]


def _units(flags: str | None) -> list[tuple[str, ...]]:
    """*flags* as units: a flag of ``_WITH_VALUE`` together with its value, any other word alone."""
    words = shlex.split(flags or "")
    units: list[tuple[str, ...]] = []
    while words:
        word = words.pop(0)
        units.append((word, words.pop(0)) if word in _WITH_VALUE and words else (word,))
    return units


def transform(flags: str | None, add: str, drop: tuple[str, ...]) -> str:
    """*flags* without the flags matching *drop* (with their value), then the flags of *add* not already there."""
    patterns = [re.compile(p + r"$") for p in drop]
    kept = [u for u in _units(flags) if not any(p.match(u[0]) for p in patterns)]
    added = [u for u in _units(add) if u not in kept]
    return " ".join(" ".join(u) for u in kept + added)


def build_dir(mode: str | None, shadow: str) -> str:
    """Where the objects and programs of *mode* rebuilt as *shadow* go (relative to the project root)."""
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{mode or 'default'}-{shadow}")
    return os.path.join(SHADOW_ROOT, name)


def apply(cliargs, shadow: str, mode: str | None) -> ShadowFlags | None:
    """Turn the loaded *cliargs* of *mode* into its *shadow*: flags transformed, build directory moved.

    Commands without compiler flags (``test``, ``run``) get only the build directory: the builds they start check
    the shadow against the mode's compiler.
    """
    if not hasattr(cliargs, "cflags"):
        if shadow not in SHADOWS:
            raise ShadowError(f"unknown shadow {shadow!r} (available: {', '.join(SHADOWS)})")
        cliargs.build_dir = build_dir(mode, shadow)
        return None
    flags = flags_for(shadow, getattr(cliargs, "compiler", None))
    cflags = transform(cliargs.cflags, flags.compile, flags.drop)
    if not re.search(r"(^|\s)-c(\s|$)", cflags):
        cflags = "-c " + cflags  # FoBiS compiles with the mode's cflags: -c must stay
    cliargs.cflags = cflags
    cliargs.lflags = transform(getattr(cliargs, "lflags", ""), flags.link, flags.drop)
    cliargs.build_dir = build_dir(mode, shadow)
    return flags
