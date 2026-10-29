"""Any-URL sources (#209 R3): release manifests on static hosting (loopback ``http.server`` and ``file://``),
checksum and archive-safety checks, redirect pages, git tree hashes and moved tags, mirrors, ``fobis publish``.
The R3 exit criterion: a package served from a plain static directory is fetched, verified and built."""

from __future__ import annotations

import configparser
import hashlib
import io
import json
import shutil
import tarfile

import pytest

from fobis.fobis import run_fobis
from fobis.registry import manifest as mf
from fobis.registry.sources import probe
from tests.registry_helpers import cli, fobis_package, git, isolate, remote, static_server

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)
    mf._LOCATED.clear()


def _tarball(files: dict[str, str], top: str = "pkg-1.0.0") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        for path, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"{top}/{path}" if top else path)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _site(root, name, releases: dict[str, dict[str, str]], corrupt: str = "") -> str:
    """A static directory with one archive per release and its manifest; returns the directory."""
    site = root / "site" / name
    site.mkdir(parents=True)
    lines = ["schema = 1", f'name = "{name}"']
    for version, files in releases.items():
        data = _tarball(files, f"{name}-{version}")
        archive = f"{name}-{version}.tar.gz"
        (site / archive).write_bytes(data)
        digest = "0" * 64 if version == corrupt else hashlib.sha256(data).hexdigest()
        lines += ["[[release]]", f'version = "{version}"', f'archive = "{archive}"', f'sha256 = "{digest}"']
    (site / mf.MANIFEST).write_text("\n".join(lines) + "\n")
    return site


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _lock(project) -> dict:
    config = configparser.RawConfigParser()
    config.read(project / ".fobis_deps" / "fobos.lock")
    return {s: dict(config.items(s)) for s in config.sections()}


# ── manifests ────────────────────────────────────────────────────────────────


def test_manifest_schema_errors(tmp_path):
    with pytest.raises(mf.SourceError, match="needs version, archive and sha256"):
        mf.parse_manifest('[[release]]\nversion = "1.0"\n', "x")
    with pytest.raises(mf.SourceError, match="64 hexadecimal"):
        mf.parse_manifest('[[release]]\nversion = "1"\narchive = "a"\nsha256 = "12"\n', "x")
    with pytest.raises(mf.SourceError, match="unknown key"):
        mf.parse_manifest('owner = "x"\n', "x")


def test_probe_static_http_source(tmp_path):
    site = _site(tmp_path, "kinds", {"1.0.0": fobis_package("kinds"), "1.1.0": fobis_package("kinds", "newer kinds")})
    with static_server(tmp_path / "site") as base:
        info = probe(f"{base}/kinds/")
        assert info.provider == "manifest" and info.versions == ["1.1.0", "1.0.0"]
        assert info.description == "newer kinds" and info.modules == ["kinds"] and info.backend == "fobis"
        # the manifest named directly, and under .well-known
        assert probe(f"{base}/kinds/{mf.MANIFEST}", inspect=False).latest == "1.1.0"
    well_known = tmp_path / "site" / "wk" / ".well-known"
    well_known.mkdir(parents=True)
    shutil.copy(site / mf.MANIFEST, well_known / mf.MANIFEST)
    for archive in site.glob("*.tar.gz"):
        shutil.copy(archive, well_known / archive.name)
    assert probe(str(tmp_path / "site" / "wk" / ".well-known"), inspect=False).versions == ["1.1.0", "1.0.0"]


def test_checksum_mismatch_and_unsafe_archive(tmp_path):
    _site(tmp_path, "bad", {"1.0.0": fobis_package("bad")}, corrupt="1.0.0")
    with pytest.raises(mf.SourceError, match="does not match the manifest"):
        probe(str(tmp_path / "site" / "bad"))
    evil = tmp_path / "site" / "evil"
    evil.mkdir()
    data = _tarball({"../../escape.f90": "x"}, top="")
    (evil / "e.tar.gz").write_bytes(data)
    (evil / mf.MANIFEST).write_text(
        f'[[release]]\nversion = "1.0.0"\narchive = "e.tar.gz"\nsha256 = "{hashlib.sha256(data).hexdigest()}"\n'
    )
    with pytest.raises(mf.SourceError, match="refusing to extract"):
        probe(str(evil))
    assert not (tmp_path / "escape.f90").exists()


def test_redirect_page(tmp_path):
    url = remote(tmp_path, "real", fobis_package("real"), tags=("v2.0.0",))
    page = tmp_path / "site" / "pkg"
    page.mkdir(parents=True)
    (page / "index.html").write_text(
        f'<html><head><meta name="fortran-source" content="git {url}"></head><body>real</body></html>\n'
    )
    with static_server(tmp_path / "site") as base:
        located = mf.locate(f"{base}/pkg/")
        assert located.kind == "git" and located.url == url and located.via == [f"{base}/pkg/"]
        assert probe(f"{base}/pkg/", inspect=False).versions == ["v2.0.0"]


def test_redirect_loop(tmp_path):
    page = tmp_path / "site" / "loop"
    page.mkdir(parents=True)
    with static_server(tmp_path / "site") as base:
        (page / "index.html").write_text(f'<meta name="fortran-source" content="git {base}/loop/">\n')
        with pytest.raises(mf.SourceError, match="too many redirects"):
            mf.locate(f"{base}/loop/")


# ── fetch ─────────────────────────────────────────────────────────────────────


