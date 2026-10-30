"""Build backends and installed packages (#209 R4): the toolchain key, the store and its receipts, application links,
``fobis pkg install/list/path/uninstall/upgrade`` on a FoBiS and an fpm package built with gfortran, two toolchain keys
side by side, and consumers linking an installed library through pkg-config (a Fortran program and a CMake project).
The R4 exit criterion."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from fobis.registry import backends
from fobis.registry.store import Receipt, Store, link_applications
from fobis.registry.toolchain import Toolchain, ToolchainError, detect
from tests.registry_helpers import cli, fobis_package, isolate, remote

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("gfortran") is None, reason="git and gfortran"
)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)


def test_toolchain_key():
    a = Toolchain("gnu", "gfortran", "/usr/bin/gfortran", "GNU Fortran (GCC) 16.2.0", "gcc")
    b = Toolchain("gnu", "gfortran", "/usr/bin/gfortran", "GNU Fortran (GCC) 16.2.0", "gcc", cflags="-fdefault-real-8")
    assert a.key.startswith("gnu-16.2.0-") and a.key == Toolchain(**{**a.__dict__}).key
    assert a.key != b.key  # any flag changes the key: conservative on purpose
    with pytest.raises(ToolchainError, match="not found on PATH"):
        detect("gnu", fc="no-such-fortran-compiler")
    with pytest.raises(ToolchainError, match="unknown compiler family"):
        detect("cobol")
    assert detect("gnu").version.startswith("GNU Fortran")


def test_store_removes_only_recorded_files(tmp_path):
    store = Store(str(tmp_path / "store"))
    prefix = store.prefix("gnu-16-x", "kinds", "v1.0.0")
    os.makedirs(os.path.join(prefix, "lib"))
    for rel in ("lib/libkinds.a", "lib/foreign.txt"):
        with open(os.path.join(prefix, rel), "w") as fh:
            fh.write("x")
    receipt = Receipt("kinds", "u", "1.0.0", "t", "gnu-16-x", prefix, "fobis", files=["lib/libkinds.a"])
    store.record(receipt)
    assert [r.name for r in store.find("kinds")] == ["kinds"]
    store.remove(receipt)
    assert os.path.isfile(os.path.join(prefix, "lib", "foreign.txt")) and store.receipts() == []


def test_application_links_never_replace_a_foreign_file(tmp_path):
    exe = tmp_path / "store" / "k" / "app" / "1.0" / "bin" / "app"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "app").write_text("mine\n")
    made, refused = link_applications([str(exe)], str(bin_dir))
    assert made == [] and refused == [str(bin_dir / "app")] and (bin_dir / "app").read_text() == "mine\n"
    (bin_dir / "app").unlink()
    newer = tmp_path / "store" / "k" / "app" / "2.0" / "bin" / "app"
    newer.parent.mkdir(parents=True)
    newer.write_text("#!/bin/sh\n")
    assert link_applications([str(exe)], str(bin_dir))[0] and link_applications([str(newer)], str(bin_dir))[0]
    assert os.path.realpath(bin_dir / "app") == str(newer)  # an older version's link is replaced


APP = {
    "fobos": "[project]\nname = hello\n\n[modes]\nmodes = app\n\n[app]\ncompiler = gnu\nsrc = ./src/\n"
    "build_dir = ./build/\ntarget = src/hello.f90\noutput = hello-app\n",
    "src/hello.f90": "program hello\nprint '(A)', 'hello from an installed application'\nend program hello\n",
}

FPM_LIB = {
    "fpm.toml": 'name = "vecs"\nversion = "0.3.0"\ndescription = "vectors"\n[build]\nauto-executables = false\n'
    "auto-tests = false\nauto-examples = false\n",
    "src/vecs.f90": "module vecs\nimplicit none\ncontains\npure real function norm2d(x, y)\nreal, intent(in) :: x, y\n"
    "norm2d = sqrt(x*x + y*y)\nend function norm2d\nend module vecs\n",
}

CONSUMER = "program use_kinds\nuse kinds\ncall kinds_hello()\nprint '(A)', 'linked'\nend program use_kinds\n"


def _pkg_config(name, pc_dir, *flags) -> list[str]:
    out = subprocess.run(
        ["pkg-config", *flags, name], env={**os.environ, "PKG_CONFIG_PATH": pc_dir}, capture_output=True, text=True,
        check=True,
    )  # fmt: skip
    return out.stdout.split()


@pytest.mark.skipif(shutil.which("pkg-config") is None, reason="pkg-config")
def test_install_fobis_library_and_link_it_through_pkg_config(tmp_path):
    url = remote(tmp_path, "kinds", fobis_package("kinds"), tags=("v1.0.0",), more={"v1.1.0": {"NEWS": "x\n"}})
    code, out = cli("pkg", "install", url, "--version", "^1.0", "--json")
    receipt = json.loads(out)
    assert code == 0 and receipt["version"] == "v1.1.0" and receipt["backend"] == "fobis"
    assert receipt["modules"] == ["kinds"] and receipt["key"].startswith("gnu-")
    prefix = receipt["prefix"]
    assert os.path.isfile(os.path.join(prefix, "lib", "libkinds.a"))
    pc_dir = os.path.join(prefix, "lib", "pkgconfig")
    flags = _pkg_config("kinds", pc_dir, "--cflags", "--libs")
    consumer = tmp_path / "use_kinds.f90"
    consumer.write_text(CONSUMER)
    subprocess.run(["gfortran", str(consumer), *flags, "-o", str(tmp_path / "use_kinds")], check=True)
    assert subprocess.run([str(tmp_path / "use_kinds")], capture_output=True, text=True).stdout.strip() == "linked"
    # installed again: nothing rebuilt; another flag set: another key, side by side
    code, out = cli("pkg", "install", url, "--version", "^1.0")
    assert code == 0 and "already installed" in out
    code, out = cli("pkg", "install", url, "--cflags", "-O0", "--json")
    other = json.loads(out)
    assert other["key"] != receipt["key"] and os.path.isdir(prefix) and os.path.isdir(other["prefix"])
    code, out = cli("pkg", "list", "--json")
    assert sorted(r["key"] for r in json.loads(out)["packages"]) == sorted([receipt["key"], other["key"]])
    code, out = cli("pkg", "path", "kinds")
    assert code == 2 and "installed 2 times" in out
    code, out = cli("pkg", "path", "kinds", "--key", receipt["key"], "--pkgconfig")
    assert out.strip() == pc_dir
    code, out = cli("pkg", "uninstall", "kinds", "--key", other["key"])
    assert code == 0 and not os.path.exists(other["prefix"]) and os.path.isdir(prefix)


@pytest.mark.skipif(shutil.which("cmake") is None or shutil.which("pkg-config") is None, reason="cmake and pkg-config")
def test_cmake_consumer_links_an_installed_package(tmp_path):
    url = remote(tmp_path, "kinds", fobis_package("kinds"))
    code, out = cli("pkg", "install", url, "--json")
    assert code == 0, out
    prefix = json.loads(out)["prefix"]
    project = tmp_path / "cmake-consumer"
    project.mkdir()
    (project / "main.f90").write_text(CONSUMER)
    (project / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\nproject(consumer Fortran)\nfind_package(PkgConfig REQUIRED)\n"
        "pkg_check_modules(KINDS REQUIRED IMPORTED_TARGET kinds)\nadd_executable(use_kinds main.f90)\n"
        "target_link_libraries(use_kinds PkgConfig::KINDS)\n"
    )
    env = {**os.environ, "PKG_CONFIG_PATH": os.path.join(prefix, "lib", "pkgconfig")}
    subprocess.run(["cmake", "-S", str(project), "-B", str(project / "b")], env=env, check=True, capture_output=True)
    subprocess.run(["cmake", "--build", str(project / "b")], env=env, check=True, capture_output=True)
    run = subprocess.run([str(project / "b" / "use_kinds")], capture_output=True, text=True)
    assert run.stdout.strip() == "linked"


def test_application_installed_linked_and_uninstalled(tmp_path):
    url = remote(tmp_path, "hello", APP, tags=("v0.1.0",))
    bin_dir = tmp_path / "bin"
    code, out = cli("pkg", "install", url, "--bin-dir", str(bin_dir))
    assert code == 0 and "linked" in out, out
    run = subprocess.run([str(bin_dir / "hello-app")], capture_output=True, text=True)
    assert run.stdout.strip() == "hello from an installed application"
    code, out = cli("pkg", "uninstall", "hello")
    assert code == 0 and not os.path.lexists(bin_dir / "hello-app")


def test_upgrade_follows_the_original_range(tmp_path):
    url = remote(tmp_path, "kinds", fobis_package("kinds"), tags=("v1.0.0",))
    assert cli("pkg", "install", url, "--version", "^1.0")[0] == 0
    code, out = cli("pkg", "upgrade")
    assert code == 0 and "up to date" in out
    repo = tmp_path / "remotes" / "kinds"
    from tests.registry_helpers import git

    (repo / "NEWS").write_text("1.1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "1.1")
    git(repo, "tag", "v1.1.0")
    git(repo, "tag", "v2.0.0")  # outside ^1.0
    code, out = cli("pkg", "upgrade", "kinds")
    assert code == 0 and "v1.0.0 -> v1.1.0" in out, out
    code, out = cli("pkg", "list", "--json")
    assert [r["version"] for r in json.loads(out)["packages"]] == ["v1.1.0"]


@pytest.mark.skipif(shutil.which("fpm") is None, reason="fpm")
def test_install_fpm_package_with_fpm(tmp_path):
    url = remote(tmp_path, "vecs", FPM_LIB, tags=("v0.3.0",))
    code, out = cli("pkg", "install", url, "--json")
    assert code == 0, out
    receipt = json.loads(out)
    assert receipt["backend"] == "fpm" and receipt["modules"] == ["vecs"] and receipt["pc_files"]


def test_tests_and_examples_are_never_installed(tmp_path):
    """Found on a real package (test-drive): a mode building every program built and linked its tests."""
    files = {**APP, "test/check_hello.f90": "program check_hello\nend program check_hello\n"}
    files["fobos"] = (
        files["fobos"]
        .replace("src = ./src/", "src = ./src/ ./test/")
        .replace("target = src/hello.f90\noutput = hello-app\n", "")
    )
    url = remote(tmp_path, "hello", files)
    code, out = cli("pkg", "install", url, "--bin-dir", str(tmp_path / "bin"), "--json")
    assert code == 0, out
    assert sorted(os.listdir(tmp_path / "bin")) == ["hello"]


def test_package_without_a_mode_for_the_compiler(tmp_path):
    files = fobis_package("kinds")
    files["fobos"] = files["fobos"].replace("compiler = gnu", "compiler = intel_nextgen")
    url = remote(tmp_path, "kinds", files)
    code, out = cli("pkg", "install", url)
    assert code == 1 and "no mode of the package's fobos uses the gnu compiler" in out


def test_package_with_its_own_dependencies(tmp_path):
    """Found on FLAP: a package's [dependencies] are fetched before it is built."""
    kinds = remote(tmp_path, "kinds", fobis_package("kinds"))
    files = fobis_package("flapish")
    files["src/flapish.f90"] = "module flapish\nuse kinds\nend module flapish\n"
    files["fobos"] += f"\n[dependencies]\nkinds = {kinds}\n"
    url = remote(tmp_path, "flapish", files)
    code, out = cli("pkg", "install", url, "--json")
    assert code == 0, out
    assert json.loads(out)["modules"] == ["flapish", "kinds"]


def test_build_output_that_is_not_utf8(tmp_path):
    """Found on urbanjost/M_strings: a build printed a Latin-1 byte and the decoding crashed the install."""
    script = tmp_path / "latin1.sh"
    script.write_bytes(b"#!/bin/sh\nprintf 'caf\\344\\n'\n")
    script.chmod(0o755)
    assert backends.run([str(script)], str(tmp_path)).strip() == "caf�"


def test_syswork_output_that_is_not_utf8(tmp_path):
    from fobis.utils import syswork

    script = tmp_path / "latin1.sh"
    script.write_bytes(b"#!/bin/sh\nprintf 'caf\\344\\n'\n")
    script.chmod(0o755)
    assert syswork([str(script)]) == [0, "caf�\n"]
