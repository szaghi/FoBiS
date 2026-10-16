"""Every link to a page of the documentation, and every anchor, exists (docs/scripts/check_links.py)."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "docs" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_links  # noqa: E402


def test_every_link_and_anchor_exists():
    found = check_links.problems()
    assert not found, "\n".join(str(p) for p in found)


def test_slugify_matches_vitepress():
    # values computed by VitePress 2's slugify
    assert check_links.slugify("1. Settings: the command line, then the mode") == (
        "_1-settings-the-command-line-then-the-mode"
    )
    assert check_links.slugify("`[case:NAME]` sections") == "case-name-sections"
    assert check_links.slugify("Lock File & Semver") == "lock-file-semver"


def test_broken_links_are_reported(tmp_path):
    page = check_links.DOCS / "cookbook" / "build.md"
    assert check_links.check_link("/fobos/#every-mode-key", page) is None
    assert check_links.check_link("./verification", page) is None
    assert check_links.check_link("#what-is-compiled-again", page) is None
    assert check_links.check_link("/fobos/#no-such-key", page).startswith("no anchor")
    assert check_links.check_link("/no/such/page", page) == "no such page"


def test_repeated_headings_get_numbered_anchors(tmp_path):
    page = tmp_path / "p.md"
    page.write_text("# T\n\n## Usage\n\n```md\n## Inside a fence\n```\n\n## Usage\n\n## Custom {#here}\n")
    assert check_links.anchors(page) == {"t", "usage", "usage-1", "here"}


def test_redirect_stubs_point_to_pages():
    stubs = 0
    for page in check_links.DOCS.rglob("*.md"):
        if "node_modules" in page.parts:
            continue
        text = page.read_text(encoding="utf-8")
        if text.startswith("---\nredirect:"):
            stubs += 1
            target = text.split("\n", 2)[1].split(":", 1)[1].strip()
            assert check_links.check_link(target, page) is None, f"{page}: {target}"
    assert stubs >= 7
