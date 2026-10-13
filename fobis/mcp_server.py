"""mcp_server.py — FoBiS as a Model Context Protocol server (``fobis mcp``).

Exposes FoBiS to any MCP client (Claude Code, other agents) over stdio (newline-delimited JSON-RPC 2.0): the
linter and the rule documentation, the knowledge packs, the build facts and dependency checks, builds and tests
with their diagnosed failures, change review, merge conflicts, commit facts, test skeletons and the ecosystem.

What is exposed are FoBiS's **facts and grounded context**, never the answers of FoBiS's own local LLM: the client
is a model already. ``ask`` returns the retrieved sections (``ask_context``), not an answer; ``build`` and ``test``
return the deterministic diagnoses of ``--explain``, not the model's explanation.

Commands that read a fobos file or run builds are executed as ``fobis`` subprocesses in the server's working
directory with their JSON output (``--json`` / ``--format json``): nothing they print can corrupt the protocol
stream on stdout, and the JSON is returned both as text and, from protocol 2025-06-18, as ``structuredContent``.
Every tool carries annotations (read-only, destructive, idempotent, open world). Rules and pack sections are also
resources (``fobis://rules/{id}``, ``fobis://kb/{id}``).
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

import json
import os
import subprocess
import sys
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import IO, Any

from . import __version__

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
STRUCTURED_SINCE = "2025-06-18"
MAX_OUTPUT = 60_000
MAX_FINDINGS = 200
_PARSE_ERROR, _INVALID_REQUEST, _METHOD_NOT_FOUND, _INVALID_PARAMS = -32700, -32600, -32601, -32602
_RESOURCE_NOT_FOUND = -32002
RULE_URI, KB_URI = "fobis://rules/", "fobis://kb/"

Runner = Callable[[list[str]], tuple[int, str, str]]


def fobis_command() -> list[str]:
    """Command line running this FoBiS: ``python -m fobis``, or ``python fobis.pyz`` from the zipapp."""
    package = os.path.dirname(os.path.abspath(__file__))
    if os.path.isdir(package):
        return [sys.executable, "-m", "fobis"]
    archive = package
    while archive and not os.path.isfile(archive):
        archive = os.path.dirname(archive)
    return [sys.executable, archive]


class ToolError(Exception):
    """A tool failed; the message is returned to the client as an error result."""


@dataclass
class Reply:
    """What a tool returns: text for the client, the JSON object when there is one."""

    text: str
    data: dict | None = None


@dataclass(frozen=True)
class Tool:
    """An MCP tool: name, description, JSON Schema of its arguments, implementation and behaviour hints."""

    name: str
    title: str
    description: str
    schema: dict
    handler: Callable[[dict], Reply]
    read_only: bool = True
    destructive: bool = False
    idempotent: bool = True
    open_world: bool = False

    def listing(self) -> dict:
        annotations = {
            "title": self.title,
            "readOnlyHint": self.read_only,
            "destructiveHint": self.destructive,
            "idempotentHint": self.idempotent,
            "openWorldHint": self.open_world,
        }
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.schema,
            "annotations": annotations,
        }


def _schema(properties: dict | None = None, required: tuple[str, ...] = ()) -> dict:
    schema: dict[str, Any] = {"type": "object", "properties": properties or {}}
    if required:
        schema["required"] = list(required)
    return schema


_STR = {"type": "string"}
_BOOL = {"type": "boolean"}
_INT = {"type": "integer"}
_STR_LIST = {"type": "array", "items": {"type": "string"}}
_MODE = {"type": "string", "description": "fobos mode (default: the fobos default mode)"}
_SHADOW = {
    "type": "string",
    "enum": ["checks", "sanitize", "strict", "none"],
    "description": "rebuild the mode as this shadow in its own build directory: checks (runtime checks, FP traps, "
    "-O0 -g), sanitize (AddressSanitizer), strict (standard conformance, warnings as errors)",
}
_MAX = {"type": "integer", "description": f"at most this many findings (default {MAX_FINDINGS})"}
_CONFIG = {"type": "string", "description": "user config holding the ecosystem registry (default: the user's)"}


def _parse_json(text: str) -> dict | None:
    """The JSON object a command printed (progress lines before it are skipped), or None."""
    start = text.find("{")
    if start < 0:
        return None
    try:
        data = json.loads(text[start:])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


@dataclass
class Server:
    """The FoBiS MCP server.

    Parameters
    ----------
    root : str
        Working directory of the subprocess commands (the project root).
    run : callable or None
        ``run(args) -> (exit code, stdout, stderr)`` executing ``fobis <args>``; replaceable in tests.
    """

    root: str = "."
    run: Runner | None = None
    protocol: str = PROTOCOL_VERSIONS[0]
    tools: dict[str, Tool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.root = os.path.abspath(self.root)
        self.run = self.run or self._run
        self.tools = {tool.name: tool for tool in self._tools()}

    # ── running fobis ─────────────────────────────────────────────────────────

    def _run(self, args: list[str]) -> tuple[int, str, str]:
        proc = subprocess.run([*fobis_command(), *args], cwd=self.root, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def _json(self, args: list[str], trim: tuple[str, int] | None = None) -> Reply:
        """Run ``fobis <args>`` whose stdout is one JSON object: the object, whatever the exit status (a failed build
        is a result: its ``status`` says so). No JSON and a non-zero exit status is an error."""
        code, out, err = self.run(args)
        data = _parse_json(out)
        if data is None:
            if code != 0:
                raise ToolError(f"fobis {' '.join(args)} failed (exit {code}):\n{(out + err).strip()[-4000:]}")
            return Reply(out.strip()[:MAX_OUTPUT])
        if trim is not None:
            key, limit = trim
            items = data.get(key)
            if isinstance(items, list) and len(items) > limit:
                data[key] = items[:limit]
                data["truncated"] = {key: len(items), "returned": limit}
        return Reply(json.dumps(data, indent=1), data)

    @staticmethod
    def _mode(arguments: dict) -> list[str]:
        """``--mode`` (and ``--shadow`` for the tools that take one) from the arguments."""
        args = ["--mode", arguments["mode"]] if arguments.get("mode") else []
        return args + (["--shadow", arguments["shadow"]] if arguments.get("shadow") else [])

    @staticmethod
    def _repeat(option: str, values: list[str] | None) -> list[str]:
        return [item for value in values or [] for item in (option, value)]

    @staticmethod
    def _limit(arguments: dict) -> int:
        return int(arguments.get("max_findings") or MAX_FINDINGS)

    # ── code quality ──────────────────────────────────────────────────────────

    def _lint(self, arguments: dict) -> Reply:
        args = ["lint", *arguments.get("paths", []), *self._mode(arguments)]
        args += self._repeat("--select", arguments.get("select")) + self._repeat("--ignore", arguments.get("ignore"))
        if arguments.get("compiler_feedback"):
            args += ["--compiler-feedback", arguments["compiler_feedback"]]
        if arguments.get("fix_diff"):
            _, out, _ = self.run([*args, "--diff"])
            return Reply(out.strip()[:MAX_OUTPUT] or "no automatic fix applies")
        return self._json([*args, "--format", "json", "--exit-zero"], trim=("findings", self._limit(arguments)))

    def _review(self, arguments: dict) -> Reply:
        args = ["review", *arguments.get("paths", []), *self._mode(arguments), "--format", "json", "--exit-zero"]
        if arguments.get("staged"):
            args.append("--staged")
        if arguments.get("base"):
            args += ["--base", arguments["base"]]
        if arguments.get("context"):
            args += ["--context", str(int(arguments["context"]))]
        args += self._repeat("--select", arguments.get("select"))
        return self._json(args, trim=("findings", self._limit(arguments)))

    @staticmethod
    def _list_rules(arguments: dict) -> Reply:
        from .lint import RULES

        prefix = str(arguments.get("prefix") or "").upper()
        rules = [
            {"id": r.id, "name": r.name, "severity": r.severity, "default": r.default, "summary": r.summary}
            for r in sorted(RULES.values(), key=lambda r: r.id)
            if r.id.startswith(prefix)
        ]
        return Reply(json.dumps({"rules": rules}, indent=1), {"rules": rules})

    @staticmethod
    def _explain_rule(arguments: dict) -> Reply:
        from .lint import RULES

        rid = str(arguments.get("id", "")).upper()
        if rid not in RULES:
            raise ToolError(f"unknown rule '{arguments.get('id')}' (use list_rules)")
        return Reply(RULES[rid].explain())

    # ── knowledge ─────────────────────────────────────────────────────────────

    def _kb(self):
        from .kb import KnowledgeBase

        return KnowledgeBase.load(root=self.root)

    def _kb_search(self, arguments: dict) -> Reply:
        from .kb import PackError

        query = arguments.get("query", "")
        if not query:
            raise ToolError("query is required")
        try:
            results = self._kb().search(query, k=int(arguments.get("k", 5)), packs=arguments.get("packs") or None)
        except PackError as exc:
            raise ToolError(str(exc)) from exc
        found = [
            {
                "id": r.chunk.id,
                "uri": KB_URI + urllib.parse.quote(r.chunk.id, safe=""),
                "heading": r.chunk.heading,
                "score": round(r.score, 2),
                "text": r.chunk.text,
            }
            for r in results
        ]
        return Reply(json.dumps({"results": found}, indent=1), {"results": found})

    def _kb_section(self, chunk_id: str, context: int = 0) -> str:
        kb = self._kb()
        if chunk_id not in kb.by_id:
            raise ToolError(f"no section '{chunk_id}' (use kb_search)")
        sections = kb.neighbours(chunk_id, before=context, after=context)
        pack = kb.packs[kb.get(chunk_id).pack]
        credit = f"\n\n-- {pack.name}: {pack.license}, {pack.meta.get('attribution', '')}" if pack.license else ""
        return "\n\n".join(f"## {c.heading} [{c.id}]\n\n{c.text}" for c in sections) + credit

    def _kb_show(self, arguments: dict) -> Reply:
        return Reply(self._kb_section(arguments.get("id", ""), int(arguments.get("context", 0))))

    def _ask_context(self, arguments: dict) -> Reply:
        question = str(arguments.get("question", "")).strip()
        if not question:
            raise ToolError("question is required")
        args = ["ask", question, "--show-context", "--json", "-k", str(int(arguments.get("k", 6)))]
        args += self._repeat("--project", arguments.get("project")) + self._repeat("--pack", arguments.get("packs"))
        return self._json(args)

    # ── the project ───────────────────────────────────────────────────────────

    def _introspect(self, arguments: dict) -> Reply:
        sections = arguments.get("sections") or ["all"]
        return self._json(["introspect", *self._mode(arguments), *(f"--{s}" for s in sections)])

    def _merge_conflicts(self, arguments: dict) -> Reply:
        paths = arguments.get("paths", [])
        return self._json(["merge-assist", *paths, *self._mode(arguments), "--no-model", "--format", "json"])

    def _testgen_skeleton(self, arguments: dict) -> Reply:
        module = str(arguments.get("module", "")).strip()
        if not module:
            raise ToolError("module is required")
        args = ["testgen", module, "--skeleton", "--format", "json", *self._mode(arguments)]
        args += self._repeat("--procedure", arguments.get("procedures"))
        if arguments.get("max"):
            args += ["--max", str(int(arguments["max"]))]
        return self._json(args)

    def _ecosystem(self, arguments: dict, args: list[str]) -> Reply:
        if arguments.get("config"):
            args += ["--config", arguments["config"]]
        return self._json(args)

    def _tree(self, arguments: dict) -> Reply:
        depth = ["--depth", str(int(arguments["depth"]))] if arguments.get("depth") else []
        return self._json(["tree", "--json", *depth])

    def _build(self, arguments: dict) -> Reply:
        args = ["build", "--json", *self._mode(arguments)]
        if arguments.get("target"):
            args += ["--target", arguments["target"]]
        return self._json(args)

    def _test(self, arguments: dict) -> Reply:
        args = ["test", "--json", *self._mode(arguments)]
        for key in ("suite", "filter"):
            if arguments.get(key):
                args += [f"--{key}", arguments[key]]
        if arguments.get("list"):
            args.append("--list")
        return self._json(args)

    def _assess(self, arguments: dict) -> Reply:
        case = str(arguments.get("case", "")).strip()
        if not case:
            raise ToolError("case is required")
        args = ["assess", case, "--json", *self._mode(arguments)]
        if arguments.get("families"):
            args += ["--families", ",".join(arguments["families"])]
        for key in ("samples", "jobs"):
            if arguments.get(key):
                args += [f"--{key}", str(int(arguments[key]))]
        return self._json(args)

    def _diff_run(self, arguments: dict) -> Reply:
        args = [
            "diff-run",
            arguments.get("ref") or "HEAD",
            *arguments.get("names", []),
            "--json",
            *self._mode(arguments),
        ]
        return self._json(args + (["--assess"] if arguments.get("assess") else []))

    def _bench(self, arguments: dict) -> Reply:
        args = ["bench", *arguments.get("names", []), "--json", *self._mode(arguments)]
        if arguments.get("compare"):
            args += ["--compare", arguments["compare"]] + (["--feedback"] if arguments.get("feedback") else [])
        if arguments.get("runs"):
            args += ["--runs", str(int(arguments["runs"]))]
        return self._json(args)

    def _matrix(self, arguments: dict) -> Reply:
        args = ["matrix", "--json"]
        for key in ("modes", "shadows", "compilers"):
            if arguments.get(key):
                args += [f"--{key}", ",".join(arguments[key])]
        args += [f"--{key}" for key in ("verify", "recheck") if arguments.get(key)]
        return self._json(args)

    # ── the catalogue ─────────────────────────────────────────────────────────

    def _tools(self) -> list[Tool]:
        return [
            Tool(
                "lint",
                "Lint Fortran sources",
                "Run the FoBiS Fortran linter (bug-prone, obsolescent, non-portable constructs; OpenMP/OpenACC/MPI "
                "defects) on the project and return the findings as JSON (rule, severity, path, line, message). "
                "With fix_diff, return the automatic fixes as a unified diff instead (nothing is written).",
                _schema(
                    {
                        "paths": {**_STR_LIST, "description": "files or directories (default: the mode's sources)"},
                        "select": {**_STR_LIST, "description": "rule ids or prefixes, e.g. OMP, ACC006, ALL"},
                        "ignore": _STR_LIST,
                        "mode": _MODE,
                        "compiler_feedback": {
                            **_STR,
                            "description": "build log with nvfortran -Minfo / gfortran -fopt-info reports",
                        },
                        "fix_diff": {**_BOOL, "description": "return the automatic fixes as a diff"},
                        "max_findings": _MAX,
                    }
                ),
                self._lint,
            ),
            Tool(
                "review",
                "Review a change",
                "Lint findings on the changed lines only: uncommitted changes (default), the staged change, or the "
                "commits since the merge base with a reference (base, e.g. origin/master). A changed OpenMP/OpenACC "
                "directive counts its whole region. JSON like lint, plus the reviewed revision.",
                _schema(
                    {
                        "paths": _STR_LIST,
                        "staged": {**_BOOL, "description": "review the staged change"},
                        "base": {**_STR, "description": "review the commits since the merge base with this ref"},
                        "context": {**_INT, "description": "also report findings this many lines from a change"},
                        "select": _STR_LIST,
                        "mode": _MODE,
                        "max_findings": _MAX,
                    }
                ),
                self._review,
            ),
            Tool(
                "list_rules",
                "List lint rules",
                "List the lint rules: id, name, severity, enabled by default, summary (optionally by id prefix).",
                _schema({"prefix": {**_STR, "description": "e.g. OMP, ACC, MPI, COR"}}),
                self._list_rules,
            ),
            Tool(
                "explain_rule",
                "Explain a lint rule",
                "Explain a lint rule: why it matters, reported and preferred code, knowledge-pack references.",
                _schema({"id": {**_STR, "description": "rule id, e.g. OMP001"}}, ("id",)),
                self._explain_rule,
            ),
            Tool(
                "kb_search",
                "Search the knowledge packs",
                "Search the knowledge packs (distilled Fortran 2023, OpenMP 6.0, OpenACC 3.4, MPI 5.0 references and "
                "HPC practice) by words, exact names (firstprivate, mpi_isend) or constraint ids (C1004).",
                _schema(
                    {
                        "query": _STR,
                        "k": {**_INT, "description": "number of results (default 5)"},
                        "packs": {**_STR_LIST, "description": "restrict to these packs"},
                    },
                    ("query",),
                ),
                self._kb_search,
            ),
            Tool(
                "kb_show",
                "Show a knowledge-pack section",
                "Return a knowledge-pack section by id (as returned by kb_search), optionally with neighbours.",
                _schema({"id": _STR, "context": {**_INT, "description": "neighbouring sections"}}, ("id",)),
                self._kb_show,
            ),
            Tool(
                "ask_context",
                "Retrieve grounding for a question",
                "The knowledge-pack sections (and, with project, the facts of the project's procedures: arguments, "
                "uses, calls, MPI calls, directives, location) most relevant to a question, labelled S1..Sn for "
                "citation. No answer is generated: reason on the sources yourself.",
                _schema(
                    {
                        "question": _STR,
                        "project": {**_STR_LIST, "description": "source directories whose procedures to search"},
                        "packs": _STR_LIST,
                        "k": {**_INT, "description": "number of sections (default 6)"},
                    },
                    ("question",),
                ),
                self._ask_context,
            ),
            Tool(
                "query",
                "Query the code graph",
                "Deterministic answers from the static analysis of the mode's sources (more precise than text search): "
                "callers/callees of a procedure (calls, function references, type-bound calls; generics and bindings "
                "give candidates; unresolved external calls listed), uses of a module, writers/readers of a variable "
                "(assignment, read, allocate, intent(out/inout) actuals; NAME or module::NAME, renames followed), "
                "defines NAME, region FILE:LINE (OpenMP/OpenACC regions and clauses), device VAR (declare, enter/exit "
                "data, data regions, update, present, implicit use in compute constructs), mpi [ROUTINE|KIND], "
                "interface NAME (header and dummy declarations, generic specifics, bindings).",
                _schema(
                    {
                        "kind": {
                            "type": "string",
                            "enum": [
                                "callers",
                                "callees",
                                "uses",
                                "writers",
                                "readers",
                                "defines",
                                "region",
                                "device",
                                "mpi",
                                "interface",
                            ],
                        },
                        "argument": {**_STR, "description": "NAME, module::NAME, MODULE, FILE:LINE, or ROUTINE|KIND"},
                        "mode": _MODE,
                    },
                    required=("kind",),
                ),
                lambda a: self._json(
                    [
                        "query",
                        a.get("kind", ""),
                        *([a["argument"]] if a.get("argument") else []),
                        "--json",
                        *self._mode(a),
                    ]
                ),
            ),
            Tool(
                "agents_md",
                "Project briefing for agents",
                "The project's facts that AGENTS.md is generated from (fobis agents-md): modes (compiler, what each "
                "builds, optimisation/debug/checks, parallel models, defines), environment setup, commands, test "
                "programs, declared cases with tolerances/references/assessment budgets, kinds in use, units without "
                "implicit none, OpenMP/OpenACC/MPI usage, dependencies; and the rendered Markdown block. Writes nothing.",
                _schema({"mode": {**_MODE, "description": "mode whose sources are analysed (default: the first)"}}),
                lambda a: self._json(["agents-md", "--print", "--json", *self._mode(a)]),
            ),
            Tool(
                "introspect",
                "Project build facts",
                "Return the project's build facts as JSON: sources, compiler, dependencies, targets, include dirs, "
                "build options, project info, varsets (sections: all or a subset).",
                _schema(
                    {
                        "mode": _MODE,
                        "sections": {
                            **_STR_LIST,
                            "description": "sources compiler dependencies targets include-dirs buildoptions "
                            "projectinfo varsets all",
                        },
                    }
                ),
                self._introspect,
            ),
            Tool(
                "check",
                "Check the dependency graph",
                "Validate the module dependency graph without compiling: files scanned, unresolved modules and "
                "includes, warnings.",
                _schema({"mode": _MODE}),
                lambda a: self._json(["check", "--json", *self._mode(a)]),
            ),
            Tool(
                "tree",
                "Dependency tree",
                "The project's inter-project dependency tree (fobos [dependencies], recursively): name, spec, version, "
                "whether fetched.",
                _schema({"depth": {**_INT, "description": "maximum depth"}}),
                self._tree,
            ),
            Tool(
                "merge_conflicts",
                "Analyse merge conflicts",
                "During a merge, rebase or cherry-pick that stopped on conflicts: for each conflict the base, ours and "
                "theirs versions (named as they really are: during a rebase ours is the upstream), the resolution "
                "of FoBiS's deterministic rules when one applies (use-list union, identical edits, dependency pins), "
                "and whether the resolved file compiles. Nothing is written or staged.",
                _schema({"paths": {**_STR_LIST, "description": "conflicted files (default: all)"}, "mode": _MODE}),
                self._merge_conflicts,
            ),
            Tool(
                "commit_facts",
                "Facts of the staged change",
                "Facts of the staged change for writing its commit message: scope candidates from the repository "
                "history, type hints (directive-only -> perf, comment-only -> docs), changed Fortran lines by kind, "
                "changed procedures and interfaces.",
                _schema(),
                lambda a: self._json(["commit", "--show-facts", "--json"]),
            ),
            Tool(
                "testgen_skeleton",
                "Test skeleton for a module",
                "A test program for a module's public procedures (generics and type-bound procedures included) that "
                "compiles: one subroutine per procedure declaring the arguments and calling it, built in a scratch "
                "copy of the project (the project is not written). Complete it with inputs and checks.",
                _schema(
                    {
                        "module": _STR,
                        "procedures": {**_STR_LIST, "description": "only these public names (or type%binding)"},
                        "max": {**_INT, "description": "at most this many procedures"},
                        "mode": _MODE,
                    },
                    ("module",),
                ),
                self._testgen_skeleton,
            ),
            Tool(
                "ecosystem_status",
                "Ecosystem status",
                "The state of every project of the user's FoBiS ecosystem: git, latest release and pending bump, CI, "
                "scaffold drift, dependency pins (runs git fetch and queries GitHub).",
                _schema({"config": _CONFIG}),
                lambda a: self._ecosystem(a, ["ecosystem", "dashboard", "--json"]),
                open_world=True,
            ),
            Tool(
                "ecosystem_impact",
                "Impact of an API change",
                "Which dependent projects of the ecosystem a change of a project's public Fortran interfaces breaks: "
                "the API changes since a base (default the latest tag) and every place a dependent uses a changed "
                "name.",
                _schema({"project": _STR, "base": _STR, "config": _CONFIG}, ("project",)),
                lambda a: self._ecosystem(
                    a,
                    ["ecosystem", "impact", a.get("project", ""), "--format", "json"]
                    + (["--base", a["base"]] if a.get("base") else []),
                ),
            ),
            Tool(
                "case_list",
                "List the declared cases",
                "The runnable cases declared in the fobos ([case:NAME]): program or command, mode, inputs, ranks, "
                "threads, timeout and the quantities each produces.",
                _schema(),
                lambda a: self._json(["case", "list", "--json"]),
            ),
            Tool(
                "provenance",
                "Provenance of a result",
                "What a result produced now depends on: commit and uncommitted change, dependency pins, compiler with "
                "version and flags of the mode, loaded modules, machine and GPUs.",
                _schema({"mode": _MODE}),
                lambda a: self._json(["provenance", "--json", *self._mode(a)]),
            ),
            Tool(
                "build",
                "Build the project",
                "Build the project with FoBiS (writes objects and targets in the mode's build directory). On failure "
                "the result holds the compiler's messages parsed (diagnostics) and FoBiS's diagnoses from facts "
                "(missing or unreachable module, object not linked, wrong compiler runtime, duplicate symbol).",
                _schema(
                    {
                        "mode": _MODE,
                        "shadow": _SHADOW,
                        "target": {**_STR, "description": "build only this program or library"},
                    }
                ),
                self._build,
                read_only=False,
            ),
            Tool(
                "test",
                "Run the tests",
                "Discover, build and run the project's Fortran test programs (or only list them). Each failure holds "
                "its facts: the parsed build errors and diagnoses, or the parsed crash (kind, message, location, "
                "frames) and FoBiS's notes on it (trusted location, debug mode to rebuild with, known compiler bugs).",
                _schema({"mode": _MODE, "shadow": _SHADOW, "suite": _STR, "filter": _STR, "list": _BOOL}),
                self._test,
                read_only=False,
            ),
            Tool(
                "case_run",
                "Run cases",
                "Build and run declared cases (all by default) in fresh run directories and return, per run, its "
                "status (ok, failed, timeout, build-failed with diagnoses, probe-error), its quantities, the tails of "
                "its output and its provenance.",
                _schema(
                    {
                        "names": {**_STR_LIST, "description": "cases to run (default: all)"},
                        "mode": _MODE,
                        "shadow": _SHADOW,
                    }
                ),
                lambda a: self._json(["case", "run", *a.get("names", []), "--json", *self._mode(a)]),
                read_only=False,
            ),
            Tool(
                "verify",
                "Verify results against references",
                "Run declared cases and compare their quantities with the stored references within each quantity's "
                "tolerance: per quantity pass/fail, max absolute and relative error, worst point, L2, NaN that "
                "appeared, and what changed in the provenance (compiler, flags, code). With repeat, runs each case "
                "N times and reports non-determinism. References are never written by this tool.",
                _schema(
                    {
                        "names": {**_STR_LIST, "description": "cases to verify (default: all)"},
                        "mode": _MODE,
                        "shadow": _SHADOW,
                        "repeat": {**_INT, "description": "runs per case (non-determinism check)"},
                    }
                ),
                lambda a: self._json(
                    ["verify", *a.get("names", []), "--json", *self._mode(a)]
                    + (["--repeat", str(int(a["repeat"]))] if a.get("repeat") else [])
                ),
                read_only=False,
            ),
            Tool(
                "matrix",
                "Build and test every mode x shadow",
                "Build, test and (with verify) run the cases of every fobos mode rebuilt as each shadow (none = the "
                "mode's own flags, checks, sanitize, strict), each in its own build directory and in the environment "
                "of its [verification] setup line. Per cell: status, compiler version, first build problem, failed "
                "tests with their crash facts, cases vs references; across cells, the quantities that disagree "
                "beyond tolerance. Missing compilers are skipped, shadows a compiler lacks are n/a. Slow: one full "
                "build per cell.",
                _schema(
                    {
                        "modes": {**_STR_LIST, "description": "modes (default: all)"},
                        "shadows": {**_STR_LIST, "description": "shadows (default: none, checks)"},
                        "compilers": {**_STR_LIST, "description": "keep modes of these compilers or families"},
                        "verify": {**_BOOL, "description": "run the declared cases too"},
                        "recheck": {**_BOOL, "description": "run failures again under the checks shadow"},
                    }
                ),
                self._matrix,
                read_only=False,
            ),
            Tool(
                "assess",
                "Assess numerical error and uncertainty",
                "Run ensembles of variants of a declared case and report what their spread says about each quantity: "
                "precision (digits agreeing with a promoted-precision build), rounding (significant digits across "
                "compiler-level perturbations: -O levels, FMA, fast math, vectorisation), compiler (other modes), "
                "parallel (thread/rank counts and repeated runs: non-determinism), inputs (elasticities or Monte "
                "Carlo correlations of perturbed inputs), refinement (observed order, Richardson extrapolation, "
                "error estimate, GCI). Budgets of the case's [assess:NAME] are checked. Slow: one build per variant.",
                _schema(
                    {
                        "case": {**_STR, "description": "the case to assess"},
                        "families": {**_STR_LIST, "description": "families (default: the case's, else rounding)"},
                        "mode": _MODE,
                        "samples": {**_INT, "description": "Monte Carlo samples (inputs)"},
                        "jobs": {**_INT, "description": "runs at a time"},
                    },
                    required=("case",),
                ),
                self._assess,
                read_only=False,
            ),
            Tool(
                "diff_run",
                "Compare results with a revision",
                "Build and run the declared cases on a git revision (default HEAD) and on the working tree, both in "
                "scratch copies (the project and its repository are not written), and compare every quantity with "
                "the case's tolerance: equivalent, or what differs, by how much and where, plus the files and "
                "procedures changed. With assess, a difference is judged against the working tree's own numerical "
                "spread. The oracle of a refactoring: equivalence shown by results.",
                _schema(
                    {
                        "ref": {**_STR, "description": "revision to compare with (default HEAD)"},
                        "names": {**_STR_LIST, "description": "cases (default: all)"},
                        "mode": _MODE,
                        "assess": {**_BOOL, "description": "judge differences against the numerical spread"},
                    }
                ),
                self._diff_run,
                read_only=False,
            ),
            Tool(
                "bench",
                "Measure run time",
                "Run the declared benchmark cases ([bench:NAME], else every case) repeatedly after warm-up, until the "
                "95% interval of the median time is within the target: median, interval, MAD, CPU/wall, throughput, "
                "notes on trustworthiness (busy machine, too-short runs, GPU timing). Compared with the case's "
                "recorded history, or with compare=REF against a revision measured interleaved in scratch copies: "
                "faster/slower only when the intervals do not overlap. feedback adds the compiler's report diff "
                "(loops that lost vectorisation, new implicit device copies, new sequential device loops). Never "
                "records history.",
                _schema(
                    {
                        "names": {**_STR_LIST, "description": "cases (default: the declared benchmarks)"},
                        "mode": _MODE,
                        "compare": {**_STR, "description": "revision to compare with"},
                        "feedback": {**_BOOL, "description": "with compare: diff the compiler reports"},
                        "runs": {**_INT, "description": "maximum runs per side"},
                    }
                ),
                self._bench,
                read_only=False,
            ),
            Tool(
                "clean",
                "Clean build products",
                "Remove the compiled objects and module files of the mode (returns the removed paths).",
                _schema({"mode": _MODE}),
                lambda a: self._json(["clean", "--json", *self._mode(a)]),
                read_only=False,
                destructive=True,
            ),
            Tool(
                "fetch",
                "Fetch dependencies",
                "Clone (or with update, update) the dependencies of fobos [dependencies] into the deps directory and "
                "build those used as libraries.",
                _schema({"update": {**_BOOL, "description": "fetch and check out again"}}),
                lambda a: self._json(["fetch", "--json", *(["--update"] if a.get("update") else [])]),
                read_only=False,
                idempotent=False,
                open_world=True,
            ),
        ]

    # ── resources ─────────────────────────────────────────────────────────────

    @staticmethod
    def _resources() -> list[dict]:
        from .lint import RULES

        return [
            {
                "uri": RULE_URI + rule.id,
                "name": rule.id,
                "title": f"{rule.id} {rule.name}",
                "description": rule.summary,
                "mimeType": "text/markdown",
            }
            for rule in sorted(RULES.values(), key=lambda r: r.id)
        ]

    def _read_resource(self, uri: str) -> str:
        from .lint import RULES

        if uri.startswith(RULE_URI):
            rid = uri[len(RULE_URI) :].upper()
            if rid in RULES:
                return RULES[rid].explain()
        if uri.startswith(KB_URI):
            return self._kb_section(urllib.parse.unquote(uri[len(KB_URI) :]))
        raise ToolError(f"unknown resource {uri}")

    # ── protocol ──────────────────────────────────────────────────────────────

    def _call(self, params: dict) -> dict:
        tool = self.tools[params["name"]]
        try:
            reply, is_error = tool.handler(params.get("arguments") or {}), False
        except ToolError as exc:
            reply, is_error = Reply(str(exc)), True
        result: dict[str, Any] = {"content": [{"type": "text", "text": reply.text}], "isError": is_error}
        if reply.data is not None and self.protocol >= STRUCTURED_SINCE:
            result["structuredContent"] = reply.data
        return result

    def handle(self, message: Any) -> dict | None:
        """The response to one JSON-RPC message (None for notifications)."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "method" not in message:
            msg_id = message.get("id") if isinstance(message, dict) else None
            return _error(msg_id, _INVALID_REQUEST, "invalid request")
        method, params, msg_id = message["method"], message.get("params") or {}, message.get("id")
        if msg_id is None:
            return None  # notification (notifications/initialized, cancellations): nothing to answer
        if method == "initialize":
            requested = params.get("protocolVersion")
            self.protocol = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            return _result(
                msg_id,
                {
                    "protocolVersion": self.protocol,
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": "fobis", "version": __version__},
                    "instructions": "FoBiS tools for a Fortran project: lint and change review, rule explanations, "
                    "knowledge packs (standards and HPC practice) and grounding for questions, build facts, "
                    "dependency check and tree, build and tests with their failures diagnosed from facts, merge "
                    "conflicts, commit facts, test skeletons, and the user's ecosystem of projects. Rules are "
                    "resources fobis://rules/{id}, pack sections fobis://kb/{id}.",
                },
            )
        if method == "ping":
            return _result(msg_id, {})
        if method == "tools/list":
            return _result(msg_id, {"tools": [tool.listing() for tool in self.tools.values()]})
        if method == "tools/call":
            if params.get("name") not in self.tools:
                return _error(msg_id, _INVALID_PARAMS, f"unknown tool '{params.get('name')}'")
            return _result(msg_id, self._call(params))
        if method == "resources/list":
            return _result(msg_id, {"resources": self._resources()})
        if method == "resources/templates/list":
            template = {
                "uriTemplate": KB_URI + "{id}",
                "name": "kb-section",
                "title": "Knowledge-pack section",
                "description": "A section of a knowledge pack by its id (URL-encoded), as returned by kb_search.",
                "mimeType": "text/markdown",
            }
            return _result(msg_id, {"resourceTemplates": [template]})
        if method == "resources/read":
            uri = str(params.get("uri", ""))
            try:
                text = self._read_resource(uri)
            except ToolError as exc:
                return _error(msg_id, _RESOURCE_NOT_FOUND, str(exc))
            return _result(msg_id, {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": text}]})
        return _error(msg_id, _METHOD_NOT_FOUND, f"method not found: {method}")

    def serve(self, stdin: IO[str], stdout: IO[str]) -> None:
        """Answer newline-delimited JSON-RPC messages from *stdin* on *stdout* until end of input."""
        for line in stdin:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                response = _error(None, _PARSE_ERROR, f"parse error: {exc}")
            else:
                response = self.handle(message)
            if response is not None:
                stdout.write(json.dumps(response) + "\n")
                stdout.flush()


def _result(msg_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
