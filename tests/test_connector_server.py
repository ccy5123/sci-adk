"""Connector wire-transport tests -- design/fusion-claude-science.md §12(a).

The routing tests are dependency-free (they call the tool handlers directly with a
spy dispatch); only ``build_server`` needs the optional ``mcp`` package, so that test
``importorskip``s it. The boundary itself is proven by ``test_connector_boundary``;
here we prove the wire tools route to the right verb, inject the digest, and CAPTURE
the CLI's stdout (so it cannot corrupt the MCP stdio JSON-RPC stream).
"""

from __future__ import annotations

import pytest

from sci_adk.adapter import connector, connector_server
from sci_adk.adapter.connector import ToolResult


def _spy(monkeypatch, exit_code: int = 0, prints: str = ""):
    calls: list[tuple[str, list[str], str | None]] = []

    def fake_dispatch(tool, args=(), *, spec_digest=None, **_kw):
        calls.append((tool, list(args), spec_digest))
        if prints:
            print(prints)  # simulate the CLI writing to stdout
        return ToolResult(tool=tool, exit_code=exit_code)

    monkeypatch.setattr(connector, "dispatch", fake_dispatch)
    return calls


def test_append_evidence_routes_and_injects_digest(monkeypatch):
    calls = _spy(monkeypatch)
    out = connector_server.append_evidence("runs/x", "e.json", "abc")
    assert calls == [("append-evidence", ["runs/x", "--evidence", "e.json"], "abc")]
    assert out["ok"] is True and out["exit_code"] == 0


def test_verify_strict_flag(monkeypatch):
    calls = _spy(monkeypatch)
    connector_server.verify("runs/x", strict_science=True)
    assert calls == [("verify", ["runs/x", "--strict-science"], None)]


def test_status_routes(monkeypatch):
    calls = _spy(monkeypatch)
    connector_server.status("runs/x")
    assert calls == [("status", ["runs/x", "--json"], None)]


def test_cli_stdout_is_captured_not_leaked(monkeypatch, capsys):
    """The CLI's stdout must be captured into the result, never leaked to the real
    stdout (which carries the MCP JSON-RPC protocol)."""
    _spy(monkeypatch, prints="derive-claim: ...")
    out = connector_server.verify("runs/x")
    assert "derive-claim: ..." in out["stdout"]
    leaked = capsys.readouterr().out
    assert "derive-claim" not in leaked, "CLI stdout leaked past the capture"


def test_verify_nonzero_exit_reports_not_ok(monkeypatch):
    _spy(monkeypatch, exit_code=2)
    out = connector_server.verify("runs/x")
    assert out["ok"] is False and out["exit_code"] == 2


def test_boundary_refusal_is_structured(monkeypatch):
    def refuse(tool, args=(), *, spec_digest=None, **_kw):
        raise connector.ConnectorBoundaryError("nope")

    monkeypatch.setattr(connector, "dispatch", refuse)
    out = connector_server.append_evidence("runs/x", "e.json", "")
    assert out["ok"] is False and "nope" in out["refused"]


def test_build_server_registers_exposed_tools():
    pytest.importorskip("mcp")
    server = connector_server.build_server()
    # FastMCP exposes registered tools via list_tools() (async) or the tool manager;
    # assert the three wire tools are present by name via the tool manager registry.
    names = {t.name for t in server._tool_manager.list_tools()}
    assert {"append_evidence", "verify", "status"} <= names
