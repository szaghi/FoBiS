"""merge.py — ``fobis merge-assist``: proposals for resolving merge conflicts, checked by the compiler.

FoBiS never touches the git state: it reads the three index stages of each conflicted file, proposes a
resolution per conflict hunk, and (with ``--apply``, hunk by hunk, after the user accepts) writes the file in the
working tree. It never runs ``git add``, ``merge --continue`` or ``rebase --continue``.

Pipeline, per conflicted file:

1. **Hunks from the stages**: base (``:1:``), ours (``:2:``) and theirs (``:3:``) are merged again with ``git
   merge-file --diff3``; the conflict blocks are the hunks. This does not depend on ``merge.conflictStyle`` or on
   edits the user already made to the file.
2. **Deterministic pre-pass** (no model): one side equals the base -> the other side; the sides differ only in
   whitespace -> ours; both sides change ``use ..., only:`` lines -> three-way union (names a side removed stay
   removed); one side only appended/prepended lines and the other only edited the base lines -> both, as a
   medium-confidence draft the model refines; both sides move a fobos ``[dependencies]`` ``tag=`` pin -> the
   higher version, flagged.
3. **Model** for the remaining hunks (`build_bundle`): base/ours/theirs, the context, the commit messages of each
   side since the merge base (their intent), the procedures at the conflict. Schema: strategy
   ``ours|theirs|both|custom`` (FoBiS builds the text of the first three itself), ``merged_text`` for ``custom``,
   rationale, confidence, risks, citations.
4. **Verification**: the resolved file is compiled in a scratch directory (syntax only, the mode's compiler;
   unresolved hunks stand in as ours, their errors ignored);
   errors on a model's hunk are fed back (at most 2 retries); a proposal that still fails is reported as failing.
   A module that is not built makes the check impossible, not failed.

`replay` measures the pre-pass on historical merges of a repository (in a clone).
"""

# Copyright (C) 2015  Stefano Zaghi
#
# This file is part of FoBiS.py.
#
# FoBiS.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FoBiS.py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with FoBiS.py. If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..llm.provider import messages
from .change import FORTRAN_EXTENSIONS, Git, _git
from .diagnostics import Diagnostic, parse_diagnostics
from .explain import missing_module_name
from .grounding import ContextBundle, Source, _parse, load_prompt

if TYPE_CHECKING:
    from ..llm.provider import Provider

STRATEGIES = ["ours", "theirs", "both", "custom"]
CONFIDENCE = ["low", "medium", "high"]
MAX_RETRIES = 2

_MARKERS = re.compile(r"^(<{7}|\|{7}|={7}|>{7})( |$)")
_USE = re.compile(
    r"^(?P<indent>\s*)use\s*(?:,\s*(?P<nature>(?:non_)?intrinsic)\s*::\s*|::\s*|\s+)(?P<module>\w+)"
    r"\s*(?:,\s*only\s*:\s*(?P<only>.*?))?\s*(?:!.*)?$",
    re.IGNORECASE,
)
_PIN = re.compile(r"^\s*(?P<name>[\w.-]+)\s*=\s*(?P<spec>\S.*?)\s*$")
_TAG = re.compile(r"::\s*tag\s*=\s*(?P<tag>[^\s:]+)")
_SECTION = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")
_PROC_HEADER = re.compile(
    r"^\s*(?:(?:pure|impure|elemental|recursive|module|non_recursive)\s+)*"
    r"(?:[\w(),=*:\s]+\s+)?(?P<kind>subroutine|function)\s+(?P<name>\w+)",
    re.IGNORECASE,
)
_PROC_END = re.compile(r"^\s*end\s+(subroutine|function)\b", re.IGNORECASE)


# ── the git state ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Operation:
    """The operation that stopped on conflicts, and what "ours" and "theirs" really are.

    Attributes
    ----------
    kind : str
        ``merge``, ``rebase``, ``cherry-pick``, ``revert`` or ``unknown``.
    ours, theirs : str
        Revisions of stage 2 and stage 3.
    ours_name, theirs_name : str
        What to call them (during a rebase, stage 2 is the upstream and stage 3 is your commit).
    """

    kind: str
    ours: str
    theirs: str
    ours_name: str
    theirs_name: str


def _verify(git: Git, ref: str) -> str:
    return git("rev-parse", "-q", "--verify", ref).strip()


