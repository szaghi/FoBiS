"""mcp_server.py — FoBiS as a Model Context Protocol server (``fobis mcp``).

Exposes the linter, the rule documentation, the knowledge packs and the build commands as MCP tools over
stdio (newline-delimited JSON-RPC 2.0), so that any MCP client (Claude Code, other agents) can use them.
No language model is involved on the FoBiS side.

Commands that read a fobos file or run builds are executed as ``fobis`` subprocesses in the server's working
directory: their output is returned to the client, and nothing they print can corrupt the protocol stream on
stdout. Rules and knowledge packs are queried in process.
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
from collections.abc import Callable
from dataclasses import dataclass
from typing import IO, Any

from . import __version__

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_OUTPUT = 60_000
_PARSE_ERROR, _INVALID_REQUEST, _METHOD_NOT_FOUND, _INVALID_PARAMS = -32700, -32600, -32601, -32602


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


@dataclass(frozen=True)
class Tool:
    """An MCP tool: name, description, JSON Schema of its arguments, implementation."""

    name: str
    description: str
    schema: dict
    handler: Callable[[dict], str]

    def listing(self) -> dict:
        return {"name": self.name, "description": self.description, "inputSchema": self.schema}


def _schema(properties: dict | None = None, required: tuple[str, ...] = ()) -> dict:
    schema: dict[str, Any] = {"type": "object", "properties": properties or {}}
    if required:
        schema["required"] = list(required)
    return schema


_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": {"type": "string"}}
_MODE = {"type": "string", "description": "fobos mode (default: the fobos default mode)"}


class Server:
    """The FoBiS MCP server.

    Parameters
    ----------
    root : str
        Working directory of the subprocess commands (the project root).
    run : callable or None
        ``run(args) -> (exit code, output)`` executing ``fobis <args>``; replaceable in tests.
    """

    def __init__(self, root: str = ".", run: Callable[[list[str]], tuple[int, str]] | None = None) -> None:
        self.root = os.path.abspath(root)
        self.run = run or self._run
        self.tools = {tool.name: tool for tool in self._tools()}

    # ── tool implementations ──────────────────────────────────────────────────

    def _run(self, args: list[str]) -> tuple[int, str]:
        proc = subprocess.run([*fobis_command(), *args], cwd=self.root, capture_output=True, text=True)
        output = proc.stdout + (("\n" + proc.stderr) if proc.stderr.strip() else "")
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + f"\n[... output truncated at {MAX_OUTPUT} characters]"
        return proc.returncode, output

    @staticmethod
    def _mode(arguments: dict) -> list[str]:
        return ["--mode", arguments["mode"]] if arguments.get("mode") else []

    def _command(self, args: list[str]) -> str:
        code, output = self.run(args)
        return f"exit code: {code}\n{output}"

    def _lint(self, arguments: dict) -> str:
        args = ["lint", *arguments.get("paths", []), "--format", "json", "--exit-zero", *self._mode(arguments)]
        for selector in arguments.get("select", []):
            args += ["--select", selector]
        for selector in arguments.get("ignore", []):
            args += ["--ignore", selector]
        if arguments.get("compiler_feedback"):
            args += ["--compiler-feedback", arguments["compiler_feedback"]]
        code, output = self.run(args)
        if code != 0:
            raise ToolError(output)
        return output

    @staticmethod
    def _list_rules(arguments: dict) -> str:
        from .lint import RULES

        rules = [
            {"id": r.id, "name": r.name, "severity": r.severity, "default": r.default, "summary": r.summary}
            for r in sorted(RULES.values(), key=lambda r: r.id)
        ]
        return json.dumps(rules, indent=1)

    @staticmethod
    def _explain_rule(arguments: dict) -> str:
        from .lint import RULES

        rid = str(arguments.get("id", "")).upper()
        if rid not in RULES:
            raise ToolError(f"unknown rule '{arguments.get('id')}' (use list_rules)")
        return RULES[rid].explain()

    def _kb(self):
        from .kb import KnowledgeBase

        return KnowledgeBase.load(root=self.root)

    def _kb_search(self, arguments: dict) -> str:
        from .kb import PackError

        query = arguments.get("query", "")
        if not query:
            raise ToolError("query is required")
        try:
            kb = self._kb()
            results = kb.search(query, k=int(arguments.get("k", 5)), packs=arguments.get("packs") or None)
        except PackError as exc:
            raise ToolError(str(exc)) from exc
        found = [
            {"id": r.chunk.id, "heading": r.chunk.heading, "score": round(r.score, 2), "text": r.chunk.text}
            for r in results
        ]
        return json.dumps(found, indent=1)

    def _kb_show(self, arguments: dict) -> str:
        kb = self._kb()
        chunk_id = arguments.get("id", "")
        if chunk_id not in kb.by_id:
            raise ToolError(f"no section '{chunk_id}' (use kb_search)")
        context = int(arguments.get("context", 0))
        sections = kb.neighbours(chunk_id, before=context, after=context)
        pack = kb.packs[kb.get(chunk_id).pack]
        credit = f"\n\n-- {pack.name}: {pack.license}, {pack.meta.get('attribution', '')}" if pack.license else ""
        return "\n\n".join(f"## {c.heading} [{c.id}]\n\n{c.text}" for c in sections) + credit

    def _introspect(self, arguments: dict) -> str:
        sections = arguments.get("sections") or ["all"]
        return self._command(["introspect", *self._mode(arguments), *(f"--{s}" for s in sections)])

    def _test(self, arguments: dict) -> str:
        args = ["test", *self._mode(arguments)]
        if arguments.get("suite"):
            args += ["--suite", arguments["suite"]]
        if arguments.get("filter"):
            args += ["--filter", arguments["filter"]]
        if arguments.get("list"):
            args.append("--list")
        return self._command(args)

    def _tools(self) -> list[Tool]:
        return [
            Tool(
                "lint",
                "Run the FoBiS Fortran linter (bug-prone, obsolescent, non-portable constructs; OpenMP/OpenACC/MPI "
                "defects) on the project and return the findings as JSON (rule, severity, path, line, message).",
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
                    }
                ),
                self._lint,
            ),
            Tool(
                "list_rules", "List every lint rule: id, name, severity, default, summary.", _schema(), self._list_rules
            ),
            Tool(
                "explain_rule",
                "Explain a lint rule: why it matters, reported and preferred code, knowledge-pack references.",
                _schema({"id": {**_STR, "description": "rule id, e.g. OMP001"}}, ("id",)),
                self._explain_rule,
            ),
            Tool(
                "kb_search",
                "Search the knowledge packs (distilled Fortran 2023, OpenMP 6.0, OpenACC 3.4, MPI 5.0 references and "
                "HPC practice) by words, exact names (firstprivate, mpi_isend) or constraint ids (C1004).",
                _schema(
                    {
                        "query": _STR,
                        "k": {"type": "integer", "description": "number of results (default 5)"},
                        "packs": {**_STR_LIST, "description": "restrict to these packs"},
                    },
                    ("query",),
                ),
                self._kb_search,
            ),
            Tool(
                "kb_show",
                "Return a knowledge-pack section by id (as returned by kb_search), optionally with neighbours.",
                _schema({"id": _STR, "context": {"type": "integer", "description": "neighbouring sections"}}, ("id",)),
                self._kb_show,
            ),
            Tool(
                "introspect",
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
                "Validate the module dependency graph without compiling (missing modules, cycles, missing includes).",
                _schema({"mode": _MODE}),
                lambda a: self._command(["check", *self._mode(a)]),
            ),
            Tool(
                "build",
                "Build the project with FoBiS (writes objects and targets in the mode's build directory).",
                _schema({"mode": _MODE}),
                lambda a: self._command(["build", *self._mode(a)]),
            ),
            Tool(
                "test",
                "Discover, build and run the project's Fortran tests (or only list them).",
                _schema({"mode": _MODE, "suite": _STR, "filter": _STR, "list": {"type": "boolean"}}),
                self._test,
            ),
        ]

    # ── protocol ──────────────────────────────────────────────────────────────

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
            version = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            return _result(
                msg_id,
                {
                    "protocolVersion": version,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fobis", "version": __version__},
                    "instructions": "FoBiS tools for a Fortran project: lint, rule explanations, knowledge packs "
                    "(standards and HPC practice), build facts, dependency check, build, tests.",
                },
            )
        if method == "ping":
            return _result(msg_id, {})
        if method == "tools/list":
            return _result(msg_id, {"tools": [tool.listing() for tool in self.tools.values()]})
        if method == "tools/call":
            tool = self.tools.get(params.get("name", ""))
            if tool is None:
                return _error(msg_id, _INVALID_PARAMS, f"unknown tool '{params.get('name')}'")
            try:
                text, is_error = tool.handler(params.get("arguments") or {}), False
            except ToolError as exc:
                text, is_error = str(exc), True
            return _result(msg_id, {"content": [{"type": "text", "text": text}], "isError": is_error})
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
