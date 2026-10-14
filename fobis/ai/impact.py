"""impact.py — ``fobis ecosystem impact``: which dependent projects a change of public interface breaks.

Deterministic. For the changed project, the **public API** of every module in a changed Fortran source is
computed on both sides (the base, by default the latest release tag, and the working tree): public procedures
with their signature (prefixes, dummy arguments and their declarations, result), generic interfaces and their
specific procedures, derived types and their components, variables and named constants (their value: a kind
constant that changes is an API change). The difference is the **API change**: removed (or made private),
changed, added.

Then every project of the ecosystem that depends on the changed one, directly or not, is scanned: each ``use`` of
a changed module, the changed names it imports (``only`` lists and renames resolved), and the lines that
reference them. That is what the release train must fix before releasing the dependents.

``--deep`` adds an LLM summary for the release train, cited on these facts (`fobis.ai.grounding`).
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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..analysis import FileUnits, Unit, read_source
from ..lint.engine import analyse
from ..llm.provider import messages
from .change import FORTRAN_EXTENSIONS, WORKTREE, Git, Revision, staged_changes
from .grounding import ANSWER_TOKENS, ContextBundle, Grounded, Source, check_claims, claims_schema, load_prompt

if TYPE_CHECKING:
    from ..analysis.lexer import Statement
    from ..llm.provider import Provider

KINDS = ["breaking", "action"]
GROUPS = {"breaking": "What breaks", "action": "What to do"}

_TYPE_DEF = re.compile(r"^type\s*(?:,\s*(?P<attrs>[^:]*?))?\s*(?:::)?\s*(?P<name>\w+)\s*(?:\(.*\))?$")
_END_TYPE = re.compile(r"^end\s*type\b")
_ONLY = re.compile(r"\bonly\s*:(?P<names>.*)$", re.IGNORECASE)
_ACCESS = ("public", "private")


def git_in(path: str) -> Git:
    """A git runner bound to the repository at *path* ('' on failure)."""

    def run(*args: str) -> str:
        done = subprocess.run(["git", *args], cwd=path, capture_output=True, text=True)
        return done.stdout if done.returncode == 0 else ""

    return run


# ── public API ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Entity:
    """A public entity of a module: name, kind and a normalised signature (what dependents rely on)."""

    name: str
    kind: str  # procedure, generic, type, variable, parameter
    signature: str
    line: int = 0


def _decl_text(unit: Unit, name: str) -> str:
    decl = unit.decls.get(name)
    if decl is None:
        return f"{name} (implicit)"
    attrs = ", ".join(k if not v else f"{k}({v})" for k, v in sorted(decl.attrs.items()) if k not in _ACCESS)
    dims = f"({decl.dims})" if decl.dims else ""
    return " ".join(f"{decl.type_spec}{', ' + attrs if attrs else ''} :: {name}{dims}".split())


def _procedure_signature(unit: Unit) -> str:
    prefixes = " ".join(sorted(p for p in unit.prefixes if p != "module"))
    lines = [f"{prefixes} {unit.kind} {unit.name}({', '.join(unit.args)})".strip()]
    lines += [_decl_text(unit, arg) for arg in unit.args]
    if unit.kind == "function":
        lines.append("result: " + _decl_text(unit, unit.result or unit.name))
    return "\n".join(lines)


def _types(module: Unit) -> dict[str, tuple[str, set[str], int]]:
    """Derived types defined in *module*: name -> (definition and components, attributes, line)."""
    found: dict[str, tuple[str, set[str], int]] = {}
    current: str | None = None
    body: list[str] = []
    attrs: set[str] = set()
    line = 0
    for stmt in module.statements:
        masked = " ".join(stmt.masked.split())
        if current is None:
            match = _TYPE_DEF.match(masked)
            if match and not masked.startswith(("type(", "type (", "type is")):
                current, body, line = match.group("name"), [masked], stmt.line
                attrs = {a.strip() for a in (match.group("attrs") or "").split(",") if a.strip()}
            continue
        body.append(masked)
        if _END_TYPE.match(masked):
            found[current] = ("\n".join(body), attrs, line)
            current = None
    return found


def _is_public(module: Unit, name: str, extra: set[str] = frozenset()) -> bool:
    decl = module.decls.get(name)
    attrs = (set(decl.attrs) if decl is not None else set()) | set(extra)
    if name in module.access:
        attrs.add(module.access[name])
    if "public" in attrs:
        return True
    if "private" in attrs:
        return False
    return module.default_access != "private"


def module_api(units: FileUnits) -> dict[str, dict[str, Entity]]:
    """Module name -> its public entities, for every module of *units*."""
    api: dict[str, dict[str, Entity]] = {}
    for module in units.units:
        if module.kind != "module" or not module.name:
            continue
        entities: dict[str, Entity] = {}
        named = set()
        for child in module.children:
            if child.is_procedure and child.name:
                named.add(child.name)
                if _is_public(module, child.name):
                    entities[child.name] = Entity(child.name, "procedure", _procedure_signature(child), child.line)
            elif child.kind == "interface" and child.name and not child.abstract:
                named.add(child.name)
                if _is_public(module, child.name):
                    words = {w for s in child.statements for w in re.findall(r"\w+", s.masked)}
                    specifics = sorted((words - {"module", "procedure"}) | {b.name for b in child.children if b.name})
                    entities[child.name] = Entity(child.name, "generic", "generic: " + ", ".join(specifics), child.line)
        for name, (body, attrs, line) in _types(module).items():
            named.add(name)
            if _is_public(module, name, attrs):
                entities[name] = Entity(name, "type", body, line)
        for name, decl in module.decls.items():
            if name in named or not decl.type_spec or not _is_public(module, name):
                continue
            kind = "parameter" if "parameter" in decl.attrs else "variable"
            signature = _decl_text(module, name) + (f" = {decl.init}" if kind == "parameter" and decl.init else "")
            entities[name] = Entity(name, kind, signature, decl.line)
        api[module.name] = entities
    return api


# ── API change ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ApiChange:
    """One change of a module's public API."""

    module: str
    name: str
    kind: str  # entity kind, or "module"
    change: str  # removed, changed, added
    before: str = ""
    after: str = ""
    path: str = ""
    line: int = 0
    via: str = ""  # re-export: the module::name this change comes from

    @property
    def breaking(self) -> bool:
        return self.change in ("removed", "changed")