def operation(git: Git = _git) -> Operation:
    """The operation in progress (from ``MERGE_HEAD``, ``REBASE_HEAD``, ``CHERRY_PICK_HEAD``, ``REVERT_HEAD``)."""
    head = _verify(git, "HEAD")
    branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    if merge := _verify(git, "MERGE_HEAD"):
        name = git("name-rev", "--name-only", "--no-undefined", merge).strip() or merge[:12]
        return Operation("merge", head, merge, f"{branch} (HEAD)", name)
    if rebase := _verify(git, "REBASE_HEAD"):
        subject = git("log", "-1", "--format=%s", rebase).strip()
        return Operation(
            "rebase", head, rebase, "upstream (the branch being rebased onto)", f"your commit {rebase[:8]} {subject}"
        )
    if pick := _verify(git, "CHERRY_PICK_HEAD"):
        subject = git("log", "-1", "--format=%s", pick).strip()
        return Operation("cherry-pick", head, pick, f"{branch} (HEAD)", f"picked commit {pick[:8]} {subject}")
    if revert := _verify(git, "REVERT_HEAD"):
        return Operation("revert", head, revert, f"{branch} (HEAD)", f"revert of {revert[:8]}")
    return Operation("unknown", head, "", f"{branch} (HEAD)", "theirs")


def conflicted_files(git: Git = _git) -> list[str]:
    """Paths (relative to the top of the repository) with unmerged index entries."""
    return [p for p in git("diff", "--no-color", "--name-only", "--diff-filter=U").splitlines() if p.strip()]


def intent(op: Operation, path: str, side: str, git: Git = _git) -> str:
    """The commit messages of *side* (``ours``/``theirs``) touching *path* since the merge base: its intent."""
    rev = op.ours if side == "ours" else op.theirs
    if not rev:
        return ""
    if op.kind in ("cherry-pick", "revert") and side == "theirs":
        return git("log", "--no-color", "-1", "--format=%s%n%b", rev).strip()
    base = git("merge-base", op.ours, op.theirs).strip() if op.theirs else ""
    span = [f"{base}..{rev}"] if base else ["-5", rev]
    return git("log", "--no-color", "--format=%s%n%b", *span, "--", f":(top){path}").strip()[:2000]


# ── hunks ──────────────────────────────────────────────────────────────────────


@dataclass
class Resolution:
    """How a hunk is resolved.

    Attributes
    ----------
    source : str
        ``pre-pass``, ``model`` or ``user``.
    strategy : str
        ``ours``, ``theirs``, ``both`` or ``custom``.
    lines : list of str
        The resolved text.
    rationale : str
    confidence : str
        ``high`` for the pre-pass rules, the model's otherwise (``low`` when it cited nothing).
    risks : list of str
    sources : list of Source
        Sources cited by the model.
    verified : bool or None
        Compiles (True), does not compile (False), not checked (None: not Fortran, unresolved hunks, modules
        not built).
    note : str
        Why it was not verified, or what to review.
    """

    source: str
    strategy: str
    lines: list[str]
    rationale: str = ""
    confidence: str = "high"
    risks: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    verified: bool | None = None
    note: str = ""


@dataclass
class Hunk:
    """A conflict block: the base, ours and theirs lines, and its resolution once known."""

    index: int
    ours: list[str]
    base: list[str]
    theirs: list[str]
    resolution: Resolution | None = None

    def side(self, strategy: str) -> list[str]:
        """The text of *strategy* ``ours``/``theirs``/``both`` (ours then theirs)."""
        return {"ours": self.ours, "theirs": self.theirs, "both": self.ours + self.theirs}[strategy]


@dataclass
class ConflictFile:
    """A conflicted file as text segments and hunks, in order."""

    path: str
    segments: list[list[str] | Hunk] = field(default_factory=list)

    @property
    def hunks(self) -> list[Hunk]:
        return [s for s in self.segments if isinstance(s, Hunk)]

    def render(self, accept: set[int] | None = None) -> tuple[str, dict[int, tuple[int, int]]]:
        """The file text with the resolutions of the *accept* hunks (every resolved hunk when None); the other
        hunks keep diff3 conflict markers. Also each hunk's (first, last) line in that text."""
        out: list[str] = []
        spans: dict[int, tuple[int, int]] = {}
        for segment in self.segments:
            if not isinstance(segment, Hunk):
                out += segment
                continue
            hunk = segment
            first = len(out) + 1
            if hunk.resolution is not None and (accept is None or hunk.index in accept):
                out += hunk.resolution.lines
            else:
                out += ["<<<<<<< ours", *hunk.ours, "||||||| base", *hunk.base, "=======", *hunk.theirs]
                out.append(">>>>>>> theirs")
            spans[hunk.index] = (first, len(out))
        return "".join(line + "\n" for line in out), spans

    def context(self, hunk: Hunk, lines: int = 6) -> tuple[list[str], list[str]]:
        """Up to *lines* lines of text before and after *hunk*."""
        pos = self.segments.index(hunk)
        prev = self.segments[pos - 1] if pos > 0 else []
        nxt = self.segments[pos + 1] if pos + 1 < len(self.segments) else []
        before = prev if not isinstance(prev, Hunk) else []
        after = nxt if not isinstance(nxt, Hunk) else []
        return list(before[-lines:]), list(after[:lines])

    def text_before(self, hunk: Hunk) -> list[str]:
        """The text before *hunk* (earlier hunks as ours) to find its section or procedure."""
        out: list[str] = []
        for segment in self.segments:
            if segment is hunk:
                break
            out += segment.ours if isinstance(segment, Hunk) else segment
        return out


