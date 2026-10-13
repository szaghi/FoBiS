"""Rebuild the knowledge packs shipped with FoBiS from their sources (maintainer tool).

Two kinds of sources:

- the standards and practice packs come from Claude skills and notes kept in the maintainer's dotfiles repository
  (https://github.com/szaghi/dotfiles); they record the dotfiles commit they were built from;
- the compilers, libraries and numerics packs come from ``kb-sources/<pack>/*.md`` in this repository; they record
  a digest of their sources, and ``tests/test_kb.py`` fails when a shipped pack differs from a fresh build.

Usage::

    python scripts/sync_kb.py ~/dotfiles          # rebuild every pack built from the dotfiles
    python scripts/sync_kb.py ~/dotfiles openmp   # rebuild one pack
    python scripts/sync_kb.py --local             # rebuild the packs of kb-sources/
    python scripts/sync_kb.py --local numerics    # rebuild one of them
"""

from __future__ import annotations

import hashlib
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


# packs written in this repository: name -> title (sources: kb-sources/<name>/*.md)
LOCAL_DIR = os.path.join(ROOT, "kb-sources")
LOCAL_SOURCE = "https://github.com/szaghi/FoBiS"
LOCAL_ATTRIBUTION = "Stefano Zaghi, https://github.com/szaghi/FoBiS"
LOCAL_PACKS = {
    "compilers": "Fortran compilers in practice: gfortran, ifx, nvfortran defaults, checks, floating point, modules",
    "libraries": "MPI implementations and HDF5 in practice: launchers, wrappers, modules, pitfalls",
    "numerics": "Numerical error assessment, floating-point behaviour and run-time measurement, with references",
}


def local_digest(sources: list[Source]) -> str:
    """A digest of the sources of a local pack (names and contents): its ``source_rev``."""
    digest = hashlib.sha256()
    for source in sorted(sources, key=lambda s: s.doc):
        digest.update(source.doc.encode())
        with open(source.path, "rb") as handle:
            digest.update(handle.read())
    return digest.hexdigest()[:12]


def build_local(name: str, out: str) -> int:
    """Build the local pack *name* from ``kb-sources/<name>`` into *out*; return the number of chunks."""
    sources = skill_sources(os.path.join(LOCAL_DIR, name))
    rev = local_digest(sources)
    title = LOCAL_PACKS[name]
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "NOTICE"), "w", encoding="utf-8") as handle:
        handle.write(
            f"NOTICE - {name} pack\n\n{title}.\n\nCopyright (C) Stefano Zaghi. Licensed CC-BY-4.0\n"
            "(https://creativecommons.org/licenses/by/4.0/). Written for FoBiS from measurements on real compilers\n"
            f"and libraries and from the cited literature. Source: {LOCAL_SOURCE}, kb-sources/{name} (digest {rev}).\n"
        )
    meta = {
        "name": name,
        "version": VERSION,
        "title": title,
        "license": "CC-BY-4.0",
        "attribution": LOCAL_ATTRIBUTION,
        "source": LOCAL_SOURCE,
        "source_rev": rev,
        "notice": "NOTICE",
    }
    return build_pack(sources, out, meta)


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
    if argv[0] == "--local":
        for name in argv[1:] or list(LOCAL_PACKS):
            count = build_local(name, os.path.join(SHIPPED_DIR, name))
            print(f"{name}: {count} chunks (kb-sources)")
        return 0
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