def api_changes(
    old: dict[str, dict[str, Entity]], new: dict[str, dict[str, Entity]], path: str = ""
) -> list[ApiChange]:
    """The public API changes from *old* to *new* (both as returned by `module_api`)."""
    changes: list[ApiChange] = []
    for module in sorted(set(old) | set(new)):
        before, after = old.get(module), new.get(module)
        if after is None:
            changes.append(ApiChange(module, module, "module", "removed", path=path))
            continue
        for name in sorted(set(before or {}) | set(after)):
            b, a = (before or {}).get(name), after.get(name)
            if a is None:
                changes.append(ApiChange(module, name, b.kind, "removed", b.signature, "", path, b.line))
            elif b is None:
                if before is not None:  # a new module is not an API change of the old ones
                    changes.append(ApiChange(module, name, a.kind, "added", "", a.signature, path, a.line))
            elif b.signature != a.signature or b.kind != a.kind:
                changes.append(ApiChange(module, name, a.kind, "changed", b.signature, a.signature, path, a.line))
    return changes


def reexports(changes: list[ApiChange], modules: dict[str, tuple[str, Unit]]) -> list[ApiChange]:
    """The *changes* re-exported by other modules of the project (*modules*: name -> (path, unit)), transitively.

    A module re-exports a changed name it imports (``use C`` or ``use C, only: name``, renames resolved) and makes
    public (its default access, or an access statement): ``penf`` re-exports ``penf_global_parameters_variables``
    this way, and dependents only ``use penf``.
    """
    known = {(c.module, c.name) for c in changes}
    found: list[ApiChange] = []
    frontier = [c for c in changes if c.kind != "module"]
    while frontier:
        by_module: dict[str, list[ApiChange]] = {}
        for change in frontier:
            by_module.setdefault(change.module, []).append(change)
        frontier = []
        for name, (path, unit) in modules.items():
            for use in unit.uses:
                changed = by_module.get(use.module.lower())
                if not changed:
                    continue
                imports = _imports(use.statement.text)
                for change in changed:
                    locals_ = [change.name] if imports is None else [k for k, v in imports.items() if v == change.name]
                    for local in locals_:
                        if (name, local) in known or not _is_public(unit, local):
                            continue
                        known.add((name, local))
                        via = change.via or f"{change.module}::{change.name}"
                        new = ApiChange(
                            name, local, change.kind, change.change, change.before, change.after, path, use.line, via
                        )
                        found.append(new)
                        frontier.append(new)
    return found