def _span(cf: ConflictFile, first: int, last: int, side: str) -> list[str]:
    """The *side* (``ours``/``theirs``) text of the segments from hunk *first* to hunk *last*."""
    out: list[str] = []
    inside = False
    for segment in cf.segments:
        if isinstance(segment, Hunk):
            if segment.index == first:
                inside = True
            if inside:
                out += segment.ours if side == "ours" else segment.theirs
            if segment.index == last:
                break
        elif inside:
            out += segment
    return out


def _span_resolved(cf: ConflictFile, first: int, last: int, accept: set[int]) -> list[str]:
    """The segments from hunk *first* to hunk *last*: accepted hunks resolved, the others in diff3 conflict."""
    out: list[str] = []
    inside = False
    for segment in cf.segments:
        if isinstance(segment, Hunk):
            if segment.index == first:
                inside = True
            if inside:
                if segment.index in accept and segment.resolution is not None:
                    out += segment.resolution.lines
                else:
                    out += ["<<<<<<< ours", *segment.ours, "||||||| base", *segment.base, "=======", *segment.theirs]
                    out.append(">>>>>>> theirs")
            if segment.index == last:
                break
        elif inside:
            out += segment
    return out


def apply_to_worktree(text: str, cf: ConflictFile, accept: set[int]) -> tuple[str, set[int]]:
    """Replace, in the working-tree *text*, the conflict blocks of the *accept* hunks with their resolutions.

    A block is matched to the run of consecutive hunks whose ours and theirs texts it holds (git may coalesce
    neighbouring conflicts into one block; any ``merge.conflictStyle``); the run is replaced by its accepted
    resolutions and the lines between them, a hunk of the run not accepted staying in conflict. Every other line,
    including the user's own resolutions of other conflicts, is kept. Returns the text and the hunks applied.
    """
    count = len(cf.hunks)
    runs = {
        (tuple(_span(cf, a, b, "ours")), tuple(_span(cf, a, b, "theirs"))): (a, b)
        for a in range(count)
        for b in range(a, count)
    }
    out: list[str] = []
    applied: set[int] = set()
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        if not lines[i].startswith("<<<<<<<"):
            out.append(lines[i])
            i += 1
            continue
        start, ours, theirs, part, j = i, [], [], "ours", i + 1
        while j < len(lines):
            line = lines[j]
            if line.startswith("|||||||") and part == "ours":
                part = "base"
            elif line.startswith("=======") and part in ("ours", "base"):
                part = "theirs"
            elif line.startswith(">>>>>>>") and part == "theirs":
                break
            elif part == "ours":
                ours.append(line)
            elif part == "theirs":
                theirs.append(line)
            j += 1
        run = runs.get((tuple(ours), tuple(theirs)))
        chosen = {k for k in range(run[0], run[1] + 1) if k in accept} if run else set()
        if j >= len(lines) or not chosen:
            out += lines[start : j + 1]
        else:
            out += _span_resolved(cf, run[0], run[1], chosen)
            applied |= chosen
        i = j + 1
    return "\n".join(out), applied


def parse_merged(path: str, text: str) -> ConflictFile:
    """Split the output of ``git merge-file -p --diff3 -L ours -L base -L theirs`` into segments and hunks."""
    cf = ConflictFile(path)
    plain: list[str] = []
    state = None
    ours: list[str] = []
    base: list[str] = []
    theirs: list[str] = []
    for line in text.splitlines():
        marker = _MARKERS.match(line) is not None
        if marker and line.startswith("<<<<<<<") and state is None:
            if plain:
                cf.segments.append(plain)
                plain = []
            state, ours, base, theirs = "ours", [], [], []
        elif marker and line.startswith("|||||||") and state == "ours":
            state = "base"
        elif marker and line.startswith("=======") and state in ("ours", "base"):
            state = "theirs"
        elif marker and line.startswith(">>>>>>>") and state == "theirs":
            cf.segments.append(Hunk(len(cf.hunks), ours, base, theirs))
            state = None
        elif state == "ours":
            ours.append(line)
        elif state == "base":
            base.append(line)
        elif state == "theirs":
            theirs.append(line)
        else:
            plain.append(line)
    if plain:
        cf.segments.append(plain)
    return cf


