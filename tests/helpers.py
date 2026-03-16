"""Shared helpers for FoBiS.py test suite."""

import filecmp
import os
import shutil

from fobis.fobis import run_fobis

# Absolute path to the tests/ directory — used by helpers to chdir into fixtures.
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Whether the OpenCoarrays compiler wrapper is available (needed for build-test15).
OPENCOARRAYS = shutil.which("caf") is not None


def run_build(directory):
    """Run a build scenario. Returns True on success."""
    build_ok = False
    old_pwd = os.getcwd()
    os.chdir(os.path.join(TESTS_DIR, directory))

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

    os.chdir(old_pwd)
    return build_ok


def run_clean(directory):
    """Run build then clean. Returns True if clean removed all artifacts."""
    old_pwd = os.getcwd()
    os.chdir(os.path.join(TESTS_DIR, directory))

    run_fobis(fake_args=["build", "-f", "fobos"])
    run_fobis(fake_args=["clean", "-f", "fobos"])

    clean_ok = not os.path.exists(directory)
    os.chdir(old_pwd)
    return clean_ok


def make_makefile(directory):
    """Generate a Makefile and compare it against the golden file."""
    old_pwd = os.getcwd()
    os.chdir(os.path.join(TESTS_DIR, directory))

    run_fobis(fake_args=["build", "-f", "fobos", "-m", "makefile_check"])
    make_ok = filecmp.cmp("makefile_check", "makefile_ok")
    if not make_ok and os.path.exists("makefile_ok2"):
        make_ok = filecmp.cmp("makefile_check", "makefile_ok2")
    if not make_ok:
        with open("makefile_check") as mk_check:
            print("generated makefile:\n" + mk_check.read())

    run_fobis(fake_args=["clean", "-f", "fobos"])
    os.chdir(old_pwd)
    return make_ok


def run_install(directory):
    """Run build + install. Returns True if artifacts were installed."""
    old_pwd = os.getcwd()
    os.chdir(os.path.join(TESTS_DIR, directory))

    run_fobis(fake_args=["clean", "-f", "fobos"])
    run_fobis(fake_args=["build", "-f", "fobos"])
    run_fobis(fake_args=["install", "-f", "fobos", "--prefix", "prefix"])

    files = [os.path.join(dp, f) for dp, _, filenames in os.walk("./prefix/") for f in filenames]
    install_ok = len(files) > 0

    run_fobis(fake_args=["rule", "-f", "fobos", "-ex", "finalize"])
    run_fobis(fake_args=["clean", "-f", "fobos"])

    os.chdir(old_pwd)
    return install_ok


def run_doctest(directory):
    """Run inline doctests. Returns True on success."""
    old_pwd = os.getcwd()
    os.chdir(os.path.join(TESTS_DIR, directory))

    run_fobis(fake_args=["clean", "-f", "fobos"])
    run_fobis(fake_args=["doctests", "-f", "fobos"])
    run_fobis(fake_args=["rule", "-f", "fobos", "-ex", "finalize"])
    run_fobis(fake_args=["clean", "-f", "fobos"])

    os.chdir(old_pwd)
    return True


def run_rule(directory):
    """Execute a custom rule. Returns True on success."""
    old_pwd = os.getcwd()
    os.chdir(os.path.join(TESTS_DIR, directory))

    run_fobis(fake_args=["rule", "-ex", "test"])

    os.chdir(old_pwd)
    return True
