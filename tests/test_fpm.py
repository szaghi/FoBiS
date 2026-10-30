"""Tests for ``fobis fpm`` (phase V12 of PLAN-verification.md): the stdlib TOML reader against ``tomllib`` on REAL
manifests (``tests/fpm/``: StringiFor, FLAP, VTKFortran — dotted tables, inline tables, arrays of tables, multi-line
strings with line-ending backslashes) and on the syntax corners, fpm.toml -> fobos (library mode from the module
named after the package, path dependencies followed, dev dependencies, metapackages, links, macros, notes; features
and profiles resolved as fpm does, checked against the GENUINE compile commands of fpm 0.13.0 on tests/fpm/packages/
mixed), fobos -> fpm.toml (library directory
from the modules, tests and executables from the programs, unique names, dependencies, the version file outside a
git repository), the CLI (no overwrite without --force, --print, --json) and a round trip built with gfortran."""

from __future__ import annotations

import json
import os
import shutil
import sys

import pytest

from fobis.fobis import run_fobis
from fobis.fpm import FpmError, dump_toml, fobos_from_fpm, parse_toml

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fpm")


@pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib is Python 3.11+")
@pytest.mark.parametrize("name", ["StringiFor", "FLAP", "VTKFortran"])
def test_reader_matches_tomllib(name):
    import tomllib

    with open(os.path.join(HERE, f"{name}.toml"), encoding="utf-8") as handle:
        text = handle.read()
    assert parse_toml(text) == tomllib.loads(text)


@pytest.mark.parametrize("name", ["StringiFor", "FLAP", "VTKFortran"])
def test_dump_toml_round_trip(name):
    # the fpm backend rewrites a package's manifest (no examples) with dump_toml: nothing else may change
    with open(os.path.join(HERE, f"{name}.toml"), encoding="utf-8") as handle:
        manifest = parse_toml(handle.read())
    assert parse_toml(dump_toml(manifest)) == manifest


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


def test_fobos_from_fpm(tmp_path, monkeypatch):
    monkeypatch.setattr("fobis.fpm.current_os", lambda: "linux")
    project = tmp_path / "demo"
    _write(
        project,
        {
            "src/demo.f90": "module demo\nuse helper\nend module demo\n",
            "app/main.f90": "program main\nend program main\n",
            "test/check.f90": "program check\nend program check\n",
            "../dep/fpm.toml": 'name = "dep"\n[library]\nsource-dir = "lib"\n[dependencies]\ninner = { path = "inner" }\n',
            "../dep/inner/fpm.toml": 'name = "inner"\n',
        },
    )
    manifest = parse_toml(
        'name = "demo"\nversion = "1.2.0"\nauthor = ["A", "B"]\ndescription = "d"\n'
        '[build]\nlink = ["lapack", "blas"]\nexternal-modules = ["netcdf"]\n'
        '[preprocess.cpp]\nmacros = ["USE_X", "N=4", "V={version}"]\n[fortran]\nimplicit-typing = true\n'
        '[features]\nwarn = "-Wall"\n'
        '[dependencies]\npenf = { git = "https://github.com/szaghi/PENF", tag = "v1.5.0" }\nmpi = "*"\n'
        'stdlib = "*"\nhelper = { path = "../dep" }\n[dev-dependencies]\ntest-drive = { git = "https://x/td" }\n'
        'fixtures = { path = "../dep/inner" }\n'
    )
    translation = fobos_from_fpm(manifest, str(project), "gnu")
    text = translation.text
    assert "modes = gnu-debug gnu-release lib-static" in text and "target = src/demo.f90" in text
    assert "src = ./src/ ./app/ ./test/\n" in text and "authors = A, B" in text
    assert "preproc = -DUSE_X -DN=4 -DV=1.2.0" in text and "ext_libs = lapack blas" in text and "mpi = True" in text
    # implicit-typing = true: no -fimplicit-none; implicit externals stay errors; free form; cpp for the macros
    assert "cflags = -c -cpp -Werror=implicit-interface -ffree-form\n" in text
    assert "penf = https://github.com/szaghi/PENF :: tag=v1.5.0" in text and "test-drive = https://x/td :: dev" in text
    # a path dependency is its library directory; its own path dependency follows (the dev one is seen there first)
    assert "helper = path=../dep/lib\ninner = path=../dep/inner/src\n" in text and "fixtures" not in text
    assert "features = debug\n" in text and "[feature:debug]\nflags = -Wall -Wextra -Wimplicit-interface" in text
    assert "[test]\ntest_dir = test" in text
    notes = "\n".join(translation.notes)
    for expected in ("stdlib", "external-modules", "[features] warn", "a feature must be a table"):
        assert expected in notes
    assert "dev-dependencies" not in notes and "helper" not in notes and "implicit-typing" not in notes
    plain = fobos_from_fpm({"name": "other"}, str(project), "intel")
    assert "lib-static" not in plain.text and any("no module named 'other'" in n for n in plain.notes)
    assert "cflags = -c -free -fPIC\n" in plain.text  # fpm's Intel flags: free form, -fPIC always


