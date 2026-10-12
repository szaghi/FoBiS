"""Rebuild the knowledge packs shipped with FoBiS from their sources (maintainer tool).

The sources are Claude skills and notes kept in the maintainer's dotfiles repository
(https://github.com/szaghi/dotfiles); the packs record the dotfiles commit they were built from.

Usage::

    python scripts/sync_kb.py ~/dotfiles          # rebuild every shipped pack
    python scripts/sync_kb.py ~/dotfiles openmp   # rebuild one pack
"""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fobis.kb import SHIPPED_DIR, Source, build_pack, skill_sources  # noqa: E402

ATTRIBUTION = "Stefano Zaghi, https://github.com/szaghi/dotfiles"
SOURCE = "https://github.com/szaghi/dotfiles"
VERSION = "1.0.0"
# The skills cross-reference the author's assistant notes; in the packs those notes are the hpc-practice pack.
REWRITES = [
    (r"cross-referenced to your memory", "cross-referenced to the hpc-practice pack"),
    (r"\byour memory\b", "the hpc-practice pack"),
    (r"`?CLAUDE-gpu\.md`?", "hpc-practice pack (gpu-practice)"),
    (r"`?CLAUDE-fortran\.md`?", "hpc-practice pack (fortran-practice)"),
    (r"\s*/\s*`?feedback_\w+`?", ""),  # "hpc-practice ... / feedback_x": the note is in the pack
    (r"\*{0,2}`?feedback_\w+`?\*{0,2}", "the hpc-practice pack"),
]

# pack name -> (title, sources relative to the dotfiles root, NOTICE relative to the dotfiles root or None)
PACKS = {
    "fortran-std": (
        "Fortran 2023 standard: distilled reference",
        ["claude/.claude/skills/fortran-2023-standard"],
        "claude/.claude/skills/fortran-2023-standard/NOTICE",
    ),
    "openmp": (
        "OpenMP 6.0 (with Nov-2025 errata): distilled reference",
        ["claude/.claude/skills/openmp-6.0"],
        "claude/.claude/skills/openmp-6.0/NOTICE",
    ),
    "openacc": (
        "OpenACC 3.4: distilled reference",
        ["claude/.claude/skills/openacc-3.4"],
        "claude/.claude/skills/openacc-3.4/NOTICE",
    ),
    "mpi": (
        "MPI 5.0: distilled reference",
        ["claude/.claude/skills/mpi-5.0"],
        "claude/.claude/skills/mpi-5.0/NOTICE",
    ),
    "hpc-practice": (
        "Fortran and GPU/HPC practice: conventions, pitfalls, measured lessons",
        ["claude/.claude/CLAUDE-fortran.md", "claude/.claude/CLAUDE-gpu.md"],
        None,
    ),
}


def _sources(dotfiles: str, paths: list[str]) -> list[Source]:
    sources = []
    for rel in paths:
        full = os.path.join(dotfiles, rel)
        if os.path.isfile(full):
            stem = os.path.basename(rel).removeprefix("CLAUDE-").removesuffix(".md")
            sources.append(Source(doc=f"{stem}-practice", path=full))
        else:
            sources.extend(skill_sources(full))
    return sources


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    dotfiles, names = os.path.abspath(os.path.expanduser(argv[0])), argv[1:] or list(PACKS)
    rev = subprocess.run(
        ["git", "-C", dotfiles, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    for name in names:
        title, paths, notice = PACKS[name]
        out = os.path.join(SHIPPED_DIR, name)
        os.makedirs(out, exist_ok=True)
        meta = {
            "name": name,
            "version": VERSION,
            "title": title,
            "license": "CC-BY-4.0",
            "attribution": ATTRIBUTION,
            "source": SOURCE,
            "source_rev": rev,
        }
        notice_path = os.path.join(dotfiles, notice) if notice else None
        if notice_path is None:  # the author's own notes: write the attribution notice
            with open(os.path.join(out, "NOTICE"), "w", encoding="utf-8") as handle:
                handle.write(
                    f"NOTICE - {name} pack\n\n{title}.\n\nCopyright (C) Stefano Zaghi. Licensed CC-BY-4.0\n"
                    "(https://creativecommons.org/licenses/by/4.0/). Original writing of the author,\n"
                    f"distilled from HPC development experience. Source: {SOURCE} (rev {rev}).\n"
                )
            meta["notice"] = "NOTICE"
        count = build_pack(_sources(dotfiles, paths), out, meta, notice=notice_path, rewrites=REWRITES)
        print(f"{name}: {count} chunks (dotfiles {rev})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
