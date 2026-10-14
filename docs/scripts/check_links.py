"""Check every link to a page of the documentation: the page exists, and so does the anchor.

Links are read from the markdown pages (``[text](/path#anchor)``, relative ``./page``, same-page ``#anchor``, front
matter ``link:`` and ``redirect:``), from the sidebar and nav of ``.vitepress/config.mts``, and, as absolute URLs of
the published site, from the README, the Claude skill and FoBiS's own sources. Anchors are computed as VitePress
computes them (its ``slugify`` of the heading's text, ``-1``, ``-2`` for repeated headings, ``{#id}`` attributes),
and a link's anchor goes through the same function, as VitePress does when it renders the link.

Usage::

    python docs/scripts/check_links.py        # report, exit 1 when a link is broken
"""

from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent
ROOT = DOCS.parent
SITE = "https://szaghi.github.io/FoBiS/"
SKIPPED = ("node_modules", ".vitepress", "examples/tutorial/", "examples/output/")
# files outside docs/ that link to the published site
OUTSIDE = ("README.md", ".claude/skills/fobis/SKILL.md", "fobis/**/*.py", "fobis/scaffolds/**/*")

_FENCE = re.compile(r"^\s*(```+|~~~+)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_ATTR_ID = re.compile(r"\s*\{#([^}]+)\}\s*$")
_LINK = re.compile(r"!?\[(?:[^\]\[]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_HTML_ID = re.compile(r"""\b(?:id|name)=["']([^"']+)["']""")
_FRONT_LINK = re.compile(r"^\s*(?:-\s*)?(?:link|redirect):\s*['\"]?(/[^'\"\s]*)")
_CONFIG_LINK = re.compile(r"link:\s*'(/[^']*)'")
_SITE_URL = re.compile(re.escape(SITE) + r"([^\s)\"'<>`]*)")
_SPECIAL = re.compile("[\\s~`!@#$%^&*()\\-_+=\\[\\]{}|\\\\;:\"'\u201c\u201d\u2018\u2019<>,.?/]+")


@dataclass(frozen=True)
class Problem:
    path: str
    line: int
    link: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}: {self.link}"


def slugify(text: str) -> str:
    """VitePress's slugify (``vitepress/src/node/markdown/plugins/slugify``)."""
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not 0x300 <= ord(c) <= 0x36F)
    text = re.sub(r"[\x00-\x1f]", "", text)
    text = re.sub(r"-{2,}", "-", _SPECIAL.sub("-", text)).strip("-")
    return re.sub(r"^(\d)", r"_\1", text).lower()


def _heading_text(raw: str) -> str:
    """The text VitePress slugifies: links reduced to their text, inline HTML dropped, escapes resolved."""
    text = re.sub(r"!?\[((?:[^\]\[]|\[[^\]]*\])*)\]\([^)]*\)", r"\1", raw)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\\(.)", r"\1", text)


def _lines(text: str):
    """``(number, line)`` of a markdown text outside fenced code blocks and front matter."""
    fence = None
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
        start = end + 1
    for number, line in enumerate(lines[start:], start + 1):
        match = _FENCE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker.startswith(fence[:3]) and line.strip() == marker:
                fence = None
            continue
        if fence is None:
            yield number, line


@cache
def anchors(page: Path) -> frozenset[str]:
    """Every anchor of *page*: its headings' ids and the ``id``/``name`` attributes of its HTML."""
    found: dict[str, bool] = {}
    for _, line in _lines(page.read_text(encoding="utf-8")):
        found.update(dict.fromkeys(_HTML_ID.findall(line), True))
        heading = _HEADING.match(line)
        if not heading:
            continue
        title = heading.group(2)
        explicit = _ATTR_ID.search(title)
        slug = explicit.group(1) if explicit else slugify(_heading_text(title))
        unique, index = slug, 1
        while unique in found and not explicit:
            unique, index = f"{slug}-{index}", index + 1
        found[unique] = True
    return frozenset(found)


def target(link: str, page: Path | None) -> tuple[Path | None, str]:
    """The markdown file (or public asset) a site link points to, and its anchor; None when there is none."""
    path, _, anchor = link.partition("#")
    path = path.split("?")[0]
    if path.startswith("/FoBiS/"):
        path = path[len("/FoBiS") :]
    if not path:  # same page
        return page, anchor
    if not path.startswith("/"):
        base = (page.parent if page else DOCS).relative_to(DOCS).as_posix()
        path = "/" + "/".join(p for p in (base, path) if p and p != ".")
    parts = []
    for part in path.split("/"):
        if part == "..":
            if parts:
                parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    clean = "/".join(parts)
    asset = DOCS / "public" / clean
    if clean and asset.is_file():
        return asset, ""
    clean = re.sub(r"\.(html|md)$", "", clean)
    for candidate in (DOCS / f"{clean}.md", DOCS / clean / "index.md"):
        if (clean and candidate.is_file()) or (not clean and candidate == DOCS / "index.md"):
            return candidate, anchor
    return None, anchor


def check_link(link: str, page: Path | None) -> str | None:
    """Why *link* (from *page*) is broken, or None."""
    found, anchor = target(link, page)
    if found is None:
        return "no such page"
    if anchor and found.suffix == ".md" and slugify(anchor) not in anchors(found):
        return f"no anchor #{anchor} in {found.relative_to(DOCS).as_posix()}"
    return None


def _internal(url: str) -> bool:
    return not re.match(r"[a-z][a-z0-9+.-]*:", url) and not url.startswith(("@/", "//"))


def page_links(text: str) -> list[tuple[int, str]]:
    """``(line, link)`` of the internal links of a markdown page (front matter included)."""
    found = []
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for number, line in enumerate(lines[1:], 2):
            if line.strip() == "---":
                break
            match = _FRONT_LINK.match(line)
            if match:
                found.append((number, match.group(1)))
    for number, line in _lines(text):
        line = re.sub(r"`[^`]*`", "", line)  # code spans
        found += [(number, url) for url in _LINK.findall(line) if _internal(url)]
        found += [(number, url) for url in re.findall(r"""href=["']([^"']+)["']""", line) if _internal(url)]
    return found


def problems(docs: Path = DOCS) -> list[Problem]:
    """Every broken link to a documentation page."""
    found = []
    for page in sorted(docs.rglob("*.md")):
        relative = page.relative_to(docs).as_posix()
        if any(part in relative for part in SKIPPED):
            continue
        for number, link in page_links(page.read_text(encoding="utf-8")):
            message = check_link(link, page)
            if message:
                found.append(Problem(relative, number, link, message))
    config = docs / ".vitepress" / "config.mts"
    for number, line in enumerate(config.read_text(encoding="utf-8").splitlines(), 1):
        for link in _CONFIG_LINK.findall(line):
            message = check_link(link, None)
            if message:
                found.append(Problem(config.relative_to(docs).as_posix(), number, link, message))
    for pattern in OUTSIDE:
        for path in sorted(ROOT.glob(pattern)):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                for rest in _SITE_URL.findall(line):
                    rest = rest.rstrip(".,;:*")
                    if re.search(r"\.(json|svg|png|gif)$", rest.partition("#")[0]):  # generated by the deploy
                        continue
                    message = check_link("/" + rest, None)
                    if message:
                        found.append(Problem(path.relative_to(ROOT).as_posix(), number, SITE + rest, message))
    return found


def main() -> int:
    found = problems()
    for problem in found:
        print(problem)
    print(f"{len(found)} broken link(s)" if found else "every link to a documentation page and anchor exists")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
