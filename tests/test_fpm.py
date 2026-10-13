"""Tests for ``fobis fpm`` (phase V12 of PLAN-verification.md): the stdlib TOML reader against ``tomllib`` on REAL
manifests (``tests/fpm/``: StringiFor, FLAP, VTKFortran — dotted tables, inline tables, arrays of tables, multi-line
strings with line-ending backslashes) and on the syntax corners, fpm.toml -> fobos (library mode from the module
named after the package, path dependency, metapackages, links, macros, notes), fobos -> fpm.toml (library directory
from the modules, tests and executables from the programs, unique names, dependencies, the version file outside a
git repository), the CLI (no overwrite without --force, --print, --json) and a round trip built with gfortran."""

from __future__ import annotations

import json
import os
import sys

import pytest

from fobis.fobis import run_fobis
from fobis.fpm import FpmError, fobos_from_fpm, parse_toml

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fpm")


@pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib is Python 3.11+")
@pytest.mark.parametrize("name", ["StringiFor", "FLAP", "VTKFortran"])
def test_reader_matches_tomllib(name):
    import tomllib

    with open(os.path.join(HERE, f"{name}.toml"), encoding="utf-8") as handle:
        text = handle.read()
    assert parse_toml(text) == tomllib.loads(text)


def test_reader_corners():
    text = """\
# comment
name = "a \\"quoted\\" \\u00e9"   # trailing comment
literal = 'C:\\path'
multi = \"\"\"
first \\
   second\"\"\"
raw = '''
keep \\n'''
nums = [1, -2, 3.5, 1_000, 0x1F, true, false,
        # inside an array
        "x",]
dotted.key = 1
dep = { git = "u", nested = { tag = "v1" } }

[table.sub]
k = 2

[[arr]]
a = 1
[[arr]]
a = 2
"""
    data = parse_toml(text)
    assert data["name"] == 'a "quoted" é' and data["literal"] == "C:\\path"
    assert data["multi"] == "first second" and data["raw"] == "keep \\n"
    assert data["nums"] == [1, -2, 3.5, 1000, 31, True, False, "x"]
    assert data["dotted"] == {"key": 1} and data["dep"]["nested"]["tag"] == "v1"
    assert data["table"]["sub"]["k"] == 2 and [a["a"] for a in data["arr"]] == [1, 2]
    for bad, message in (("a = 1\na = 2\n", "duplicate key"), ('a = "x\n', "unterminated"), ("a = [1 2]\n", "','")):
        with pytest.raises(FpmError, match=message):
            parse_toml(bad)


def _write(root, files):
    for path, text in files.items():
        full = os.path.normpath(os.path.join(root, path))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(text)


def test_fobos_from_fpm(tmp_path):
    project = tmp_path / "demo"
    _write(
        project,
        {
            "src/demo.f90": "module demo\nuse helper\nend module demo\n",
            "app/main.f90": "program main\nend program main\n",
            "test/check.f90": "program check\nend program check\n",
            "../dep/fpm.toml": 'name = "dep"\n[library]\nsource-dir = "lib"\n',
        },
    )
    manifest = parse_toml(
        'name = "demo"\nversion = "1.2.0"\nauthor = ["A", "B"]\ndescription = "d"\n'
        '[build]\nlink = ["lapack", "blas"]\nexternal-modules = ["netcdf"]\n'
        '[preprocess.cpp]\nmacros = ["USE_X", "N=4"]\n[fortran]\nimplicit-typing = false\n'
        '[features]\nwarn = "-Wall"\n'
        '[dependencies]\npenf = { git = "https://github.com/szaghi/PENF", tag = "v1.5.0" }\nmpi = "*"\n'
        'stdlib = "*"\nhelper = { path = "../dep" }\n[dev-dependencies]\ntest-drive = { git = "https://x/td" }\n'
    )
    translation = fobos_from_fpm(manifest, str(project), "gnu")
    text = translation.text
    assert "modes = gnu-debug gnu-release lib-gnu" in text and "target = src/demo.f90" in text
    assert "src = ./src/ ./app/ ./test/ ./../dep/lib/" in text and "authors = A, B" in text
    assert "preproc = -DUSE_X -DN=4" in text and "ext_libs = lapack blas" in text and "mpi = True" in text
    assert "penf = https://github.com/szaghi/PENF :: tag=v1.5.0" in text and "test-drive = https://x/td" in text
    assert "build_profile = debug" in text and "[test]\ntest_dir = test" in text
    notes = "\n".join(translation.notes)
    for expected in ("stdlib", "external-modules", "implicit-typing", "[features]", "dev-dependencies", "helper"):
        assert expected in notes
    plain = fobos_from_fpm({"name": "other"}, str(project), "intel")
    assert "lib-intel" not in plain.text and any("no module named 'other'" in n for n in plain.notes)


