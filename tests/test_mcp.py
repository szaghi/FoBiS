"""Tests for fobis mcp — the Model Context Protocol server (JSON-RPC over stdio): handshake, the tool catalogue and
its annotations, the command line of every subprocess tool, JSON results (structuredContent from 2025-06-18,
findings trimmed, a failed build is a result not an error), in-process rule and pack tools, resources, the stream,
and real runs of fobis behind the tools."""

from __future__ import annotations

import io
import json
import os
import subprocess

import pytest

from fobis.mcp_server import MAX_FINDINGS, PROTOCOL_VERSIONS, Server, fobis_command

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compiler-feedback")
TOOLS = [
    "lint",
    "review",
    "list_rules",
    "explain_rule",
    "kb_search",
    "kb_show",
    "ask_context",
    "introspect",
    "check",
    "tree",
    "merge_conflicts",
    "commit_facts",
    "testgen_skeleton",
    "ecosystem_status",
    "ecosystem_impact",
    "case_list",
    "provenance",
    "build",
    "test",
    "case_run",
    "clean",
    "fetch",
]


def _request(msg_id, method, params=None):
    message = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def _result(server, name, arguments=None):
    return server.handle(_request(1, "tools/call", {"name": name, "arguments": arguments or {}}))["result"]


def _call(server, name, arguments=None):
    result = _result(server, name, arguments)
    return result["content"][0]["text"], result["isError"]


@pytest.fixture
def calls():
    return []


@pytest.fixture
def reply():
    return {"code": 0, "out": '{"findings": []}', "err": ""}


@pytest.fixture
def server(calls, reply, tmp_path):
    def fake_run(args):
        calls.append(args)
        return reply["code"], reply["out"], reply["err"]

    return Server(root=str(tmp_path), run=fake_run)


# ── protocol ───────────────────────────────────────────────────────────────────


def test_initialize_negotiates_protocol_version(server):
    result = server.handle(_request(1, "initialize", {"protocolVersion": "2025-03-26"}))["result"]
    assert result["protocolVersion"] == "2025-03-26"
    assert result["capabilities"] == {"tools": {}, "resources": {}} and result["serverInfo"]["name"] == "fobis"
    newer = server.handle(_request(2, "initialize", {"protocolVersion": "2099-01-01"}))["result"]
    assert newer["protocolVersion"] == PROTOCOL_VERSIONS[0]


def test_notifications_get_no_response_and_ping_works(server):
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert server.handle(_request(3, "ping")) == {"jsonrpc": "2.0", "id": 3, "result": {}}


def test_tools_list_has_schemas_and_annotations(server):
    tools = {t["name"]: t for t in server.handle(_request(1, "tools/list"))["result"]["tools"]}
    assert list(tools) == TOOLS
    assert all(t["inputSchema"]["type"] == "object" and t["description"] and t["title"] for t in tools.values())
    assert tools["kb_search"]["inputSchema"]["required"] == ["query"]
    hints = {n: t["annotations"] for n, t in tools.items()}
    assert {n for n, a in hints.items() if not a["readOnlyHint"]} == {"build", "test", "case_run", "clean", "fetch"}
    assert {n for n, a in hints.items() if a["destructiveHint"]} == {"clean"}
    assert {n for n, a in hints.items() if a["openWorldHint"]} == {"ecosystem_status", "fetch"}
    assert not hints["fetch"]["idempotentHint"] and hints["build"]["idempotentHint"]


def test_errors(server):
    assert server.handle(_request(1, "bogus"))["error"]["code"] == -32601
    assert server.handle(_request(1, "tools/call", {"name": "nope"}))["error"]["code"] == -32602
    assert server.handle({"id": 1, "method": "ping"})["error"]["code"] == -32600  # no jsonrpc field


def test_structured_content_only_from_2025_06_18(server):
    server.handle(_request(1, "initialize", {"protocolVersion": "2025-06-18"}))
    assert _result(server, "lint")["structuredContent"] == {"findings": []}
    server.handle(_request(1, "initialize", {"protocolVersion": "2025-03-26"}))
    result = _result(server, "lint")
    assert "structuredContent" not in result and json.loads(result["content"][0]["text"]) == {"findings": []}


# ── subprocess tools ───────────────────────────────────────────────────────────


