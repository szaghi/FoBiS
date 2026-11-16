"""The one-line installer, scripts/install.sh rendered by fobis scaffold (GH #217).

Two tiers. The selection, option and exit-status rules run against stub tools on PATH (no compiler needed). The
installs build tests/installer-test1 (a one-module library shipping a fobos, an fpm.toml, a CMakeLists.txt and a
makefile) with each real build system available, link a consumer through the generated pkg-config file and uninstall.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from fobis.Fobos import Fobos
from fobis.Scaffolder import Scaffolder, get_project_vars

FIXTURE = Path(__file__).parent / "installer-test1"


class _DemoFobos:
    """The fixture's fobos values, with an optional [installer] configuration."""

    def __init__(self, **installer):
        self._installer = installer

    def get_scaffold_config(self):
        return {"toolchain": "linux-gnu"}

    def get_project_info(self):
        return {"name": "demo", "authors": [], "repository": "https://github.com/o/demo"}

    def get_dependencies(self):
        return {}

    def get_installer_config(self):
        cfg = dict(Fobos._INSTALLER_KEYS)
        cfg.update(self._installer)
        return cfg


def _render(tmp_path: Path, **installer) -> Path:
    """Render scripts/install.sh for the fixture project into tmp_path/install.sh."""
    s = Scaffolder(project_vars=get_project_vars(fobos=_DemoFobos(**installer)), cwd=str(tmp_path))
    script = tmp_path / "install.sh"
    script.write_text(s._get_canonical(s.manifest["scripts/install.sh"]), encoding="utf-8")
    script.chmod(0o755)
    return script


def _tree(tmp_path: Path, files: tuple[str, ...]) -> Path:
    """A source tree shipping the given build files (their content does not matter to detection)."""
    src = tmp_path / "src-tree"
    src.mkdir()
    for name in files:
        (src / name).write_text("\n", encoding="utf-8")
    return src