# ── the commands ───────────────────────────────────────────────────────────────


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def package(tmp_path, monkeypatch):
    _write(
        tmp_path,
        {
            "fpm.toml": 'name = "kit"\nversion = "0.3.0"\n[library]\nsource-dir = "src"\n',
            "src/kit.f90": "module kit\nimplicit none\ncontains\npure integer function twice(i)\n"
            "integer, intent(in) :: i\ntwice = 2 * i\nend function twice\nend module kit\n",
            "test/t_kit.f90": "program t_kit\nuse kit\nimplicit none\nif (twice(2) /= 4) error stop 1\n"
            "end program t_kit\n",
        },
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_import_round_trip(package, capsys):
    code, out, _ = _run(["fpm", "import", "--print"], capsys)
    assert code == 0 and out.startswith("# generated by fobis fpm import") and not (package / "fobos").exists()
    code, out, err = _run(["fpm", "import"], capsys)
    assert code == 0 and "fobos written" in out + err and (package / "fobos").is_file()
    assert _run(["fpm", "import"], capsys)[0] == 2  # no overwrite
    assert _run(["fpm", "import", "--force", "--json"], capsys)[0] == 0
    assert _run(["build", "--mode", "lib-gnu"], capsys)[0] == 0
    assert (package / "build" / "lib" / "libkit.a").is_file()
    code, out, _ = _run(["test", "--mode", "gnu-debug", "--json"], capsys)
    assert code == 0 and json.loads(out)["passed"] == 1


def test_export(tmp_path, monkeypatch, capsys):
    _write(
        tmp_path,
        {
            "fobos": "[project]\nname = kit\nversion = VERSION\nsummary = A kit\nauthors = A\n  B\n\n"
            "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/ ./app/ ./tests/\nmpi = True\n"
            "preproc = -DUSE_X\n\n[dependencies]\npenf = https://github.com/szaghi/PENF :: tag=v1.5.0\n",
            "VERSION": "v0.3.0\n",
            "src/kit.f90": "module kit\nend module kit\n",
            "src/sub/more.f90": "module more\nend module more\n",
            "app/run.f90": "program run\nend program run\n",
            "tests/a/t1.f90": "program volatile\nend program volatile\n",
            "tests/b/t2.f90": "program volatile\nend program volatile\n",
        },
    )
    monkeypatch.chdir(tmp_path)
    code, out, _ = _run(["fpm", "export", "--json"], capsys)
    data = json.loads(out)
    manifest = parse_toml(data["text"])
    assert code == 0 and data["written"] == "fpm.toml" and manifest["version"] == "0.3.0"  # VERSION file, no git
    assert manifest["author"] == "A, B" and manifest["description"] == "A kit"
    assert manifest["library"]["source-dir"] == "src" and manifest["build"]["auto-tests"] is False
    assert manifest["dependencies"]["mpi"] == "*"
    assert manifest["dependencies"]["penf"] == {"git": "https://github.com/szaghi/PENF", "tag": "v1.5.0"}
    assert manifest["preprocess"]["cpp"]["macros"] == ["USE_X"]
    assert [e["name"] for e in manifest["executable"]] == ["run"]
    assert sorted(t["name"] for t in manifest["test"]) == ["t1", "t2"]  # same program name: file stems
    assert _run(["fpm", "export"], capsys)[0] == 2  # fpm.toml exists
    os.remove("fobos")
    code, out, err = _run(["fpm", "export", "--print"], capsys)
    assert code == 2 and "no fobos to export" in out + err