def test_command_lines(server, calls):
    _call(server, "lint", {"paths": ["src"], "select": ["OMP", "ACC006"], "ignore": ["COR040"], "mode": "gnu"})
    _call(server, "lint", {"compiler_feedback": "b.log", "fix_diff": True})
    _call(server, "review", {"staged": True, "base": "origin/master", "context": 2, "select": ["OMP"]})
    _call(server, "ask_context", {"question": "why?", "project": ["src"], "packs": ["openmp"], "k": 3})
    _call(server, "introspect", {"sections": ["sources", "compiler"]})
    _call(server, "check", {"mode": "gnu"})
    _call(server, "tree", {"depth": 2})
    _call(server, "merge_conflicts", {"paths": ["a.f90"]})
    _call(server, "commit_facts")
    _call(server, "testgen_skeleton", {"module": "m", "procedures": ["f"], "max": 3})
    _call(server, "ecosystem_status", {"config": "c.ini"})
    _call(server, "ecosystem_impact", {"project": "penf", "base": "v1"})
    _call(server, "build", {"mode": "gnu", "target": "app.f90"})
    _call(server, "test", {"suite": "unit", "filter": "t_*", "list": True})
    _call(server, "clean")
    _call(server, "fetch", {"update": True})
    _call(server, "case_list")
    _call(server, "provenance", {"mode": "gnu"})
    _call(server, "case_run", {"names": ["sod"], "mode": "gnu"})
    assert calls == [
        [
            "lint",
            "src",
            "--mode",
            "gnu",
            "--select",
            "OMP",
            "--select",
            "ACC006",
            "--ignore",
            "COR040",
            "--format",
            "json",
            "--exit-zero",
        ],
        ["lint", "--compiler-feedback", "b.log", "--diff"],
        [
            "review",
            "--format",
            "json",
            "--exit-zero",
            "--staged",
            "--base",
            "origin/master",
            "--context",
            "2",
            "--select",
            "OMP",
        ],
        ["ask", "why?", "--show-context", "--json", "-k", "3", "--project", "src", "--pack", "openmp"],
        ["introspect", "--sources", "--compiler"],
        ["check", "--json", "--mode", "gnu"],
        ["tree", "--json", "--depth", "2"],
        ["merge-assist", "a.f90", "--no-model", "--format", "json"],
        ["commit", "--show-facts", "--json"],
        ["testgen", "m", "--skeleton", "--format", "json", "--procedure", "f", "--max", "3"],
        ["ecosystem", "dashboard", "--json", "--config", "c.ini"],
        ["ecosystem", "impact", "penf", "--format", "json", "--base", "v1"],
        ["build", "--json", "--mode", "gnu", "--target", "app.f90"],
        ["test", "--json", "--suite", "unit", "--filter", "t_*", "--list"],
        ["clean", "--json"],
        ["fetch", "--json", "--update"],
        ["case", "list", "--json"],
        ["provenance", "--json", "--mode", "gnu"],
        ["case", "run", "sod", "--json", "--mode", "gnu"],
    ]


def test_required_arguments(server, calls):
    assert _call(server, "ask_context", {"question": " "})[1]
    assert _call(server, "testgen_skeleton")[1]
    assert calls == []


def test_a_failed_command_with_json_is_a_result_not_an_error(server, reply):
    reply.update(code=1, out='Building...\n{"status": "error", "diagnoses": [{"kind": "missing-module"}]}')
    server.handle(_request(1, "initialize", {"protocolVersion": "2025-06-18"}))
    result = _result(server, "build")
    assert not result["isError"] and result["structuredContent"]["diagnoses"][0]["kind"] == "missing-module"


def test_a_failed_command_without_json_is_an_error(server, reply):
    reply.update(code=1, out="", err="Error: unknown rule or prefix 'X'")
    text, is_error = _call(server, "lint", {"select": ["X"]})
    assert is_error and "unknown rule" in text and "exit 1" in text


def test_findings_are_trimmed(server, reply):
    findings = [{"rule": "COR001", "line": i} for i in range(MAX_FINDINGS + 5)]
    reply["out"] = json.dumps({"findings": findings})
    data = json.loads(_call(server, "lint")[0])
    assert len(data["findings"]) == MAX_FINDINGS
    assert data["truncated"] == {"findings": MAX_FINDINGS + 5, "returned": MAX_FINDINGS}
    assert len(json.loads(_call(server, "review", {"max_findings": 3})[0])["findings"]) == 3


# ── in-process tools and resources ─────────────────────────────────────────────


def test_rule_and_kb_tools_in_process(server):
    rules = json.loads(_call(server, "list_rules")[0])["rules"]
    assert any(r["id"] == "OMP001" for r in rules)
    assert {r["id"][:3] for r in json.loads(_call(server, "list_rules", {"prefix": "acc"})[0])["rules"]} == {"ACC"}
    text, is_error = _call(server, "explain_rule", {"id": "acc006"})
    assert not is_error and "!$acc routine" in text
    assert _call(server, "explain_rule", {"id": "NOPE"})[1]
    found = json.loads(_call(server, "kb_search", {"query": "acc routine seq", "k": 2})[0])["results"]
    assert found[0]["id"] == "openacc:patterns#routine-for-device-callable-functions"
    assert found[0]["uri"] == "fobis://kb/openacc%3Apatterns%23routine-for-device-callable-functions"
    shown, _ = _call(server, "kb_show", {"id": found[0]["id"]})
    assert "routine seq" in shown and "CC-BY-4.0" in shown
    assert _call(server, "kb_show", {"id": "no:such#id"})[1]
    assert _call(server, "kb_search", {"query": ""})[1]