def _stub_env(tmp_path: Path, tools: tuple[str, ...]) -> dict[str, str]:
    """PATH with stubs: gfortran (version 16.2.0) and each named tool; nothing else of the user's toolchain."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "gfortran").write_text("#!/bin/sh\necho 16.2.0\n", encoding="utf-8")
    for tool in tools:
        (bindir / tool).write_text('#!/bin/sh\necho "$0 $*" >> "$STUB_LOG"\n', encoding="utf-8")
    for stub in bindir.iterdir():
        stub.chmod(0o755)
    for util in _UTILS:  # the system utilities the script uses, and nothing else of the system (no real cmake, fpm)
        real = shutil.which(util)
        if real and not (bindir / util).exists():
            (bindir / util).symlink_to(real)
    return {"PATH": str(bindir), "HOME": str(tmp_path), "STUB_LOG": str(tmp_path / "stub.log"), "TMPDIR": str(tmp_path)}


_UTILS = (
    "bash",
    "sh",
    "basename",
    "dirname",
    "tar",
    "mktemp",
    "sed",
    "grep",
    "tr",
    "sort",
    "rm",
    "rmdir",
    "mkdir",
    "cat",
    "comm",
    "find",
    "cp",
    "uname",
    "head",
    "tail",
    "tee",
    "wc",
    "awk",
)


def _run(script: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    """The installer with no terminal: a new session has no controlling terminal, so /dev/tty cannot be opened and the
    menu never shows (stdin alone is not enough: under an interactive pytest the installer would read the keyboard)."""
    return subprocess.run(
        ["bash", str(script), *args],
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        check=False,
    )


# -- options and selection (stub tools) --------------------------------------------------------------------------------


def test_version_and_help(tmp_path):
    script = _render(tmp_path)
    env = _stub_env(tmp_path, ())
    assert _run(script, env, "--version").stdout.strip() == "install.sh 2"
    out = _run(script, env, "--help")
    assert (
        out.returncode == 0 and "curl -fsSL https://github.com/o/demo/releases/latest/download/install.sh" in out.stdout
    )


@pytest.mark.parametrize("args", [("--bogus",), ("--build", "scons"), ("--prefix",)])
def test_usage_errors_exit_2(tmp_path, args):
    assert _run(_render(tmp_path), _stub_env(tmp_path, ()), *args).returncode == 2


def test_a_single_build_system_is_used_whatever_the_order(tmp_path):
    """A project shipping only CMake builds with CMake, though cmake is third in the order."""
    out = _run(
        _render(tmp_path),
        _stub_env(tmp_path, ("fobis", "cmake")),
        "--source",
        str(_tree(tmp_path, ("CMakeLists.txt",))),
        "--dry-run",
    )
    assert out.returncode == 0, out.stderr
    assert "build system: cmake (available: cmake)" in out.stderr


def test_build_naming_a_system_not_shipped_is_a_usage_error(tmp_path):
    out = _run(
        _render(tmp_path),
        _stub_env(tmp_path, ("make",)),
        "--source",
        str(_tree(tmp_path, ("fobos",))),
        "--build",
        "make",
    )
    assert out.returncode == 2
    assert "--build make: demo ships fobis only" in out.stderr


def test_several_systems_without_a_terminal_take_the_order(tmp_path):
    """No --build, no terminal: the first of fobis, fpm, cmake, make that the sources ship."""
    tree = _tree(tmp_path, ("makefile", "CMakeLists.txt", "fpm.toml"))
    out = _run(_render(tmp_path), _stub_env(tmp_path, ("fpm", "cmake", "make")), "--source", str(tree), "--dry-run")
    assert out.returncode == 0, out.stderr
    assert "build system: fpm (available: fpm cmake make)" in out.stderr


def test_several_systems_with_a_terminal_ask(tmp_path):
    """No --build, a terminal: the menu; the answer picks the build system (driven through a pty by script(1))."""
    if not shutil.which("script"):
        pytest.skip("script(1) not available")
    script = _render(tmp_path)
    tree = _tree(tmp_path, ("fobos", "fpm.toml", "CMakeLists.txt"))
    env = _stub_env(tmp_path, ("fobis", "fpm", "cmake"))
    env["PATH"] += os.pathsep + os.path.dirname(shutil.which("script"))
    command = f"bash {script} --source {tree} --dry-run"
    out = subprocess.run(
        ["script", "-qec", command, "/dev/null"], env=env, input="3\n", capture_output=True, text=True, check=False
    )
    assert "Choose [1-3, default 1]" in out.stdout
    assert "build system: cmake" in out.stdout, out.stdout


def test_the_chosen_tool_must_exist(tmp_path):
    """--build fpm without fpm: a usage error naming the alternatives."""
    out = _run(
        _render(tmp_path),
        _stub_env(tmp_path, ("cmake",)),
        "--source",
        str(_tree(tmp_path, ("fpm.toml", "CMakeLists.txt"))),
        "--build",
        "fpm",
    )
    assert out.returncode == 2 and "fpm not found" in out.stderr and "fpm cmake" in out.stderr


def test_dry_run_builds_nothing(tmp_path):
    env = _stub_env(tmp_path, ("cmake",))
    out = _run(
        _render(tmp_path),
        env,
        "--source",
        str(_tree(tmp_path, ("CMakeLists.txt",))),
        "--dry-run",
        "--prefix",
        str(tmp_path / "prefix"),
    )
    assert out.returncode == 0, out.stderr
    assert "dry run: would build demo local with cmake" in out.stderr
    assert not (tmp_path / "stub.log").exists() and not (tmp_path / "prefix").exists()


def test_deps_shows_the_command(tmp_path):
    """--deps prints the package command first (apt-get stubbed: no root, no network)."""
    env = _stub_env(tmp_path, ("cmake", "apt-get", "sudo", "id"))
    out = _run(
        _render(tmp_path, apt="libfoo-dev"),
        env,
        "--source",
        str(_tree(tmp_path, ("CMakeLists.txt",))),
        "--deps",
        "--dry-run",
    )
    assert out.returncode == 0, out.stderr
    assert "apt-get install -y libfoo-dev" in out.stderr


def test_uninstall_without_install_is_a_no_op(tmp_path):
    out = _run(_render(tmp_path), _stub_env(tmp_path, ()), "--uninstall", "--prefix", str(tmp_path / "prefix"))
    assert out.returncode == 0 and "nothing of demo installed" in out.stderr


# -- real installs of the fixture library -------------------------------------------------------------------------------


def _real_env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update({"HOME": str(tmp_path), "TMPDIR": str(tmp_path)})
    env.pop("FC", None)
    return env


_TOOLS = {"fobis": "fobis", "fpm": "fpm", "cmake": "cmake", "make": "make"}


@pytest.mark.parametrize("build", ["fobis", "fpm", "cmake", "make"])
def test_install_link_uninstall(tmp_path, build):
    """Each build system installs the fixture per compiler, a consumer links through pkg-config, uninstall empties."""
    for tool in ("gfortran", "pkg-config", _TOOLS[build]):
        if not shutil.which(tool):
            pytest.skip(f"{tool} not available")
    script = _render(tmp_path)
    prefix = tmp_path / "prefix"
    env = _real_env(tmp_path)
    out = _run(script, env, "--source", str(FIXTURE), "--build", build, "--prefix", str(prefix), "--fc", "gfortran")
    assert out.returncode == 0, out.stderr
    tag = "gnu-" + subprocess.run(["gfortran", "-dumpfullversion"], capture_output=True, text=True).stdout.strip()
    if build == "make":  # the makefile's own install target: its layout (lib/, include/), not the per-compiler one
        assert (prefix / "lib" / "libdemo.a").is_file()
    else:
        assert (prefix / "lib" / "demo" / tag / "libdemo.a").is_file()
    assert (prefix / "lib" / "pkgconfig" / f"demo-{tag}.pc").is_file() and (prefix / "lib/pkgconfig/demo.pc").is_file()
    assert (prefix / "share" / "demo" / tag / "manifest").is_file()

    consumer = tmp_path / "consumer.f90"
    consumer.write_text('program c\nuse demo\nprint "(I0)", answer()\nend program\n', encoding="utf-8")
    flags = subprocess.run(
        ["pkg-config", "--cflags", "--libs", "demo"],
        env={**env, "PKG_CONFIG_PATH": str(prefix / "lib/pkgconfig")},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    subprocess.run(["gfortran", str(consumer), *flags, "-o", str(tmp_path / "c")], check=True, cwd=tmp_path)
    assert subprocess.run([str(tmp_path / "c")], capture_output=True, text=True).stdout.strip() == "42"

    out = _run(script, env, "--uninstall", "--prefix", str(prefix))
    assert out.returncode == 0, out.stderr
    left = [p for p in prefix.rglob("*") if "venv" not in p.parts]
    assert left == [], left


def test_make_without_install_target_copies_the_declared_dirs(tmp_path):
    """A makefile without install: [installer] make_lib/make_mod say where the library and modules are."""
    for tool in ("gfortran", "make"):
        if not shutil.which(tool):
            pytest.skip(f"{tool} not available")
    src = tmp_path / "src-noinstall"
    shutil.copytree(FIXTURE, src)
    text = (src / "makefile").read_text(encoding="utf-8")
    (src / "makefile").write_text(text.split("\ninstall:")[0] + "\n", encoding="utf-8")
    prefix = tmp_path / "prefix"
    env = _real_env(tmp_path)
    no_keys = _run(_render(tmp_path), env, "--source", str(src), "--build", "make", "--prefix", str(prefix))
    assert no_keys.returncode == 1 and "declare [installer] make_lib" in no_keys.stderr
    script = _render(tmp_path, make_lib=".", make_mod=".")
    out = _run(script, env, "--source", str(src), "--build", "make", "--prefix", str(prefix), "--fc", "gfortran")
    assert out.returncode == 0, out.stderr
    assert list((prefix / "lib" / "demo").glob("*/libdemo.a")) and list(
        (prefix / "include" / "demo").glob("*/demo.mod")
    )


def test_pre_and_check_rules_run(tmp_path):
    """[installer] pre and check: fobos rules run before the build and after the install (PREFIX exported)."""
    for tool in ("gfortran", "fobis"):
        if not shutil.which(tool):
            pytest.skip(f"{tool} not available")
    src = tmp_path / "src-rules"
    shutil.copytree(FIXTURE, src)
    with (src / "fobos").open("a", encoding="utf-8") as fobos:
        fobos.write(
            "\n[rule-native]\nrule = touch native.done\n"
            '\n[rule-smoke]\nrule = bash -c \'test -n "$PREFIX" && touch "$PREFIX/smoke.done"\'\n'
        )
    prefix = tmp_path / "prefix"
    script = _render(tmp_path, pre="native", check="smoke")
    out = _run(
        script,
        _real_env(tmp_path),
        "--source",
        str(src),
        "--build",
        "fobis",
        "--prefix",
        str(prefix),
        "--fc",
        "gfortran",
        "--verbose",
    )
    assert out.returncode == 0, out.stderr
    assert "pre-build: fobis rule --ex native" in out.stderr and (prefix / "smoke.done").is_file()