def load_conflict(path: str, git: Git = _git) -> ConflictFile:
    """The conflict of *path*, from its index stages (a missing stage is empty: add/add, modify/delete)."""
    stages = [git("show", f":{n}:{path}") for n in (2, 1, 3)]
    with tempfile.TemporaryDirectory() as tmp:
        names = []
        for label, text in zip(("ours", "base", "theirs"), stages, strict=True):
            name = os.path.join(tmp, label)
            with open(name, "w", encoding="utf-8") as handle:
                handle.write(text)
            names.append(name)
        merged = subprocess.run(
            ["git", "merge-file", "-p", "--diff3", "-L", "ours", "-L", "base", "-L", "theirs", *names],
            capture_output=True,
            text=True,
        ).stdout
    return parse_merged(path, merged)


# ── deterministic pre-pass ─────────────────────────────────────────────────────


def _squash(lines: list[str]) -> str:
    return "".join("".join(lines).split())


def _uses(lines: list[str]) -> list[re.Match] | None:
    """The ``use`` statements of *lines* (blank lines ignored), None when any other line is there."""
    found = []
    for line in lines:
        if not line.strip():
            continue
        if line.rstrip().endswith("&"):
            return None
        match = _USE.match(line)
        if match is None:
            return None
        found.append(match)
    return found


def _names(text: str | None) -> list[str]:
    return [n.strip() for n in (text or "").split(",") if n.strip()]


def merge_uses(base: list[str], ours: list[str], theirs: list[str]) -> list[str] | None:
    """Three-way union of ``use`` statements: modules and ``only`` names added by either side are kept, those a
    side removed stay removed. None when the lines are not all ``use`` statements."""
    parsed = [_uses(lines) for lines in (base, ours, theirs)]
    if parsed[0] is None or not parsed[1] or not parsed[2]:
        return None
    base_u, ours_u, theirs_u = ({m.group("module").lower(): m for m in p} for p in parsed)
    out = []
    for module in dict.fromkeys([*ours_u, *theirs_u]):
        if module in base_u and (module not in ours_u or module not in theirs_u):
            continue  # a side removed the module
        pick = [m for m in (ours_u.get(module), theirs_u.get(module)) if m is not None]
        first = pick[0]
        only: list[str] | None = None
        if all(m.group("only") is not None for m in pick):
            base_names = {n.lower() for n in _names(base_u[module].group("only"))} if module in base_u else set()
            sides = [_names(m.group("only")) for m in pick]
            kept = [{n.lower() for n in names} for names in sides]
            removed = {n for n in base_names if any(n not in k for k in kept)}
            only, seen = [], set()
            for name in (n for names in sides for n in names):
                if name.lower() not in removed and name.lower() not in seen:
                    seen.add(name.lower())
                    only.append(name)
        nature = f", {first.group('nature')} ::" if first.group("nature") else ""
        line = f"{first.group('indent')}use{nature} {first.group('module')}"
        if only is not None:
            line += f", only: {', '.join(only)}"
        out.append(line)
    return out


def _pins(lines: list[str]) -> dict[str, str] | None:
    pins = {}
    for line in lines:
        if not line.strip() or line.strip().startswith(("#", ";")):
            continue
        match = _PIN.match(line)
        if match is None:
            return None
        pins[match.group("name")] = match.group("spec")
    return pins


def merge_pins(base: list[str], ours: list[str], theirs: list[str]) -> tuple[list[str], str] | None:
    """Both sides moved fobos ``[dependencies]`` ``tag=`` pins: the higher version of each, written as ours."""
    from ..SemVer import Version

    pins = [_pins(lines) for lines in (base, ours, theirs)]
    if any(p is None for p in pins) or set(pins[1]) != set(pins[2]):
        return None
    base_p, ours_p, theirs_p = pins
    chosen: dict[str, str] = {}
    moved = []
    for name, ours_spec in ours_p.items():
        theirs_spec = theirs_p[name]
        if ours_spec == theirs_spec or theirs_spec == base_p.get(name):
            chosen[name] = ours_spec
        elif ours_spec == base_p.get(name):
            chosen[name] = theirs_spec
        else:
            tags = [_TAG.search(s) for s in (ours_spec, theirs_spec)]
            if not all(tags) or _TAG.sub("", ours_spec) != _TAG.sub("", theirs_spec):
                return None  # not two tags of the same dependency
            try:
                versions = [Version(t.group("tag")) for t in tags]
            except ValueError:
                return None
            higher = 0 if versions[0] >= versions[1] else 1
            chosen[name] = (ours_spec, theirs_spec)[higher]
            moved.append(f"{name}: {tags[0].group('tag')} vs {tags[1].group('tag')} -> {tags[higher].group('tag')}")
    lines = []
    for line in ours:
        match = _PIN.match(line) if line.strip() else None
        lines.append(line.replace(match.group("spec"), chosen[match.group("name")]) if match else line)
    return lines, "; ".join(moved)