def latest_tag(git: Git) -> str:
    """The latest release tag reachable from HEAD ('' when there is none)."""
    return git("describe", "--tags", "--abbrev=0").strip()


def project_changes(path: str, base: str | None = None) -> tuple[str, list[ApiChange]]:
    """The public API changes of the project at *path* from *base* (default: its latest tag, else HEAD) to its
    working tree; the base used and the changes."""
    git = git_in(path)
    base = base or latest_tag(git) or "HEAD"
    revision = Revision((base,), base, WORKTREE, path)
    changes: list[ApiChange] = []
    for status, new_path, old_path in staged_changes(git, revision):
        if not new_path.lower().endswith(FORTRAN_EXTENSIONS):
            continue
        old_text = revision.show("old", old_path, git) if status != "A" else ""
        new_text = revision.show("new", new_path, git) if status != "D" else ""
        old_api = module_api(analyse(old_text, old_path)) if old_text else {}
        new_api = module_api(analyse(new_text, new_path)) if new_text else {}
        changes += api_changes(old_api, new_api, new_path)
    if changes:
        modules = {}
        for source in fortran_sources(path):
            try:
                units = analyse(read_source(source), source)
            except (OSError, UnicodeDecodeError):
                continue
            for unit in units.units:
                if unit.kind == "module" and unit.name:
                    modules[unit.name] = (os.path.relpath(source, path), unit)
        changes += reexports(changes, modules)
    return base, changes


# ── usages in dependents ───────────────────────────────────────────────────────


@dataclass
class Usage:
    """Where a dependent uses a changed module, and the changed names it references there."""

    project: str
    path: str
    line: int
    module: str
    statement: str
    names: list[str] = field(default_factory=list)
    references: list[tuple[int, str, str]] = field(default_factory=list)  # (line, changed name, statement)


def _imports(statement: str) -> dict[str, str] | None:
    """Local name -> module entity of a ``use ..., only:`` list (renames resolved); None without ``only``."""
    match = _ONLY.search(statement)
    if not match:
        return None
    imported = {}
    for item in match.group("names").split(","):
        item = item.strip().lower()
        if not item:
            continue
        local, _, remote = item.partition("=>")
        imported[local.strip()] = (remote or local).strip()
    return imported


def _scope_statements(unit: Unit) -> list[Statement]:
    out = list(unit.statements)
    for child in unit.children:
        out += _scope_statements(child)
    return out