def test_resources(server):
    resources = server.handle(_request(1, "resources/list"))["result"]["resources"]
    omp001 = next(r for r in resources if r["name"] == "OMP001")
    assert omp001["uri"] == "fobis://rules/OMP001" and omp001["mimeType"] == "text/markdown"
    read = server.handle(_request(2, "resources/read", {"uri": "fobis://rules/omp001"}))["result"]["contents"][0]
    assert read["uri"] == "fobis://rules/omp001" and read["text"].startswith("OMP001")
    template = server.handle(_request(3, "resources/templates/list"))["result"]["resourceTemplates"][0]
    assert template["uriTemplate"] == "fobis://kb/{id}"
    uri = "fobis://kb/openacc%3Apatterns%23routine-for-device-callable-functions"
    section = server.handle(_request(4, "resources/read", {"uri": uri}))["result"]["contents"][0]["text"]
    assert "routine seq" in section
    assert server.handle(_request(5, "resources/read", {"uri": "fobis://nope"}))["error"]["code"] == -32002


def test_serve_over_streams(server):
    lines = [
        json.dumps(_request(1, "initialize", {"protocolVersion": "2025-06-18"})),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        "",
        "{not json",
        json.dumps(_request(2, "tools/list")),
    ]
    out = io.StringIO()
    server.serve(io.StringIO("\n".join(lines) + "\n"), out)
    responses = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r.get("id") for r in responses] == [1, None, 2]
    assert responses[1]["error"]["code"] == -32700


def test_fobis_command_from_a_package_directory():
    assert fobis_command()[1:] == ["-m", "fobis"]


# ── real fobis behind the tools ────────────────────────────────────────────────


def test_lint_tool_runs_fobis_for_real():
    server = Server(root=FIXTURE)
    text, is_error = _call(
        server, "lint", {"mode": "nv", "select": ["ACC001"], "compiler_feedback": "nvfortran-build.txt"}
    )
    assert not is_error
    findings = json.loads(text)["findings"]
    assert [(f["rule"], f["line"]) for f in findings] == [("ACC001", 9), ("ACC001", 18)]


def test_build_check_and_test_tools_for_real(tmp_path):
    """A project with a missing module: check and build diagnose it, test reports each test's facts."""
    (tmp_path / "src").mkdir()
    (tmp_path / "test").mkdir()
    (tmp_path / "src" / "m.f90").write_text(
        "module m\ncontains\ninteger function one()\none = 1\nend function\nend module m\n"
    )
    (tmp_path / "test" / "t_ok.f90").write_text("program t_ok\nuse m\nif (one() /= 1) error stop 1\nend program t_ok\n")
    (tmp_path / "test" / "t_bad.f90").write_text("program t_bad\nuse nothere\nend program t_bad\n")
    (tmp_path / "fobos").write_text("[default]\ncompiler = gnu\nsrc = ./\nbuild_dir = ./build/\n")
    server = Server(root=str(tmp_path))
    server.handle(_request(1, "initialize", {"protocolVersion": "2025-06-18"}))
    check = _result(server, "check")["structuredContent"]
    assert check["status"] == "error" and check["unresolved"][0]["dependency"] == "nothere"
    build = _result(server, "build", {"target": "test/t_bad.f90"})
    assert not build["isError"] and build["structuredContent"]["diagnoses"][0]["kind"] == "missing-module"
    tests = {r["name"]: r for r in _result(server, "test")["structuredContent"]["results"]}
    assert tests["t_ok"]["status"] == "passed" and tests["t_bad"]["status"] == "build-failed"
    assert tests["t_bad"]["diagnoses"][0]["summary"].startswith("module nothere is not available")


def test_merge_conflicts_tool_for_real(tmp_path, monkeypatch):
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = T\n\temail = t@t\n[commit]\n\tgpgsign = false\n[color]\n\tui = always\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))

    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=False, capture_output=True, text=True)

    source = tmp_path / "m.f90"
    source.write_text("module m\nuse iso_fortran_env, only: int32\nimplicit none\nend module m\n")
    git("init", "-q", "-b", "master")
    git("add", ".")
    git("commit", "-qm", "feat: m")
    git("checkout", "-qb", "other")
    source.write_text(source.read_text().replace("int32", "int32, real64"))
    git("commit", "-qam", "feat: real64")
    git("checkout", "-q", "master")
    source.write_text(source.read_text().replace("int32", "int32, int64"))
    git("commit", "-qam", "feat: int64")
    git("merge", "other")
    server = Server(root=str(tmp_path))
    server.handle(_request(1, "initialize", {"protocolVersion": "2025-06-18"}))
    data = _result(server, "merge_conflicts")["structuredContent"]
    (hunk,) = data["files"][0]["hunks"]
    assert data["operation"]["kind"] == "merge" and data["files"][0]["compiles"] is True
    assert hunk["resolution"]["lines"] == ["use iso_fortran_env, only: int32, int64, real64"]
    assert "<<<<<<<" in source.read_text()  # nothing written
