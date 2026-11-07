"""Shared helpers for FoBiS.py test suite."""

import filecmp
import os
import shutil

from fobis.fobis import run_fobis

# Absolute path to the tests/ directory — used by helpers to chdir into fixtures.
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Whether the OpenCoarrays compiler wrapper is available (needed for build-test15).
OPENCOARRAYS = shutil.which("caf") is not None

# Whether PreForM.py is available (needed for build-test5).
PREFORM = shutil.which("PreForM.py") is not None


# Fixtures whose inputs (../build-test2/precompiled/, ../build-test{3,7,9}/lib/) are made by build-test1's finalize rule.
BUILT_BY_BUILD_TEST1 = {"build-test2", "build-test3", "build-test7", "build-test9"}


def _copy_fixture(directory, tmp_path):
    """Copy the fixture *directory* into *tmp_path*, keeping its name (rules reach siblings as ../NAME); return it.

    Each test builds in its own copy: built in place, the fixtures were shared state between parallel workers
    (pytest -n auto), and builds rewrote tracked files (build-test24's preprocessed sources).
    """
    copy = os.path.join(str(tmp_path), directory)
    shutil.copytree(os.path.join(TESTS_DIR, directory), copy, symlinks=True)
    return copy


def run_build(monkeypatch, directory, tmp_path):
    """Run a build scenario in a copy of its fixture under *tmp_path*. Returns True on success."""
    build_ok = False
    fixture = _copy_fixture(directory, tmp_path)
    if directory in BUILT_BY_BUILD_TEST1:
        # what a serial run got from the previous test: build-test1 built, then its finalize rule writing into the
        # copy made above (copied after, the copy would find the directory the rule's mkdir -p made)
        monkeypatch.chdir(_copy_fixture("build-test1", tmp_path))
        run_fobis(fake_args=["clean", "-f", "fobos"])
        run_fobis(fake_args=["build", "-f", "fobos"])
        run_fobis(fake_args=["rule", "-f", "fobos", "-ex", "finalize"])
    monkeypatch.chdir(fixture)

    run_fobis(fake_args=["clean", "-f", "fobos"])

    try:
        run_fobis(fake_args=["build", "-f", "fobos"])
        build_ok = os.path.exists(directory)
    except (Exception, SystemExit):
        if directory == "build-test6":
            with open("building-errors.log") as logerror:
                build_ok = "Unclassifiable statement" in list(logerror)[-1]
            os.remove("building-errors.log")

    run_fobis(fake_args=["rule", "-f", "fobos", "-ex", "finalize"])
    run_fobis(fake_args=["clean", "-f", "fobos"])

    return build_ok


def run_clean(monkeypatch, directory):
    """Run build then clean. Returns True if clean removed all artifacts."""
    monkeypatch.chdir(os.path.join(TESTS_DIR, directory))

    run_fobis(fake_args=["build", "-f", "fobos"])
    run_fobis(fake_args=["clean", "-f", "fobos"])

    return not os.path.exists(directory)


def make_makefile(monkeypatch, directory):
    """Generate a Makefile and compare it against the golden file."""
    monkeypatch.chdir(os.path.join(TESTS_DIR, directory))

    run_fobis(fake_args=["build", "-f", "fobos", "-m", "makefile_check"])
    make_ok = filecmp.cmp("makefile_check", "makefile_ok")  # the rules are sorted by file: one golden file
    if not make_ok:
        with open("makefile_check") as mk_check:
            print("generated makefile:\n" + mk_check.read())

    run_fobis(fake_args=["clean", "-f", "fobos"])
    return make_ok


def run_install(monkeypatch, directory):
    """Run build + install. Returns True if artifacts were installed."""
    monkeypatch.chdir(os.path.join(TESTS_DIR, directory))

    run_fobis(fake_args=["clean", "-f", "fobos"])
    run_fobis(fake_args=["build", "-f", "fobos"])
    run_fobis(fake_args=["install", "-f", "fobos", "--prefix", "prefix"])

    files = [os.path.join(dp, f) for dp, _, filenames in os.walk("./prefix/") for f in filenames]
    install_ok = len(files) > 0

    run_fobis(fake_args=["rule", "-f", "fobos", "-ex", "finalize"])
    run_fobis(fake_args=["clean", "-f", "fobos"])

    return install_ok


def run_doctest(monkeypatch, directory):
    """Run inline doctests. Returns True on success."""
    monkeypatch.chdir(os.path.join(TESTS_DIR, directory))

    run_fobis(fake_args=["clean", "-f", "fobos"])
    run_fobis(fake_args=["doctests", "-f", "fobos"])
    run_fobis(fake_args=["rule", "-f", "fobos", "-ex", "finalize"])
    run_fobis(fake_args=["clean", "-f", "fobos"])

    return True


def run_rule(monkeypatch, directory):
    """Execute a custom rule. Returns True on success."""
    monkeypatch.chdir(os.path.join(TESTS_DIR, directory))

    run_fobis(fake_args=["rule", "-ex", "test"])

    return True
