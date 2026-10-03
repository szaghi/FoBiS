"""Tests for the scaffolded scripts/release.sh: its recovery hints must match what actually happened."""

from __future__ import annotations

import os
import shutil
import subprocess
from importlib import resources

import pytest

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="release.sh needs bash")

TEMPLATE = resources.files("fobis") / "scaffolds" / "verbatim" / "scripts" / "release.sh"


def git(cwd, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A released project (v1.0.0) with one unreleased commit, a local bare origin and a git-cliff stub."""
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = T\n\temail = t@example.com\n[commit]\n\tgpgsign = false\n[tag]\n\tgpgSign = false\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    bindir = tmp_path / "bin"  # `git cliff` runs the git-cliff executable found on PATH
    bindir.mkdir()
    stub = bindir / "git-cliff"
    stub.write_text('#!/usr/bin/env bash\n# git-cliff --tag TAG --output FILE\necho "## [$2]" > "$4"\n')
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")

    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "master", str(bare))
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(bare), str(work))
    (work / "scripts").mkdir()
    shutil.copy(str(TEMPLATE), work / "scripts" / "release.sh")
    (work / "scripts" / "release.sh").chmod(0o755)
    (work / "VERSION").write_text("v1.0.0\n")
    (work / "CHANGELOG.md").write_text("## [v1.0.0]\n")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "feat: first")
    git(work, "tag", "-a", "v1.0.0", "-m", "v1.0.0")
    (work / "src.f90").write_text("! change\n")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "fix: a change")
    git(work, "push", "-q", "origin", "master", "--tags")
    return work


def release(repo, answer: str = "y\n"):
    return subprocess.run(
        ["./scripts/release.sh", "v1.0.1"], cwd=repo, input=answer, capture_output=True, text=True, check=False
    )


def hint_commands(output: str) -> list[str]:
    """The commands the recovery message tells to run (4-space indented lines)."""
    return [line.strip() for line in output.splitlines() if line.startswith("    ") and line.strip().startswith("git ")]


def test_release_succeeds(repo):
    result = release(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert git(repo, "ls-remote", "--tags", "origin", "refs/tags/v1.0.1")
    assert (repo / "VERSION").read_text().strip() == "v1.0.1"


def test_declined_changes_nothing(repo):
    head = git(repo, "rev-parse", "HEAD")
    result = release(repo, "n\n")
    assert result.returncode == 0 and "Aborted" in result.stdout
    assert git(repo, "rev-parse", "HEAD") == head
    assert not git(repo, "status", "--porcelain")


def test_failed_commit_reports_bumped_and_its_hint_restores_the_tree(repo):
    git(repo, "config", "commit.gpgsign", "true")
    git(repo, "config", "gpg.program", "false")  # signing fails: the commit is refused
    head = git(repo, "rev-parse", "HEAD")
    result = release(repo)
    out = result.stdout + result.stderr
    assert result.returncode != 0
    assert "FAILED at stage: bumped" in out  # not "committed": no commit was made
    assert "git tag" not in out  # tagging now would tag the previous commit
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "status", "--porcelain")  # release files modified, and staged
    for command in hint_commands(out):
        subprocess.run(command, cwd=repo, shell=True, check=True)
    assert not git(repo, "status", "--porcelain")  # the hint really restores the tree
    assert (repo / "VERSION").read_text().strip() == "v1.0.0"


def test_failed_tag_reports_committed_and_its_hint_completes_the_release(repo):
    git(repo, "config", "tag.gpgSign", "true")
    git(repo, "config", "gpg.program", "false")  # the commit is fine, signing the tag fails
    result = release(repo)
    out = result.stdout + result.stderr
    assert result.returncode != 0
    assert "FAILED at stage: committed" in out
    assert git(repo, "log", "-1", "--format=%s") == "chore(release): v1.0.1"
    assert not git(repo, "tag", "-l", "v1.0.1")
    git(repo, "config", "tag.gpgSign", "false")
    for command in hint_commands(out):
        subprocess.run(command, cwd=repo, shell=True, check=True)
    assert git(repo, "ls-remote", "--tags", "origin", "refs/tags/v1.0.1")


def test_failed_push_reports_tagged_and_its_hint_completes_the_release(repo, tmp_path):
    git(repo, "config", "remote.origin.pushurl", str(tmp_path / "nowhere.git"))
    result = release(repo)
    out = result.stdout + result.stderr
    assert result.returncode != 0
    assert "FAILED at stage: tagged" in out
    assert git(repo, "tag", "-l", "v1.0.1") == "v1.0.1"
    git(repo, "config", "--unset", "remote.origin.pushurl")
    for command in hint_commands(out):
        subprocess.run(command, cwd=repo, shell=True, check=True)
    assert git(repo, "ls-remote", "--tags", "origin", "refs/tags/v1.0.1")


def test_die_after_confirmation_prints_the_recovery_hint(repo):
    """`die` exits without firing the ERR trap: after the confirmation it must still show how to recover."""
    script = repo / "scripts" / "release.sh"
    anchor = 'success "VERSION updated to ${NEW_TAG}"\n'
    text = script.read_text()
    assert text.count(anchor) == 1
    script.write_text(text.replace(anchor, anchor + 'die "injected failure"\n'))
    git(repo, "commit", "-qam", "test: inject a failure")
    git(repo, "push", "-q")
    result = release(repo)
    out = result.stdout + result.stderr
    assert result.returncode == 1
    assert "injected failure" in out
    assert "FAILED at stage: bumped" in out
    for command in hint_commands(out):
        subprocess.run(command, cwd=repo, shell=True, check=True)
    assert not git(repo, "status", "--porcelain")


def test_die_before_confirmation_prints_no_recovery_hint(repo):
    (repo / "dirty.txt").write_text("x")  # pre-flight refuses a dirty tree
    result = release(repo)
    assert result.returncode == 1
    assert "working tree is dirty" in result.stderr
    assert "FAILED at stage" not in result.stdout + result.stderr
