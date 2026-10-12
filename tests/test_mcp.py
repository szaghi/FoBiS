"""Tests for fobis mcp — the Model Context Protocol server (JSON-RPC over stdio)."""

from __future__ import annotations

import io
import json
import os

import pytest

from fobis.mcp_server import PROTOCOL_VERSIONS, Server, fobis_command

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compiler-feedback")


def _request(msg_id, method, params=None):
    message = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def _call(server, name, arguments=None):
    response = server.handle(_request(1, "tools/call", {"name": name, "arguments": arguments or {}}))
    result = response["result"]
    return result["content"][0]["text"], result["isError"]


@pytest.fixture
def calls():
    return []


@pytest.fixture
def server(calls, tmp_path):
    def fake_run(args):
        calls.append(args)
        return 0, '{"findings": []}'

    return Server(root=str(tmp_path), run=fake_run)


def test_initialize_negotiates_protocol_version(server):
    result = server.handle(_request(1, "initialize", {"protocolVersion": "2025-03-26"}))["result"]
    assert result["protocolVersion"] == "2025-03-26"
    assert result["capabilities"] == {"tools": {}} and result["serverInfo"]["name"] == "fobis"
    newer = server.handle(_request(2, "initialize", {"protocolVersion": "2099-01-01"}))["result"]
    assert newer["protocolVersion"] == PROTOCOL_VERSIONS[0]


def test_notifications_get_no_response_and_ping_works(server):
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert server.handle(_request(3, "ping")) == {"jsonrpc": "2.0", "id": 3, "result": {}}


def test_tools_list_has_schemas(server):
    tools = server.handle(_request(1, "tools/list"))["result"]["tools"]
    names = [t["name"] for t in tools]
    assert names == [
        "lint",
        "list_rules",
        "explain_rule",
        "kb_search",
        "kb_show",
        "introspect",
        "check",
        "build",
        "test",
    ]
    assert all(t["inputSchema"]["type"] == "object" and t["description"] for t in tools)
    assert next(t for t in tools if t["name"] == "kb_search")["inputSchema"]["required"] == ["query"]


def test_errors(server):
    assert server.handle(_request(1, "bogus"))["error"]["code"] == -32601
    assert server.handle(_request(1, "tools/call", {"name": "nope"}))["error"]["code"] == -32602
    assert server.handle({"id": 1, "method": "ping"})["error"]["code"] == -32600  # no jsonrpc field


def test_lint_tool_builds_the_command(server, calls):
    arguments = {
        "paths": ["src"],
        "select": ["OMP", "ACC006"],
        "ignore": ["COR040"],
        "mode": "gnu",
        "compiler_feedback": "b.log",
    }
    text, is_error = _call(server, "lint", arguments)
    assert not is_error and json.loads(text) == {"findings": []}
    assert calls == [
        [
            "lint",
            "src",
            "--format",
            "json",
            "--exit-zero",
            "--mode",
            "gnu",
            "--select",
            "OMP",
            "--select",
            "ACC006",
            "--ignore",
            "COR040",
            "--compiler-feedback",
            "b.log",
        ]
    ]


def test_command_tools(server, calls):
    _call(server, "introspect", {"sections": ["sources", "compiler"]})
    _call(server, "check", {"mode": "gnu"})
    _call(server, "build")
    text, _ = _call(server, "test", {"suite": "unit", "list": True})
    assert calls == [
        ["introspect", "--sources", "--compiler"],
        ["check", "--mode", "gnu"],
        ["build"],
        ["test", "--suite", "unit", "--list"],
    ]
    assert text.startswith("exit code: 0")


def test_lint_tool_failure_is_an_error_result(tmp_path):
    server = Server(root=str(tmp_path), run=lambda args: (1, "Error: unknown rule or prefix 'X'"))
    text, is_error = _call(server, "lint", {"select": ["X"]})
    assert is_error and "unknown rule" in text


def test_rule_and_kb_tools_in_process(server):
    rules = json.loads(_call(server, "list_rules")[0])
    assert any(r["id"] == "OMP001" for r in rules)
    text, is_error = _call(server, "explain_rule", {"id": "acc006"})
    assert not is_error and "!$acc routine" in text
    assert _call(server, "explain_rule", {"id": "NOPE"})[1]
    found = json.loads(_call(server, "kb_search", {"query": "acc routine seq", "k": 2})[0])
    assert found[0]["id"] == "openacc:patterns#routine-for-device-callable-functions"
    shown, _ = _call(server, "kb_show", {"id": found[0]["id"]})
    assert "routine seq" in shown and "CC-BY-4.0" in shown
    assert _call(server, "kb_show", {"id": "no:such#id"})[1]
    assert _call(server, "kb_search", {"query": ""})[1]


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


def test_lint_tool_runs_fobis_for_real():
    server = Server(root=FIXTURE)
    text, is_error = _call(server, "lint", {"mode": "nv", "select": ["ACC001"], "compiler_feedback": "nvfortran-build.txt"})
    assert not is_error
    findings = json.loads(text)["findings"]
    assert [(f["rule"], f["line"]) for f in findings] == [("ACC001", 9), ("ACC001", 18)]