def merge_adjacent(base: list[str], ours: list[str], theirs: list[str]) -> tuple[list[str], str] | None:
    """One side only appended (or prepended) lines to the base, the other only edited the base lines: both
    changes, the edited lines with the added ones. Git leaves such adjacent edits in conflict."""
    if not base:
        return None
    for adder, editor, name in ((ours, theirs, "ours"), (theirs, ours, "theirs")):
        if len(adder) > len(base) and adder[: len(base)] == base and editor != base:
            return [*editor, *adder[len(base) :]], f"{name} appended lines after the base, the other side edited it"
        if len(adder) > len(base) and adder[-len(base) :] == base and editor != base:
            return [*adder[: -len(base)], *editor], f"{name} prepended lines before the base, the other side edited it"
    return None


def _section(cf: ConflictFile, hunk: Hunk) -> str | None:
    for line in reversed(cf.text_before(hunk)):
        if match := _SECTION.match(line):
            return match.group("name").strip().lower()
    return None


def pre_pass(cf: ConflictFile, hunk: Hunk) -> Resolution | None:
    """The deterministic resolution of *hunk*, when one of the rules applies."""
    if hunk.ours == hunk.base:
        return Resolution("pre-pass", "theirs", list(hunk.theirs), "only theirs changed these lines")
    if hunk.theirs == hunk.base:
        return Resolution("pre-pass", "ours", list(hunk.ours), "only ours changed these lines")
    if hunk.ours == hunk.theirs:
        return Resolution("pre-pass", "ours", list(hunk.ours), "both sides made the same change")
    if _squash(hunk.ours) == _squash(hunk.theirs):
        return Resolution("pre-pass", "ours", list(hunk.ours), "the sides differ only in whitespace: ours kept")
    if cf.path.lower().endswith(FORTRAN_EXTENSIONS):
        merged = merge_uses(hunk.base, hunk.ours, hunk.theirs)
        if merged is not None:
            return Resolution("pre-pass", "custom", merged, "use statements: three-way union of modules and names")
    adjacent = merge_adjacent(hunk.base, hunk.ours, hunk.theirs)
    if adjacent is not None:
        lines, how = adjacent
        return Resolution(
            "pre-pass",
            "custom",
            lines,
            f"adjacent edits combined: {how}",
            confidence="medium",
            note="both changes kept: check that they are consistent (e.g. clauses one side added to a directive)",
        )
    if os.path.basename(cf.path).startswith("fobos") and _section(cf, hunk) == "dependencies":
        pins = merge_pins(hunk.base, hunk.ours, hunk.theirs)
        if pins is not None:
            lines, moved = pins
            note = f"both sides moved a pin ({moved}): review" if moved else ""
            return Resolution("pre-pass", "custom", lines, "dependency pins: the higher version of each", note=note)
    return None


# ── model ──────────────────────────────────────────────────────────────────────


def merge_schema(labels: list[str]) -> dict:
    """JSON Schema of a proposal; citations are an enum of the bundle's labels."""
    citation = {"type": "string", "enum": labels} if labels else {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "strategy": {"type": "string", "enum": STRATEGIES},
            "merged_text": {"type": "string"},
            "rationale": {"type": "string"},
            "confidence": {"type": "string", "enum": CONFIDENCE},
            "risks": {"type": "array", "items": {"type": "string"}},
            "citations": {"type": "array", "items": citation},
        },
        "required": ["strategy", "merged_text", "rationale", "confidence", "risks", "citations"],
        "additionalProperties": False,
    }


def procedures_touched(cf: ConflictFile, hunk: Hunk) -> list[str]:
    """Procedures whose headers are in the hunk, else the procedure enclosing it (nearest header before it)."""
    names = [m.group("name").lower() for line in hunk.ours + hunk.theirs if (m := _PROC_HEADER.match(line))]
    if not names:
        for line in reversed(cf.text_before(hunk)):
            if _PROC_END.match(line):
                break
            if m := _PROC_HEADER.match(line):
                names.append(m.group("name").lower())
                break
    return list(dict.fromkeys(names))


def _text(lines: list[str]) -> str:
    return "\n".join(lines) if lines else "(no lines)"


