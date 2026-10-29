"""Helpers of the package-index tests (#209): git remotes with tags served as ``file://`` URLs, a loopback static
HTTP server, the CLI run in-process with Typer's runner."""

from __future__ import annotations

import functools
import http.server
import os
import subprocess
import threading
from contextlib import contextmanager

from typer.testing import CliRunner

from fobis.cli import app

GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false"]


def git(cwd, *args) -> str:
    result = subprocess.run(["git", *GIT_ID, *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout


def remote(root, name, files, tags=("v1.0.0",), more=None) -> str:
    """
    A git repository *root*/remotes/*name* holding *files*, committed and tagged with each of *tags*; *more* maps a
    later tag to the files changed before it. Returns its ``file://`` URL.
    """
    repo = root / "remotes" / name
    for path, text in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
    git(repo, "init", "-q", "-b", "master")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    for tag in tags:
        git(repo, "tag", tag)
    for tag, changed in (more or {}).items():
        for path, text in changed.items():
            (repo / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / path).write_text(text)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", f"towards {tag}")
        git(repo, "tag", tag)
    return f"file://{repo}"


def module_source(name: str, body: str = "") -> str:
    return f"module {name}\nimplicit none\n{body}contains\nsubroutine {name}_hello()\nend subroutine {name}_hello\nend module {name}\n"


def fobis_package(name: str, summary: str = "", modules=None) -> dict[str, str]:
    """Files of a FoBiS library project named *name* (one module per name of *modules*, default *name*)."""
    files = {
        "fobos": f"[project]\nname = {name}\nsummary = {summary or name + ' library'}\n\n"
        "[modes]\nmodes = lib\n\n[lib]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\nmod_dir = ./mod/\n"
        f"obj_dir = ./obj/\ntarget = src/{(modules or [name])[0]}.f90\nmklib = static\noutput = lib{name}.a\n",
        "LICENSE": "MIT License\n\nPermission is hereby granted, free of charge, to any person ...\n",
    }
    for module in modules or [name]:
        files[f"src/{module}.f90"] = module_source(module)
    return files


@contextmanager
def static_server(directory):
    """Serve *directory* on a loopback port; yields the base URL (no trailing slash)."""
    handler = functools.partial(_QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # no request log in the test output
        pass


def cli(*args, env=None):
    """Run ``fobis ARGS`` in-process; returns (exit code, stdout + stderr)."""
    result = CliRunner().invoke(app, list(args), env=env, catch_exceptions=False)
    return result.exit_code, result.output


def isolate(monkeypatch, tmp_path):
    """A user configuration, index cache and package store of the test only."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("FOBIS_INDEX_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("FOBIS_PKGS_DIR", str(tmp_path / "pkgs"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