def usages_in(project: str, root: str, changes: list[ApiChange], files: list[str], max_refs: int = 20) -> list[Usage]:
    """The usages of the breaking *changes* in the sources *files* of the dependent *project* (under *root*).

    A ``use`` counts when the code references a changed name, when its ``only`` list imports a removed name (the
    ``use`` line itself no longer compiles), or when the whole module was removed. A plain ``use`` of a module
    whose changed names are never referenced is not affected.
    """
    breaking: dict[str, set[str]] = {}
    removed: set[tuple[str, str]] = set()
    removed_modules = set()
    for change in changes:
        if change.breaking and change.kind == "module":
            removed_modules.add(change.module)
        elif change.breaking:
            breaking.setdefault(change.module, set()).add(change.name)
            if change.change == "removed":
                removed.add((change.module, change.name))
    modules = set(breaking) | removed_modules
    found: list[Usage] = []
    for path in files:
        try:
            units = analyse(read_source(path), path)
        except (OSError, UnicodeDecodeError):
            continue
        for unit in units.walk():
            for use in unit.uses:
                module = use.module.lower()
                if module not in modules:
                    continue
                imports = _imports(use.statement.text)
                changed = breaking.get(module, set())
                local = (
                    {n: n for n in changed} if imports is None else {k: v for k, v in imports.items() if v in changed}
                )
                statement = " ".join(use.statement.text.split())
                usage = Usage(
                    project, os.path.relpath(path, root), use.line, module, statement, sorted(set(local.values()))
                )
                if module in removed_modules:
                    usage.names = ["(the whole module)"]
                for stmt in _scope_statements(unit):
                    if stmt is use.statement or len(usage.references) >= max_refs:
                        continue
                    for loc, remote in local.items():
                        if re.search(rf"(?<![\w%]){re.escape(loc)}\b", stmt.masked):
                            usage.references.append((stmt.line, remote, " ".join(stmt.text.split())[:160]))
                            break
                referenced = {remote for _, remote, _ in usage.references}
                # an only-list importing a removed name breaks the use line itself; otherwise only references count
                imported_removed = (
                    {v for v in local.values() if (module, v) in removed} if imports is not None else set()
                )
                if module not in removed_modules:
                    usage.names = sorted(referenced | imported_removed)
                if usage.names:
                    found.append(usage)
    return found


def fortran_sources(path: str) -> list[str]:
    """The Fortran sources of a project's own repository: tracked and untracked files not ignored, so neither
    fetched dependencies nor the contents of git submodules (vendored copies of other projects) are counted as its
    code. Outside a git repository, every source under *path* (fetched dependencies excluded)."""
    from ..cli._constants import __extensions_parsed__

    done = subprocess.run(
        ["git", "-C", path, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
    )
    extensions = tuple(__extensions_parsed__)
    if done.returncode == 0:
        files = sorted({f for f in done.stdout.split("\0") if f.endswith(extensions)})
        return [os.path.join(path, f) for f in files if os.path.isfile(os.path.join(path, f))]
    from ..lint import discover_files

    return discover_files([path], extensions=__extensions_parsed__)


# ── report ─────────────────────────────────────────────────────────────────────


@dataclass
class Impact:
    """The impact of a project's change on its dependents."""

    project: str
    base: str
    changes: list[ApiChange]
    dependents: list[str]
    usages: list[Usage]

    @property
    def breaking(self) -> list[ApiChange]:
        return [c for c in self.changes if c.breaking]

    def affected(self) -> dict[str, list[Usage]]:
        out: dict[str, list[Usage]] = {}
        for usage in self.usages:
            out.setdefault(usage.project, []).append(usage)
        return out

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "base": self.base,
            "changes": [{**c.__dict__, "breaking": c.breaking} for c in self.changes],
            "dependents": self.dependents,
            "usages": [
                {
                    "project": u.project,
                    "path": u.path,
                    "line": u.line,
                    "module": u.module,
                    "use": u.statement,
                    "names": u.names,
                    "references": [{"line": n, "name": name, "statement": s} for n, name, s in u.references],
                }
                for u in self.usages
            ],
        }


def _change_line(c: ApiChange) -> str:
    mark = "BREAKING" if c.breaking else ""  # the change column says "added" already
    where = f" ({c.path}:{c.line})" if c.line else (f" ({c.path})" if c.path else "")
    if c.kind == "module":
        return f"  {mark:8} module {c.module} removed{where}"
    via = f" (re-exports {c.via})" if c.via else ""
    return f"  {mark:8} {c.change:7} {c.kind} {c.module}::{c.name}{via}{where}"