FEATURES = """
name = "feat"
version = "0.1.0"
[library]
type = ["shared", "static"]
[features]
# all compilers, then gfortran, then linux, then both
checks.flags = "-g"
checks.gfortran.flags = "-fcheck=all"
checks.linux.preprocess.cpp.macros = "ON_LINUX"
checks.linux.gfortran.flags = "-fbacktrace"
checks.windows.flags = "-Ox"
checks.ifx.flags = "-check all"
checks.requires = ["base"]
base.preprocess.cpp.macros = ["BASE", "VER={version}"]
base.link-time-flags = "-Wl,--as-needed"
base.c-flags = "-std=c11"
parallel.dependencies.openmp = "*"
openmp.flags = "-DOWN_OPENMP"
odd.executable = [{ name = "x", source-dir = "x" }]
debug.flags = "-g3"
[profiles]
default = ["base"]
careful = ["checks", "parallel"]
broken = ["missing"]
old = { gfortran = { flags = "-O" } }
"""


def test_features_and_profiles(tmp_path, monkeypatch):
    """fpm's merge: the base first, then each variant for this compiler and OS in the manifest's order; profiles are
    lists of features; ``default`` goes first in debug and release only; a manifest ``debug`` feature replaces fpm's."""
    monkeypatch.setattr("fobis.fpm.current_os", lambda: "linux")
    _write(tmp_path, {"src/feat.f90": "module feat\nend module feat\n", "src/clock.c": "int f(void) { return 1; }\n"})
    translation = fobos_from_fpm(parse_toml(FEATURES), str(tmp_path), "gnu")
    text = translation.text
    assert "[feature:checks]\nflags = -g -fcheck=all -fbacktrace -DON_LINUX\nrequires = base\n" in text
    assert "[feature:base]\nflags = -DBASE -DVER=0.1.0\n" in text
    assert "[feature:parallel]\nflags = @openmp\n" in text and "[feature:fpm-openmp]\nflags = -DOWN_OPENMP\n" in text
    assert "[feature:debug]\nflags = -g3\n" in text and "[feature:release]\nflags = -O3 -Wimplicit-interface" in text
    assert "modes = gnu-debug gnu-release gnu-careful gnu-broken lib-shared lib-static" in text
    assert "[gnu-debug]\ntemplate = template-common\nfeatures = base debug\n" in text
    assert "[gnu-careful]\ntemplate = template-common\nfeatures = checks parallel\n" in text
    # C: the features' C flags and macros, the template's macros; link-time flags in the mode
    assert "c_cflags = -c -std=c11 -O3 -fPIC -fmax-errors=1 -funroll-loops\n" in text
    assert "c_preproc = -DBASE -DVER=0.1.0\nlflags = -Wl,--as-needed\n" in text
    assert "[lib-shared]" in text and "mklib = shared" in text and "output = libfeat.so" in text
    assert "cflags = -c -cpp -fimplicit-none -Werror=implicit-interface -ffree-form -fPIC\n" in text
    notes = translation.notes
    assert "feature openmp is named fpm-openmp in the fobos: openmp is a FoBiS feature already" in notes
    assert "feature odd: executable not translated" in notes
    assert "features checks have flags for ifx too: import again with --compiler intel_nextgen" in notes
    assert "feature checks has flags for windows, not for linux" in notes
    assert "profile broken: no feature missing" in notes
    assert "[profiles] old: not a list of features (an older fpm syntax), not translated" in notes
    intel = fobos_from_fpm(parse_toml(FEATURES), str(tmp_path), "intel_nextgen").text
    assert "[feature:checks]\nflags = -g -check all -DON_LINUX\n" in intel and "-fpp" in intel
    nvidia = fobos_from_fpm(parse_toml(FEATURES), str(tmp_path), "nvfortran").text
    assert "[feature:release]\nflags = -Mbackslash\n" in nvidia  # fpm's own release for nvfortran