def build_bundle(
    cf: ConflictFile, hunk: Hunk, op: Operation, git: Git = _git, errors: str = "", draft: Resolution | None = None
) -> ContextBundle:
    """What the model gets to resolve *hunk*: the operation, the three versions, the context, each side's intent,
    and the pre-pass *draft* when a rule combined the sides but the result needs a judgement."""
    note = (
        " During a rebase, ours (stage 2) is the upstream and theirs (stage 3) is the commit being replayed."
        if op.kind == "rebase"
        else ""
    )
    sections = [
        ("Operation", f"{op.kind}: ours = {op.ours_name}; theirs = {op.theirs_name}.{note}"),
        ("File", f"{cf.path}, conflict {hunk.index + 1} of {len(cf.hunks)}"),
    ]
    if errors:
        sections.append(("Compiler errors of the previous proposal", errors))
    before, after = cf.context(hunk)
    tag = f"{cf.path}#{hunk.index + 1}"
    sources = [
        Source(f"base:{tag}", "base (the common ancestor)", _text(hunk.base)),
        Source(f"ours:{tag}", f"ours: {op.ours_name}", _text(hunk.ours)),
        Source(f"theirs:{tag}", f"theirs: {op.theirs_name}", _text(hunk.theirs)),
        Source(f"context:{tag}", "the lines around the conflict", "\n".join([*before, "<<< conflict >>>", *after])),
    ]
    for side, name in (("ours", op.ours_name), ("theirs", op.theirs_name)):
        text = intent(op, cf.path, side, git)
        if text:
            sources.append(Source(f"intent:{side}", f"commit messages of {side} ({name})", text))
    procedures = procedures_touched(cf, hunk)
    if procedures:
        sources.append(Source(f"fact:{cf.path}#procedures", "procedures at the conflict", ", ".join(procedures)))
    if draft is not None:
        title = f"deterministic draft ({draft.rationale}): it keeps both changes but may need to make them consistent"
        sources.append(Source(f"draft:{tag}", title, _text(draft.lines)))
    return ContextBundle(sections=sections, sources=sources)


def check_proposal(raw: str, hunk: Hunk, bundle: ContextBundle) -> Resolution | None:
    """The model's proposal, checked: FoBiS builds ours/theirs/both itself; a custom text must have no conflict
    markers; a proposal citing nothing is kept at confidence low. None when unusable."""
    data = _parse(raw)
    if not data:
        return None
    strategy = str(data.get("strategy", "")).strip().lower()
    if strategy not in STRATEGIES:
        return None
    if strategy == "custom":
        text = str(data.get("merged_text", ""))
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        if not text.strip() or any(_MARKERS.match(line) for line in lines):
            return None
    else:
        lines = list(hunk.side(strategy))
    by_label = dict(zip(bundle.labels, bundle.sources, strict=True))
    labels = [str(c).strip().strip("[]").upper() for c in data.get("citations") or []]
    sources = list(dict.fromkeys(by_label[c] for c in labels if c in by_label))
    confidence = str(data.get("confidence", "low")).strip().lower()
    confidence = confidence if confidence in CONFIDENCE else "low"
    note = ""
    if not sources:
        confidence, note = "low", "the proposal cites no source"
    risks = [str(r).strip() for r in data.get("risks") or [] if str(r).strip()]
    return Resolution(
        "model", strategy, lines, str(data.get("rationale", "")).strip(), confidence, risks, sources, note=note
    )


def propose(
    cf: ConflictFile,
    hunk: Hunk,
    op: Operation,
    provider: Provider,
    git: Git = _git,
    errors: str = "",
    draft: Resolution | None = None,
) -> Resolution | None:
    """Ask *provider* for a resolution of *hunk* (refining *draft* when given); the checked proposal or None."""
    bundle = build_bundle(cf, hunk, op, git, errors, draft)
    completion = provider.chat(
        messages(bundle.render(), system=load_prompt("merge")),
        schema=merge_schema(bundle.labels),
        temperature=0.0,
        seed=0,
    )
    return check_proposal(completion.text, hunk, bundle)


# ── verification ───────────────────────────────────────────────────────────────


def syntax_command(
    compiler: str, fc: str | None, path: str, scratch: str, includes: list[str], defines: list[str]
) -> list[str]:
    """The syntax-only compile command for the mode's *compiler* family (module files written in *scratch*)."""
    family = {"intel_nextgen": "intel", "pgi": "nvfortran", "opencoarrays-gnu": "gnu"}.get(compiler, compiler)
    inc = [f"-I{d}" for d in includes]
    if family == "intel":
        return [fc or "ifx", "-syntax-only", "-module", scratch, *inc, *defines, path]
    if family == "nvfortran":
        return [fc or "nvfortran", "-c", "-o", os.path.join(scratch, "x.o"), "-module", scratch, *inc, *defines, path]
    if family == "lfortran":
        return [fc or "lfortran", "-c", "-o", os.path.join(scratch, "x.o"), "-J", scratch, *inc, *defines, path]
    return [fc or "gfortran", "-fsyntax-only", f"-J{scratch}", *inc, *defines, path]


