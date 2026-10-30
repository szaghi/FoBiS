"""Advisories, witnesses and Software Heritage (#209 R7): ``fortran-advisories.toml`` published by a package after
the locked version, ``fobis audit`` (affected -> exit 1, unaffected ok), ``--witness`` against a mirror (agrees, and a
mirror whose tag was moved), and the Software Heritage fallback of ``fetch`` (``:: archive=swh``) against a local
fake of its API, the content checked against the lock's tree hash."""

from __future__ import annotations

import configparser
import http.server
import json
import shutil
import subprocess
import threading

import pytest

from fobis.fobis import run_fobis
from fobis.registry.advisories import parse_advisories
from fobis.registry.index import RegistryError
from tests.registry_helpers import cli, fobis_package, git, isolate, remote

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git")

ADVISORY = (
    'schema = 1\n[[advisory]]\nid = "KINDS-2026-001"\naffected = "<1.1.0"\nseverity = "high"\n'
    'summary = "wrong kind for 128-bit reals"\nurl = "https://example.org/kinds/1"\n'
)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _project(tmp_path, monkeypatch, spec):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "fobos").write_text(f"[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\n\n[dependencies]\nkinds = {spec}\n")
    monkeypatch.chdir(project)
    return project


def test_advisory_schema():
    (advisory,) = parse_advisories(ADVISORY)
    assert advisory.affects("v1.0.3") and not advisory.affects("1.1.0")
    with pytest.raises(RegistryError, match="severity must be one of"):
        parse_advisories(ADVISORY.replace('"high"', '"urgent"'))
    with pytest.raises(RegistryError, match="missing summary"):
        parse_advisories('[[advisory]]\nid = "x"\naffected = "<1"\nseverity = "low"\n')


def test_audit_reads_advisories_published_after_the_locked_version(tmp_path, monkeypatch, capsys):
    url = remote(tmp_path, "kinds", fobis_package("kinds"), tags=("v1.0.0",))
    project = _project(tmp_path, monkeypatch, f"{url} :: tag=v1.0.0")
    assert _run(["fetch", "--no-build"], capsys)[0] == 0
    code, out = cli("audit")
    assert code == 0 and "ok" in out
    repo = tmp_path / "remotes" / "kinds"
    (repo / "fortran-advisories.toml").write_text(ADVISORY)  # published later, on the default branch
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "advisory")
    code, out = cli("audit", "--json")
    data = json.loads(out)
    assert code == 1 and data["dependencies"][0]["advisories"][0]["id"] == "KINDS-2026-001"
    assert "kinds v1.0.0: KINDS-2026-001 (high)" in data["problems"][0]
    del project


def test_witness_agrees_and_disagrees(tmp_path, monkeypatch, capsys):
    url = remote(tmp_path, "kinds", fobis_package("kinds"), tags=("v1.0.0",))
    mirror = tmp_path / "mirror.git"
    git(tmp_path, "clone", "-q", "--mirror", url, str(mirror))
    _project(tmp_path, monkeypatch, f"{url} :: tag=v1.0.0 :: mirror=file://{mirror}")
    assert _run(["fetch", "--no-build"], capsys)[0] == 0
    code, out = cli("audit", "--witness")
    assert code == 0 and sum(line.endswith(": agrees") for line in out.splitlines()) == 2
    # the tag is moved on the mirror only: the witness disagrees
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", f"file://{mirror}", str(work))
    (work / "NEWS").write_text("moved\n")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "moved")
    git(work, "tag", "-f", "v1.0.0")
    git(work, "push", "-q", "-f", "origin", "v1.0.0")
    code, out = cli("audit", "--witness")
    assert code == 1 and sum(line.endswith(": DIFFERS") for line in out.splitlines()) == 1


def test_a_mirror_lacking_the_tag_is_not_a_disagreement(tmp_path, monkeypatch, capsys):
    """Found by the packages tutorial: a mirror that lags (v1.1.0 not pushed there yet) was reported DIFFERS."""
    url = remote(tmp_path, "kinds", fobis_package("kinds"), tags=("v1.0.0",))
    mirror = tmp_path / "mirror.git"
    git(tmp_path, "clone", "-q", "--mirror", url, str(mirror))
    git(tmp_path / "remotes" / "kinds", "tag", "v1.1.0")  # at the source only
    _project(tmp_path, monkeypatch, f"{url} :: tag=v1.1.0 :: mirror=file://{mirror}")
    assert _run(["fetch", "--no-build"], capsys)[0] == 0
    code, out = cli("audit", "--witness")
    assert code == 0, out
    assert any(line.endswith(": agrees") for line in out.splitlines())
    assert any(line.endswith(": lacks v1.1.0") for line in out.splitlines())


class _FakeSWH(http.server.BaseHTTPRequestHandler):
    """The Software Heritage endpoints FoBiS calls, for one origin with one tag."""

    tree = ""
    tarball = b""

    def log_message(self, *args):  # no request log in the test output
        pass

    def _send(self, payload, content="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", content)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path
        if "/visit/latest/" in path:
            return self._send({"snapshot": "snap1"})
        if path.endswith("/snapshot/snap1/"):
            return self._send({"branches": {"refs/tags/v1.0.0": {"target": "rel1", "target_type": "release"}}})
        if path.endswith("/release/rel1/"):
            return self._send({"target": "rev1", "target_type": "revision"})
        if path.endswith("/revision/rev1/"):
            return self._send({"directory": self.tree})
        if path.endswith("/raw/"):
            return self._send(self.tarball, "application/gzip")
        self.send_error(404)

    def do_POST(self):
        return self._send({"status": "done", "fetch_url": f"/api/1/vault/flat/swh:1:dir:{self.tree}/raw/"})


def test_software_heritage_fallback(tmp_path, monkeypatch, capsys):
    url = remote(tmp_path, "kinds", fobis_package("kinds"), tags=("v1.0.0",))
    repo = tmp_path / "remotes" / "kinds"
    _FakeSWH.tree = git(repo, "rev-parse", "v1.0.0^{tree}").strip()
    _FakeSWH.tarball = subprocess.run(
        ["git", "archive", "--format=tar.gz", f"--prefix=swh:1:dir:{_FakeSWH.tree}/", "v1.0.0"],
        cwd=repo, capture_output=True, check=True,
    ).stdout  # fmt: skip
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeSWH)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("FOBIS_SWH_API", f"http://127.0.0.1:{server.server_address[1]}/api/1/")
    try:
        project = _project(tmp_path, monkeypatch, f"{url} :: tag=v1.0.0 :: archive=swh")
        assert _run(["fetch", "--no-build"], capsys)[0] == 0
        lock = configparser.RawConfigParser()
        lock.read(project / ".fobis_deps" / "fobos.lock")
        assert lock.get("kinds", "tree") == _FakeSWH.tree
        # the source disappears: the archived copy is fetched and checked against the lock's tree
        shutil.rmtree(repo)
        shutil.rmtree(project / ".fobis_deps" / "kinds")
        code, out = _run(["fetch", "--no-build"], capsys)
        assert code == 0 and "from Software Heritage" in out, out
        assert (project / ".fobis_deps" / "kinds" / "src" / "kinds.f90").is_file()
        # an archive whose content differs from the lock is refused
        _FakeSWH.tree = "0" * 40
        shutil.rmtree(project / ".fobis_deps" / "kinds")
        code, out = _run(["fetch", "--no-build"], capsys)
        assert code == 1 and "does not match the lock" in out
    finally:
        server.shutdown()
        server.server_close()