def _project(tmp_path, monkeypatch, spec: str):
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.f90").write_text("program main\nuse kinds\ncall kinds_hello()\nend program main\n")
    (project / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\ntarget = src/main.f90\n\n"
        f"[dependencies]\nkinds = {spec}\n"
    )
    monkeypatch.chdir(project)
    return project


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")
def test_static_package_fetched_verified_built(tmp_path, monkeypatch, capsys):
    """The R3 exit criterion: a package served from a plain static directory, fetched, verified, built."""
    _site(tmp_path, "kinds", {"1.0.0": fobis_package("kinds"), "1.2.0": fobis_package("kinds", "newer")})
    with static_server(tmp_path / "site") as base:
        project = _project(tmp_path, monkeypatch, f"{base}/kinds/ :: semver=^1.0")
        code, out = _run(["fetch"], capsys)
        assert code == 0, out
        lock = _lock(project)["kinds"]
        assert lock["provider"] == "manifest" and lock["version"] == "1.2.0" and len(lock["sha256"]) == 64
        assert (project / ".fobis_deps" / "kinds" / "src" / "kinds.f90").is_file()
        code, out = _run(["build"], capsys)
        assert code == 0, out
        assert (project / "build" / "main").is_file()
        # fetched again: nothing downloaded, same release
        code, out = _run(["fetch"], capsys)
        assert code == 0 and "already fetched" in out


def test_static_package_pinned_and_changed_release_detected(tmp_path, monkeypatch, capsys):
    site = _site(tmp_path, "kinds", {"1.0.0": fobis_package("kinds"), "1.2.0": fobis_package("kinds")})
    project = _project(tmp_path, monkeypatch, f"file://{site} :: tag=1.0.0")
    assert _run(["fetch", "--no-build"], capsys)[0] == 0
    assert _lock(project)["kinds"]["version"] == "1.0.0"
    # the release archive is replaced under the same version: --update must refuse it
    data = _tarball({"src/kinds.f90": "module kinds\nend module kinds\n"}, "kinds-1.0.0")
    (site / "kinds-1.0.0.tar.gz").write_bytes(data)
    text = (site / mf.MANIFEST).read_text()
    old = text.split('sha256 = "')[1].split('"')[0]
    (site / mf.MANIFEST).write_text(text.replace(old, hashlib.sha256(data).hexdigest(), 1))
    mf._LOCATED.clear()
    code, out = _run(["fetch", "--update", "--no-build"], capsys)
    assert code == 1 and "release 1.0.0 changed" in out


def test_moved_git_tag_detected(tmp_path, monkeypatch, capsys):
    url = remote(tmp_path, "kinds", fobis_package("kinds"), tags=("v1.0.0",))
    project = _project(tmp_path, monkeypatch, f"{url} :: tag=v1.0.0")
    assert _run(["fetch", "--no-build"], capsys)[0] == 0
    tree = _lock(project)["kinds"]["tree"]
    assert len(tree) == 40
    repo = tmp_path / "remotes" / "kinds"
    (repo / "NEWS").write_text("moved\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "moved")
    git(repo, "tag", "-f", "v1.0.0")
    shutil.rmtree(project / ".fobis_deps" / "kinds")
    _, out = _run(["fetch", "--no-build"], capsys)
    assert "tag v1.0.0 of kinds moved" in out


def test_mirror_used_when_the_source_fails(tmp_path, monkeypatch, capsys):
    url = remote(tmp_path, "kinds", fobis_package("kinds"))
    mirror = tmp_path / "mirror.git"
    git(tmp_path, "clone", "-q", "--mirror", url, str(mirror))
    project = _project(tmp_path, monkeypatch, f"file://{tmp_path}/gone :: tag=v1.0.0 :: mirror=file://{mirror}")
    code, out = _run(["fetch", "--no-build"], capsys)
    assert code == 0 and "from mirror" in out, out
    assert (project / ".fobis_deps" / "kinds" / "src" / "kinds.f90").is_file()


# ── publish ───────────────────────────────────────────────────────────────────


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")
def test_publish_round_trip(tmp_path, monkeypatch, capsys):
    """publish --archive -> serve -> add -> fetch -> build; publish --index lists the project."""
    url = remote(tmp_path, "kinds", fobis_package("kinds", "kinds for all"), tags=("v1.0.0",))
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", url, str(work))
    monkeypatch.chdir(work)
    dist = tmp_path / "site" / "kinds"
    code, out = cli("publish", "--archive", str(dist))
    assert code == 0 and "kinds-1.0.0.tar.gz" in out, out
    manifest = mf.parse_manifest((dist / mf.MANIFEST).read_text(), "x")
    assert [r.version for r in manifest.releases] == ["1.0.0"]
    code, out = cli("publish", "--archive", str(dist))
    assert code == 2 and "already published" in out
    index = tmp_path / "my-index" / "index.toml"
    index.parent.mkdir()
    code, out = cli("publish", "--index", str(index), "--source", "https://example.org/kinds/")
    assert code == 0
    text = index.read_text()
    assert '[package.kinds]\nsource = "https://example.org/kinds/"\ndescription = "kinds for all"' in text
    assert 'provides = ["kinds"]' in text
    with static_server(tmp_path / "site") as base:
        project = _project(tmp_path, monkeypatch, f"{base}/kinds/")
        code, out = _run(["fetch"], capsys)
        assert code == 0, out
        assert _run(["build"], capsys)[0] == 0
        assert (project / "build" / "main").is_file()
        assert json.loads(json.dumps(_lock(project)["kinds"]))["version"] == "1.0.0"