def render_text(impact: Impact) -> str:
    """The impact as text: the API changes, then each dependent with its usages."""
    lines = [f"{impact.project}: public API changes since {impact.base}"]
    if not impact.changes:
        lines.append("  none (no public interface of a Fortran module changed)")
    for c in impact.changes:
        lines.append(_change_line(c))
        if c.change == "changed" and not c.via:
            lines += [f"           - {line}" for line in c.before.splitlines()]
            lines += [f"           + {line}" for line in c.after.splitlines()]
    lines.append("")
    if not impact.dependents:
        lines.append("No ecosystem project depends on it.")
        return "\n".join(lines)
    affected = impact.affected()
    for name in impact.dependents:
        uses = affected.get(name, [])
        if not uses:
            lines.append(f"{name}: not affected (no use of a changed name)")
            continue
        lines.append(f"{name}: affected")
        for u in uses:
            lines.append(f"  {u.path}:{u.line}: {u.statement}  [changed: {', '.join(u.names) or '-'}]")
            lines += [f"    {u.path}:{n}: {name_}: {s}" for n, name_, s in u.references]
    lines += [
        "",
        f"{len(impact.breaking)} breaking change(s); {len(affected)} of {len(impact.dependents)} dependent "
        "project(s) affected.",
    ]
    return "\n".join(lines)


def render_markdown(impact: Impact) -> str:
    """The impact as markdown, for a release note or an issue."""
    lines = [f"### Impact of `{impact.project}` changes since `{impact.base}`", ""]
    if impact.changes:
        lines += ["| Change | Entity | Where |", "|---|---|---|"]
        for c in impact.changes:
            mark = "**breaking**: " if c.breaking else ""
            lines.append(f"| {mark}{c.change} | {c.kind} `{c.module}::{c.name}` | `{c.path}:{c.line}` |")
    else:
        lines.append("No public interface changed.")
    affected = impact.affected()
    lines += ["", "#### Dependents", ""]
    for name in impact.dependents:
        uses = affected.get(name, [])
        places = sum(len(u.references) or 1 for u in uses)
        lines.append(f"- **{name}**: " + (f"{places} place(s) to update" if uses else "not affected"))
        lines += [f"  - `{u.path}:{u.line}` `{u.statement}`" for u in uses]
    return "\n".join(lines)


def impact_bundle(impact: Impact) -> ContextBundle:
    """What the model gets to summarise the impact for the release train."""
    dependents = ", ".join(impact.dependents) or "none"
    sections = [("Change", f"{impact.project}: public API changes since {impact.base}; dependents: {dependents}")]
    sources = []
    for c in impact.changes:
        text = f"{c.change} {c.kind} {c.module}::{c.name}"
        text += f"\nbefore:\n{c.before}" if c.before else ""
        text += f"\nafter:\n{c.after}" if c.after else ""
        sources.append(
            Source(f"api:{impact.project}:{c.module}::{c.name}", f"API change of {c.module}::{c.name}", text)
        )
    for u in impact.usages:
        refs = "\n".join(f"line {n}: {s}" for n, _, s in u.references) or "(imported, no reference found)"
        sources.append(
            Source(
                f"use:{u.project}:{u.path}:{u.line}",
                f"{u.project} {u.path}:{u.line} uses {u.module}",
                f"{u.statement}\n{refs}",
            )
        )
    return ContextBundle(sections=sections, sources=sources)


def impact_summary(bundle: ContextBundle, provider: Provider, seed: int = 0) -> Grounded:
    """Ask *provider* for the cited summary: what breaks where, and what to do in the release train."""
    completion = provider.chat(
        messages(bundle.render(), system=load_prompt("impact")),
        schema=claims_schema(bundle.labels, kinds=KINDS),
        temperature=0.0,
        seed=seed,
        max_tokens=ANSWER_TOKENS,
    )
    return check_claims(completion.text, bundle)
