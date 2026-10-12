"""references.py — knowledge-pack sections each rule is grounded on (``fobis kb show <id>``).

Chunk ids depend on the shipped packs: ``tests/test_kb.py`` fails when one no longer resolves (after
``scripts/sync_kb.py`` rebuilt a pack), so update this table together with the packs.
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

REFERENCES: dict[str, tuple[str, ...]] = {
    "COR001": ("fortran-std:ch19-scope-association#key-concepts",),
    "COR002": ("fortran-std:ch19-scope-association#anti-patterns",),
    "COR010": ("fortran-std:ch08-attribute-declarations#core-idea",),
    "COR011": ("fortran-std:ch08-attribute-declarations#array-dummy-bounds-the-rebasing-trap",),
    "COR020": ("hpc-practice:fortran-practice#implicit-save-trap", "fortran-std:ch19-scope-association#anti-patterns"),
    "COR040": ("hpc-practice:fortran-practice#module-visibility",),
    "OBS001": ("fortran-std:ch21-annex-b-deleted-obsolescent#obsolescent-features-b-3-still-legal-avoid-in-new-code",),
    "OBS005": ("fortran-std:ch21-annex-b-deleted-obsolescent#obsolescent-features-b-3-still-legal-avoid-in-new-code",),
    "OBS009": ("fortran-std:cheatsheet#loop-choice",),
    "OBS020": ("mpi:ch16-deprecated-removed#common-deprecated-modern-replacements",),
    "MDN201": ("mpi:ch17-language-bindings#anti-patterns",),
    "PRT011": ("hpc-practice:fortran-practice#kind-specifications-portability",),
    "PRT021": ("hpc-practice:fortran-practice#forbidden-kind-violating-patterns",),
    "FOR001": ("hpc-practice:fortran-practice#implicit-save-trap",),
    "FOR004": ("hpc-practice:fortran-practice#function-result-component-access-chained-func-component-is-i",),
    "FOR005": ("hpc-practice:gpu-practice#gpu-benchmark-timing", "openmp:patterns#portable-timing"),
    "OMP001": (
        "openmp:ch07-data-environment#key-concepts",
        "openmp:overview#two-attribute-systems-ch-7-never-conflate",
    ),
    "OMP002": ("openmp:ch07-data-environment#frameworks-introduced",),
    "OMP003": ("openmp:ch06-base-language#anti-patterns",),
    "OMP007": ("mpi:overview#init-threads-ch-11-2",),
    "ACC002": ("hpc-practice:gpu-practice#atomic-operations-red-flag",),
    "ACC003": ("hpc-practice:gpu-practice#device-code-pitfalls",),
    "ACC004": ("hpc-practice:gpu-practice#nvfortran-bug-openacc-reduction-into-a-declare-create-module",),
    "ACC006": (
        "openacc:patterns#routine-for-device-callable-functions",
        "openacc:ch07-procedures-async-fortran#frameworks-introduced",
    ),
    "ACC008": ("hpc-practice:gpu-practice#gpu-benchmark-timing", "openacc:ch07-procedures-async-fortran#anti-patterns"),
    "ACC011": ("openacc:patterns#collapse-reduction-for-dense-nests",),
    "MPI001": ("mpi:ch02-terms-conventions#anti-patterns",),
}