@dataclass
class Check:
    """The outcome of compiling a resolved file: errors per hunk, errors elsewhere, or why it was not checked."""

    ok: bool | None
    by_hunk: dict[int, list[Diagnostic]] = field(default_factory=dict)
    elsewhere: list[Diagnostic] = field(default_factory=list)
    reason: str = ""


def verify(
    cf: ConflictFile,
    compiler: str = "gnu",
    fc: str | None = None,
    includes: list[str] | None = None,
    defines: list[str] | None = None,
    run=subprocess.run,
) -> Check:
    """Compile the file with every resolution applied, syntax only, in a scratch directory."""
    if not cf.path.lower().endswith(FORTRAN_EXTENSIONS):
        return Check(None, reason="not a Fortran source")
    unresolved = [h for h in cf.hunks if h.resolution is None]
    if len(unresolved) == len(cf.hunks):
        return Check(None, reason="no conflict is resolved")
    for hunk in unresolved:  # placeholder: ours, so the resolved hunks can be checked
        hunk.resolution = Resolution("placeholder", "ours", list(hunk.ours))
    try:
        text, spans = cf.render()
    finally:
        for hunk in unresolved:
            hunk.resolution = None
    with tempfile.TemporaryDirectory() as scratch:
        path = os.path.join(scratch, os.path.basename(cf.path))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        command = syntax_command(compiler, fc, path, scratch, includes or [], defines or [])
        try:
            done = run(command, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return Check(None, reason=f"the compiler could not run: {exc}")
    errors = [d for d in parse_diagnostics(done.stdout + done.stderr) if d.is_error]
    missing = sorted({name for d in errors if (name := missing_module_name(d))})
    if missing:
        return Check(None, reason=f"module(s) {', '.join(missing)} not built: build the project once to verify")
    placeholders = {h.index for h in unresolved}
    if done.returncode == 0 and not errors:
        return Check(True)
    check = Check(False, reason=(done.stdout + done.stderr).strip()[-400:])
    for diagnostic in errors:
        hit = next((i for i, (a, b) in spans.items() if diagnostic.line and a <= diagnostic.line <= b), None)
        if hit in placeholders:
            continue  # an unresolved hunk compiled as ours: not a fault of the proposals
        if hit is None:
            check.elsewhere.append(diagnostic)
        else:
            check.by_hunk.setdefault(hit, []).append(diagnostic)
    return check


def resolve_file(
    cf: ConflictFile,
    op: Operation,
    provider: Provider | None,
    git: Git = _git,
    compiler: str = "gnu",
    fc: str | None = None,
    includes: list[str] | None = None,
    defines: list[str] | None = None,
    run=subprocess.run,
    on_status=None,
) -> Check:
    """Resolve every hunk of *cf* (pre-pass, then the model), verify, and retry the failing model hunks."""
    for hunk in cf.hunks:
        hunk.resolution = pre_pass(cf, hunk)
        draft = hunk.resolution if hunk.resolution is not None and hunk.resolution.confidence != "high" else None
        if (hunk.resolution is None or draft is not None) and provider is not None:
            if on_status:
                on_status(f"[llm] {cf.path}: conflict {hunk.index + 1}/{len(cf.hunks)}")
            hunk.resolution = propose(cf, hunk, op, provider, git, draft=draft) or draft
    check = verify(cf, compiler, fc, includes, defines, run)
    retries = 0
    while check.ok is False and provider is not None and retries < MAX_RETRIES:
        failing = [h for h in cf.hunks if h.index in check.by_hunk and h.resolution and h.resolution.source == "model"]
        if not failing:
            break
        retries += 1
        for hunk in failing:
            errors = "\n".join(d.text or d.message for d in check.by_hunk[hunk.index])
            if on_status:
                on_status(f"[llm] {cf.path}: conflict {hunk.index + 1} does not compile, retry {retries}/{MAX_RETRIES}")
            hunk.resolution = propose(cf, hunk, op, provider, git, errors) or hunk.resolution
        check = verify(cf, compiler, fc, includes, defines, run)
    for hunk in cf.hunks:
        res = hunk.resolution
        if res is None:
            continue
        if check.ok is True:
            res.verified = True
        elif check.ok is False and hunk.index in check.by_hunk:
            res.verified = False
            res.note = f"does not compile: {check.by_hunk[hunk.index][0].message}"
        elif check.ok is None:
            res.note = res.note or f"not compiled: {check.reason}"
    return check


# ── report ─────────────────────────────────────────────────────────────────────


def _block(title: str, lines: list[str]) -> list[str]:
    return [f"  {title}:", *(f"    | {line}" for line in lines or ["(no lines)"])]


def render_hunk(cf: ConflictFile, hunk: Hunk, op: Operation) -> str:
    """One conflict: the three versions, the proposal and its status."""
    out = [f"{cf.path}: conflict {hunk.index + 1} of {len(cf.hunks)}"]
    out += _block("base", hunk.base)
    out += _block(f"ours ({op.ours_name})", hunk.ours)
    out += _block(f"theirs ({op.theirs_name})", hunk.theirs)
    res = hunk.resolution
    if res is None:
        out.append("  no proposal: resolve it by hand")
        return "\n".join(out)
    status = {True: "compiles", False: "does NOT compile", None: "not compiled"}[res.verified]
    out.append(f"  proposal [{res.source}, {res.strategy}, confidence {res.confidence}, {status}]: {res.rationale}")
    out += _block("proposed", res.lines)
    out += [f"  risk: {risk}" for risk in res.risks]
    if res.note:
        out.append(f"  note: {res.note}")
    if res.sources:
        out.append("  cites: " + ", ".join(s.id for s in res.sources))
    return "\n".join(out)


def both_sides_touched(files: list[ConflictFile]) -> list[str]:
    """Procedures at conflicts (changed by both sides): what to test after the merge."""
    names = []
    for cf in files:
        for hunk in cf.hunks:
            names += [f"{cf.path}: {p}" for p in procedures_touched(cf, hunk)]
    return list(dict.fromkeys(names))


# ── replay on historical merges ────────────────────────────────────────────────


@dataclass
class ReplayStats:
    """How the pre-pass did on historical merges: hunks seen; resolved by a high-confidence rule and agreeing with
    the committed resolution; medium-confidence drafts (for the model) and how many already equal it."""

    merges: int = 0
    conflicted: int = 0
    hunks: int = 0
    resolved: int = 0
    agree: int = 0
    drafts: int = 0
    drafts_exact: int = 0
    disagree: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "merges": self.merges,
            "conflicted_merges": self.conflicted,
            "hunks": self.hunks,
            "resolved_high_confidence": self.resolved,
            "agree_with_human": self.agree,
            "drafts_for_the_model": self.drafts,
            "drafts_equal_to_human": self.drafts_exact,
            "disagree": self.disagree,
        }


