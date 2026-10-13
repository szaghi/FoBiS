"""Tests for fobis.kb — pack building, retrieval, shipped packs (quality gates), fobis kb CLI; the packs written in
this repository (``kb-sources/``: compilers, libraries, numerics) match a fresh build of their sources, and every
compiler flag the compilers pack names is accepted by that compiler (flags of other compilers named on purpose are
rejected), for each compiler on PATH."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess

import pytest
from typer.testing import CliRunner

from fobis.cli import app
from fobis.kb import KnowledgeBase, PackError, Source, build_pack, clean, discover_packs, load_pack, tokenize
from fobis.kb.build import chunk_document, symbols_of
from fobis.kb.pack import SHIPPED_DIR
from fobis.lint import RULES

# ── building ───────────────────────────────────────────────────────────────────

_SKILL = """\
---
name: demo
description: "CONSULT THIS BEFORE ANSWERING"
---

# Demo standard

## How to Use This Skill

- **With a topic** — I read the chapter.

## Data sharing

Pairs with the `other` skill.
Variables are `shared` by default; use `private(x)` for per-thread copies. See C1004.

### Reduction

The `reduction` clause combines per-thread partial results at the end of the region.
"""


def test_clean_drops_front_matter_and_assistant_directed_text():
    text = clean(_SKILL)
    assert not text.startswith("---")
    assert "How to Use This Skill" not in text and "I read the chapter" not in text
    assert "the `other` skill" not in text
    assert "Variables are `shared` by default" in text


def test_chunk_document_ids_headings_symbols():
    chunks = chunk_document("demo", "overview", clean(_SKILL))
    assert [c["id"] for c in chunks] == ["demo:overview#data-sharing", "demo:overview#reduction"]
    assert chunks[1]["heading"] == "Demo standard > Data sharing > Reduction"
    assert set(chunks[0]["symbols"]) >= {"shared", "private", "c1004"}


def test_long_sections_are_split_and_ids_stay_unique():
    body = "\n\n".join(f"Paragraph {i} " + "word " * 80 for i in range(10))
    chunks = chunk_document("p", "d", f"## Long\n\n{body}\n\n## Long\n\nshort but long enough to be kept as a chunk.\n")
    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids)) and len(ids) > 2
    assert all(len(c["text"]) <= 1900 for c in chunks)


def test_symbols_of_directives_and_constraints():
    assert symbols_of("Use `!$acc routine seq` and `MPI_Isend`; see R1101.") == [
        "!$acc routine seq",
        "mpi_isend",
        "r1101",
    ]


def _build(tmp_path, name="demo", **meta):
    src = tmp_path / "skill"
    src.mkdir(exist_ok=True)
    (src / "SKILL.md").write_text(_SKILL)
    out = tmp_path / "packs" / name
    meta = {"name": name, "license": "CC-BY-4.0", **meta}
    count = build_pack([Source("overview", str(src / "SKILL.md"))], str(out), meta)
    return out, count


def test_build_and_load_round_trip(tmp_path):
    out, count = _build(tmp_path, title="Demo")
    pack = load_pack(str(out))
    assert count == len(pack.chunks) == 2
    assert pack.meta["title"] == "Demo" and pack.license == "CC-BY-4.0"


def test_build_requires_license_unless_private(tmp_path):
    src = tmp_path / "a.md"
    src.write_text(_SKILL)
    with pytest.raises(PackError, match="license is required"):
        build_pack([Source("a", str(src))], str(tmp_path / "out"), {"name": "a"})
    assert build_pack([Source("a", str(src))], str(tmp_path / "out"), {"name": "a"}, allow_unlicensed=True) == 2
    with pytest.raises(PackError, match="invalid pack name"):
        build_pack([Source("a", str(src))], str(tmp_path / "out"), {"name": "Bad Name", "license": "MIT"})


def test_build_applies_rewrites(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("## S\n\nSee CLAUDE-gpu.md for the timing rules of this section.\n")
    out = tmp_path / "out"
    rewrites = [(r"CLAUDE-gpu\.md", "pack X")]
    build_pack([Source("a", str(src))], str(out), {"name": "a", "license": "MIT"}, rewrites=rewrites)
    assert "pack X" in load_pack(str(out)).chunks[0].text


def test_discover_precedence_project_over_user_over_shipped(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.chdir(project)
    notes = tmp_path / "n.md"
    notes.write_text("## Section\n\nA section long enough to become a chunk of the pack.\n")
    meta = {"name": "openmp", "license": "MIT"}
    build_pack([Source("n", str(notes))], str(tmp_path / "config" / "fobis" / "kb" / "openmp"), meta)
    packs = {p.name: p for p in discover_packs()}
    assert packs["openmp"].scope == "user" and packs["mpi"].scope == "shipped"
    build_pack([Source("n", str(notes))], str(project / ".fobis" / "kb" / "openmp"), meta)
    assert {p.name: p for p in discover_packs()}["openmp"].scope == "project"


# ── retrieval ──────────────────────────────────────────────────────────────────


def test_tokenize_splits_snake_case_and_drops_stopwords():
    assert tokenize("The MPI_Isend of a request") == ["mpi_isend", "mpi", "isend", "request"]


def test_search_ranks_and_filters(tmp_path):
    out, _ = _build(tmp_path)
    kb = KnowledgeBase([load_pack(str(out))])
    assert kb.search("reduction partial results")[0].chunk.id == "demo:overview#reduction"
    assert kb.search("private per-thread copies")[0].chunk.id == "demo:overview#data-sharing"
    assert kb.search("reduction", packs=["other"]) == []
    neighbours = [c.id for c in kb.neighbours("demo:overview#reduction")]
    assert neighbours == ["demo:overview#data-sharing", "demo:overview#reduction"]


# ── shipped packs: quality gates ───────────────────────────────────────────────

_LOCAL = ("compilers", "libraries", "numerics")  # built from kb-sources/ by scripts/sync_kb.py --local
_SHIPPED = ("fortran-std", "hpc-practice", "mpi", "openacc", "openmp", *_LOCAL)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def shipped() -> KnowledgeBase:
    return KnowledgeBase(load_pack(f"{SHIPPED_DIR}/{name}") for name in _SHIPPED)


def test_shipped_packs_carry_license_attribution_notice(shipped):
    for pack in shipped.packs.values():
        assert pack.license == "CC-BY-4.0", pack.name
        assert pack.meta.get("attribution") and pack.meta.get("source_rev")
        assert pack.notice().strip(), pack.name
        assert len(pack.chunks) > 10


def test_shipped_packs_have_no_assistant_directed_text(shipped):
    leftover = re.compile(r"\bthis skill\b|\bCLAUDE-\w+\.md\b|\byour memory\b|\bfeedback_\w+|MEMORY\.md", re.IGNORECASE)
    offenders = [c.id for c in shipped.chunks if leftover.search(c.text) or leftover.search(c.heading)]
    assert not offenders


def test_shipped_chunk_ids_are_unique(shipped):
    ids = [c.id for c in shipped.chunks]
    assert len(ids) == len(set(ids))


def test_rule_references_resolve(shipped):
    missing = {rid: ref for rid, rule in RULES.items() for ref in rule.refs if ref not in shipped.by_id}
    assert not missing, f"stale rule references (packs rebuilt?): {missing}"


def test_code_references_resolve(shipped):
    """Pack sections named by the code (assess methods, crash and bench notes) exist."""
    from fobis.ai import crash
    from fobis.verification import assess, bench

    named = [
        *assess.METHODS.values(),
        crash.BACKTRACES_LIE,
        crash.GFORTRAN_EFAULT,
        crash.NVFORTRAN_719,
        bench.TIMING_SECTION,
        bench.FP64_SECTION,
    ]
    assert [ref for ref in named if ref not in shipped.by_id] == []


# Retrieval evaluation (phase B exit criterion): the expected section is among the first 5 results.
RETRIEVAL_EVAL = [
    ("implicit save initialization in declaration", "hpc-practice:fortran-practice#implicit-save-trap"),
    ("acc routine seq device callable", "openacc:patterns#routine-for-device-callable-functions"),
    ("MPI_Init_thread thread level funneled", "mpi:overview#init-threads-ch-11-2"),
    (
        "declare create reduction",
        "hpc-practice:gpu-practice#nvfortran-bug-openacc-reduction-into-a-declare-create-module",
    ),
    ("data sharing attributes loop iteration variable private", "openmp:ch07-data-environment#key-concepts"),
    ("cpu_time system_clock benchmark timing", "hpc-practice:gpu-practice#gpu-benchmark-timing"),
    ("mpif.h deprecated mpi_f08", "mpi:ch16-deprecated-removed#common-deprecated-modern-replacements"),
    (
        "function result component access",
        "hpc-practice:fortran-practice#function-result-component-access-chained-func-component-is-i",
    ),
    ("atomic red flag", "hpc-practice:gpu-practice#atomic-operations-red-flag"),
    ("kind parameters portability", "hpc-practice:fortran-practice#kind-specifications-portability"),
    (
        "common block obsolescent",
        "fortran-std:ch21-annex-b-deleted-obsolescent#obsolescent-features-b-3-still-legal-avoid-in-new-code",
    ),
    ("forall do concurrent loop choice", "fortran-std:cheatsheet#loop-choice"),
    ("ifx segfault large automatic array heap-arrays", "compilers:ifx#automatic-arrays-temporaries-and-the-stack"),
    ("nvfortran fused multiply add Kieee", "compilers:nvfortran#fma-is-on-even-at-o0"),
    ("cannot read module file created by a different version", "compilers:gfortran#module-files"),
    ("mpirun not enough slots oversubscribe", "libraries:mpi-implementations#more-ranks-than-processors"),
    ("hdf5 dataset dimensions transposed", "libraries:hdf5#dimensions-appear-reversed"),
    ("grid convergence index observed order", "numerics:assessment#refinement-family"),
    ("benchmark confidence interval median", "numerics:measurement#use-the-median-and-its-interval"),
    ("kahan compensated summation reassociation", "numerics:floating-point#compensated-summation"),
]


@pytest.mark.parametrize(("query", "expected"), RETRIEVAL_EVAL)
def test_retrieval_eval_top5(shipped, query, expected):
    assert expected in [r.chunk.id for r in shipped.search(query, k=5)]


# ── packs written in this repository ───────────────────────────────────────────


def _sync_kb():
    spec = importlib.util.spec_from_file_location("sync_kb", os.path.join(_ROOT, "scripts", "sync_kb.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", _LOCAL)
def test_local_packs_match_their_sources(name, tmp_path):
    """The shipped pack is a build of kb-sources/<name>: edit the sources, then run sync_kb.py --local."""
    _sync_kb().build_local(name, str(tmp_path))
    for item in ("pack.ini", "NOTICE", "index.json"):
        with open(os.path.join(SHIPPED_DIR, name, item), encoding="utf-8") as shipped_file:
            assert (tmp_path / item).read_text(encoding="utf-8") == shipped_file.read(), f"{name}/{item} stale"


# flags a compiler document names on purpose although that compiler rejects them (other compilers' flags)
_FOREIGN = {("nvfortran", "-ffp-contract=off"), ("nvfortran", "-fsanitize=address")}
_REJECTED = re.compile(r"unknown|ignoring|unrecogni|invalid|Unknown switch", re.IGNORECASE)


def _document_flags(doc: str) -> list[str]:
    """The compiler flags in the code spans of a compilers-pack document (a span may hold several flags)."""
    with open(os.path.join(_ROOT, "kb-sources", "compilers", f"{doc}.md"), encoding="utf-8") as handle:
        spans = re.findall(r"`([^`\n]+)`", handle.read())
    return sorted(
        {s for s in spans if re.match(r"-[A-Za-z]", s) and not s.endswith("=") and s not in ("-###", "-dryrun")}
    )


@pytest.mark.parametrize(("doc", "compiler"), [("gfortran", "gfortran"), ("ifx", "ifx"), ("nvfortran", "nvfortran")])
def test_compiler_flags_of_the_pack_are_accepted(doc, compiler, tmp_path):
    """Run for each compiler on PATH (load the toolchains first to check them all)."""
    if shutil.which(compiler) is None:
        pytest.skip(f"{compiler} not on PATH")
    (tmp_path / "p.f90").write_text("program p\nend program p\n")
    wrong = []
    for span in _document_flags(doc):
        run = subprocess.run(
            [compiler, *shlex.split(span), "-c", "p.f90", "-o", "p.o"], capture_output=True, text=True, cwd=tmp_path
        )
        rejected = run.returncode != 0 or bool(_REJECTED.search(run.stdout + run.stderr))
        if rejected != ((compiler, span) in _FOREIGN):
            wrong.append(f"{span}: {'rejected' if rejected else 'accepted'}")
    assert not wrong, f"{compiler}: {wrong}"


# ── CLI ────────────────────────────────────────────────────────────────────────


@pytest.fixture
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    return lambda *args: runner.invoke(app, ["kb", *args])


def test_cli_list_search_show_notice(cli):
    listing = cli("list")
    assert listing.exit_code == 0 and "openmp" in listing.output and "CC-BY-4.0" in listing.output
    found = cli("search", "acc routine seq", "-k", "2")
    assert found.exit_code == 0 and "openacc:patterns#routine-for-device-callable-functions" in found.output
    shown = cli("show", "openacc:patterns#routine-for-device-callable-functions")
    assert shown.exit_code == 0 and "routine seq" in shown.output and "CC-BY-4.0" in shown.output
    notice = cli("notice", "mpi")
    assert notice.exit_code == 0 and "University of Tennessee" in notice.output


def test_cli_search_json_and_pack_filter(cli):
    result = cli("search", "reduction", "--pack", "openacc", "--json")
    assert result.exit_code == 0
    assert all(item["id"].startswith("openacc:") for item in json.loads(result.output))
    assert cli("search", "x", "--pack", "nope").exit_code == 1


def test_cli_build_add_remove(cli, tmp_path):
    notes = tmp_path / "notes.md"
    notes.write_text("## Team rule\n\nEvery kernel validates its inputs on the host before launch.\n")
    built = cli("build", str(notes), "--name", "team", "--private")
    assert built.exit_code == 0, built.output
    listing = cli("list").output
    assert "team" in listing and "PRIVATE" in listing
    assert "team:notes#team-rule" in cli("search", "kernel validates inputs").output
    assert cli("build", str(notes), "--name", "lic").exit_code == 1  # no licence, not private
    assert cli("add", str(tmp_path / "config" / "fobis" / "kb" / "team"), "--project").exit_code == 0
    assert (tmp_path / ".fobis" / "kb" / "team" / "index.json").exists()
    assert cli("remove", "team").exit_code == 0
    assert cli("remove", "team", "--project").exit_code == 0
    assert "team" not in cli("list").output
    assert cli("remove", "openmp").exit_code == 1  # shipped packs cannot be removed
    assert cli("show", "no:such#id").exit_code == 1


def test_shipped_packs_load_from_a_zip_archive(tmp_path, monkeypatch):
    """The standalone fobis.pyz is a zip: shipped packs must be read as package resources, not files."""
    import os
    import zipfile

    from fobis.kb import pack as pack_module

    archive = tmp_path / "packs.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for name in ("mpi", "openacc"):
            for leaf in ("pack.ini", "NOTICE", "index.json"):
                zf.write(os.path.join(SHIPPED_DIR, name, leaf), f"packs/{name}/{leaf}")
    monkeypatch.setattr(pack_module, "shipped_root", lambda: zipfile.Path(archive) / "packs")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.chdir(tmp_path)
    packs = {p.name: p for p in discover_packs()}
    assert set(packs) == {"mpi", "openacc"}
    assert "University of Tennessee" in packs["mpi"].notice()