def test_feature_tables_errors(tmp_path, monkeypatch):
    monkeypatch.setattr("fobis.fpm.current_os", lambda: "linux")
    with pytest.raises(FpmError, match="must be a table"):
        fobos_from_fpm(parse_toml('name = "x"\n[features]\nf.linux = 1\n'), str(tmp_path), "gnu")


def _fpm_lines(profile):
    """The genuine compile commands of fpm 0.13.0 for the ``mixed`` fixture: {file: flags}."""
    lines = {}
    with open(os.path.join(HERE, "mixed-fpm-0.13.0.txt"), encoding="utf-8") as handle:
        for line in handle:
            if line.startswith(profile + " "):
                where, command = line[len(profile) + 1 :].split(": ", 1)
                lines[where] = command
    return lines


def _flags(command):
    words = command.split()
    return {w for w in words if w.startswith("-") and w not in ("-c", "-o") and not w.startswith(("-I", "-J"))}


@pytest.mark.skipif(sys.platform != "linux" or shutil.which("gcc") is None, reason="recorded on linux with gcc")
@pytest.mark.parametrize("profile", ["debug", "release", "quick", "careful"])
def test_imported_modes_compile_with_fpm_flags(tmp_path, monkeypatch, capsys, profile):
    """``tests/fpm/packages/mixed`` imported and built: every file of the package is compiled with the flags fpm 0.13.0
    used (``tests/fpm/mixed-fpm-0.13.0.txt``); a dependency compiled with the project gets the project's macros too."""
    shutil.copytree(os.path.join(HERE, "packages", "mixed"), tmp_path / "mixed")
    monkeypatch.chdir(tmp_path / "mixed")
    assert _run(["fpm", "import"], capsys)[0] == 0
    code, out, _ = _run(["build", "--mode", f"gnu-{profile}", "--verbose"], capsys)
    assert code == 0, out
    commands = {}
    for line in out.splitlines():
        if line.startswith("Executing: [('"):
            command = line[len("Executing: [('") :].split("', None")[0]
            commands[command.split()[-3]] = command  # ... SOURCE -o OBJECT
    for where, command in _fpm_lines(profile).items():
        ours = _flags(commands[where])
        if where.startswith("crate/"):
            ours = {f for f in ours if not f.startswith("-D")}
        assert ours == _flags(command), where
    import subprocess

    printed = subprocess.run([f"build/{profile}/main"], capture_output=True, text=True, check=True).stdout.split()
    assert printed == (["baseline", "3", "6"] if profile in ("debug", "release") else ["3", "6"])


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc")
def test_imported_package_tests_and_libraries(tmp_path, monkeypatch, capsys):
    shutil.copytree(os.path.join(HERE, "packages", "mixed"), tmp_path / "mixed")
    monkeypatch.chdir(tmp_path / "mixed")
    assert _run(["fpm", "import"], capsys)[0] == 0
    code, out, _ = _run(["test", "--mode", "gnu-careful", "--json"], capsys)
    assert code == 0 and json.loads(out)["passed"] == 1
    for mode, library in (("lib-static", "build/lib/libmixed.a"), ("lib-shared", "build/lib-shared/libmixed.so")):
        assert _run(["build", "--mode", mode], capsys)[0] == 0
        assert (tmp_path / "mixed" / library).is_file()


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
    assert _run(["build", "--mode", "lib-static"], capsys)[0] == 0
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
