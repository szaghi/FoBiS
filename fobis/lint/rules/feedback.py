"""feedback.py — rules whose evidence is the compiler's own report (``fobis lint --compiler-feedback LOG``).

These rules read nothing from the source: they turn the messages of a build log (nvfortran ``-Minfo``,
gfortran ``-fopt-info``) into findings on the reported lines. Without ``--compiler-feedback`` they report
nothing.
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

import re
from collections.abc import Iterator

from ..rule import Hit, LintContext, rule

_IMPLICIT_DATA_RE = re.compile(
    r"^Generating implicit (copy|copyin|copyout|create)\((.*)\)(?:\s*\[if not already present\])?$"
)
_SEQUENTIAL_RE = re.compile(r"^(?:Complex )?[Ll]oop carried dependence of (\S+) prevents parallelization")
_IMPLICIT_MAP_RE = re.compile(r"^Generating implicit map\((\w+):(.*)\)$")
_NOT_VECTORIZED_RE = re.compile(r"^not vectorized: (.*)$")
_FEEDBACK_NOTE = "Reported only with `fobis lint --compiler-feedback LOG` (see the linting guide)."


def _grouped(ctx: LintContext, compiler: str, pattern: re.Pattern) -> dict[int, list[re.Match]]:
    """Matches of *pattern* in the *compiler*'s messages for this file, grouped by line."""
    found: dict[int, list[re.Match]] = {}
    for message in ctx.feedback:
        if message.compiler == compiler:
            match = pattern.match(message.text)
            if match:
                found.setdefault(message.line, []).append(match)
    return found


@rule(
    "ACC001",
    "implicit-data-movement",
    summary="The compiler moves data implicitly for an OpenACC compute region (nvfortran: 'Generating implicit copy').",
    rationale=f"""
        When a compute region uses an array that no enclosing data region or `present` clause covers, the
        compiler inserts a copy for that launch. `[if not already present]` means the copy is skipped only if
        the data happens to be on the device: in a loop of kernel launches this silently becomes a host-device
        transfer per launch, usually the dominant cost. Keep the data resident (`!$acc enter data`, a `data`
        region around the loop, `declare create`) and state it with `present(...)` or `default(present)`,
        which also turns a missing device copy into a runtime error instead of a slow transfer.
        {_FEEDBACK_NOTE}
        """,
    bad="""
        !$acc parallel loop          ! nvfortran: Generating implicit copy(y(:n))
        do i = 1, n
          y(i) = y(i) + a * x(i)
        end do
        """,
    good="""
        !$acc enter data copyin(x, y)        ! once, outside the time loop
        ...
        !$acc parallel loop present(x, y)
        do i = 1, n
          y(i) = y(i) + a * x(i)
        end do
        """,
)
def check_implicit_data(ctx: LintContext) -> Iterator[Hit]:
    for line, matches in sorted(_grouped(ctx, "nvfortran", _IMPLICIT_DATA_RE).items()):
        moves = ", ".join(f"{m.group(1)}({m.group(2)})" for m in matches)
        yield Hit(
            line=line, message=f"implicit data movement for the compute region: {moves}", snippet=f"implicit {moves}"
        )


@rule(
    "ACC012",
    "sequential-device-loop",
    summary="A loop in an OpenACC compute region runs sequentially: the compiler found a loop-carried dependence.",
    rationale=f"""
        In a `kernels` region the compiler parallelises only the loops it can prove independent. A loop-carried
        dependence (`y(i) = y(i) + y(i-1)`) makes it generate a serial kernel: the loop runs on one GPU thread,
        often slower than on the host. Restructure the computation (a scan, a different loop order), or move
        the loop off the device; if the dependence is only apparent (aliasing the compiler cannot rule out),
        say so with `!$acc loop independent`.
        {_FEEDBACK_NOTE}
        """,
    bad="""
        !$acc kernels
        do i = 2, n
          y(i) = y(i) + y(i-1)      ! nvfortran: Loop carried dependence of y prevents parallelization
        end do
        !$acc end kernels
        """,
    good="!$acc parallel loop independent   ! only when the dependence is not real",
)
def check_sequential_loop(ctx: LintContext) -> Iterator[Hit]:
    for line, matches in sorted(_grouped(ctx, "nvfortran", _SEQUENTIAL_RE).items()):
        names = ", ".join(sorted({m.group(1) for m in matches}))
        yield Hit(
            line=line,
            message=f"loop runs sequentially on the device: loop-carried dependence of {names}",
            snippet=f"seq {names}",
        )


@rule(
    "OMP008",
    "implicit-target-map",
    summary="The compiler maps data implicitly for an OpenMP target region (nvfortran: 'Generating implicit map').",
    rationale=f"""
        Variables used in a `target` region without a `map` clause are mapped implicitly; arrays default to
        `tofrom`, a copy in and out at every execution of the region. In an iterative loop that is a transfer
        per iteration. Keep the data on the device with `target enter data` / `target data` and map exactly
        what each region needs (`map(to:)`, `map(from:)`, or nothing when present).
        {_FEEDBACK_NOTE}
        """,
    bad="""
        !$omp target teams distribute parallel do     ! nvfortran: Generating implicit map(tofrom:y(:))
        do i = 1, n
          y(i) = 2 * y(i)
        end do
        """,
    good="""
        !$omp target enter data map(to: y)
        ...
        !$omp target teams distribute parallel do
        """,
)
def check_implicit_map(ctx: LintContext) -> Iterator[Hit]:
    for line, matches in sorted(_grouped(ctx, "nvfortran", _IMPLICIT_MAP_RE).items()):
        maps = ", ".join(f"map({m.group(1)}:{m.group(2)})" for m in matches)
        yield Hit(line=line, message=f"implicit {maps} for the target region", snippet=f"implicit {maps}")


@rule(
    "PRF001",
    "loop-not-vectorized",
    summary="gfortran could not vectorise a loop (`-fopt-info-vec-missed`).",
    rationale=f"""
        A loop the compiler could not vectorise runs one element per instruction. The reason the compiler gives
        (a dependence, a non-contiguous access, a call it cannot inline) is reported with the finding. Many
        loops are not worth vectorising: this rule is informational and off by default; select it when tuning
        a hot spot. {_FEEDBACK_NOTE}
        """,
    bad="""
        do i = 2, n
          y(i) = y(i) * y(i-1)      ! gfortran: missed: couldn't vectorize loop
        end do
        """,
    severity="info",
    default=False,
)
def check_not_vectorized(ctx: LintContext) -> Iterator[Hit]:
    messages = [m for m in ctx.feedback if m.compiler == "gfortran"]
    for idx, message in enumerate(messages):
        if message.text != "couldn't vectorize loop":
            continue
        reason = next((r.group(1) for m in messages[idx + 1 : idx + 4] if (r := _NOT_VECTORIZED_RE.match(m.text))), "")
        detail = f": {reason}" if reason else ""
        yield Hit(line=message.line, message=f"loop not vectorized{detail}", snippet=f"novec {reason}")