def replay(repo: str, limit: int = 50) -> ReplayStats:
    """Replay the last *limit* two-parent merges of *repo* (a clone): redo each merge in a temporary worktree,
    run the pre-pass on its conflicts, and compare with the committed resolution. It adds and removes a worktree
    in *repo*: use a clone, never a working tree you care about."""

    def git_in(cwd: str) -> Git:
        def run_git(*args: str) -> str:
            return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).stdout

        return run_git

    git = git_in(repo)
    identity = {
        "GIT_AUTHOR_NAME": "r",
        "GIT_AUTHOR_EMAIL": "r@r",
        "GIT_COMMITTER_NAME": "r",
        "GIT_COMMITTER_EMAIL": "r@r",
    }
    env = {**os.environ, **identity}
    stats = ReplayStats()
    with tempfile.TemporaryDirectory() as tmp:
        work = os.path.join(tmp, "replay")
        local = git_in(work)
        for merge in [m for m in git("rev-list", "--merges", f"-n{limit}", "HEAD").split() if m]:
            parents = git("rev-list", "--parents", "-n1", merge).split()[1:]
            if len(parents) != 2:
                continue
            stats.merges += 1
            subprocess.run(
                ["git", "worktree", "add", "-q", "--detach", work, parents[0]], cwd=repo, capture_output=True
            )
            try:
                subprocess.run(
                    ["git", "merge", "--no-commit", "--no-ff", parents[1]], cwd=work, capture_output=True, env=env
                )
                paths = conflicted_files(local)
                stats.conflicted += bool(paths)
                for path in paths:
                    cf = load_conflict_in(work, path)
                    final = git("show", f"{merge}:{path}")
                    for hunk in cf.hunks:
                        stats.hunks += 1
                        res = pre_pass(cf, hunk)
                        if res is None:
                            continue
                        exact = "\n".join(res.lines) in final
                        if res.confidence != "high":  # a draft: the model refines it, it is not final
                            stats.drafts += 1
                            stats.drafts_exact += exact
                            continue
                        stats.resolved += 1
                        if exact:
                            stats.agree += 1
                        else:
                            stats.disagree.append(f"{merge[:8]} {path} #{hunk.index + 1}: {res.rationale}")
            finally:
                subprocess.run(["git", "merge", "--abort"], cwd=work, capture_output=True)
                subprocess.run(["git", "worktree", "remove", "--force", work], cwd=repo, capture_output=True)
    return stats


def load_conflict_in(cwd: str, path: str) -> ConflictFile:
    """`load_conflict` for a repository other than the current directory."""

    def run_git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).stdout

    return load_conflict(path, run_git)
