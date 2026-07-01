"""Claude Science connector -- MCP wire transport (local Desktop Extension).

Exposes the §7 boundary core (``connector.py``) as MCP tools over stdio so a Claude
Science session can drive the sci-adk record through a curated, default-deny surface.
FUS-1 holds: nothing here bypasses the deterministic engine; the binding verdict is
the Stop-hook ``sci-adk verify``.

Requires the optional ``mcp`` dependency::  pip install -e ".[connector]"
Run::  sci-adk-connector      # or: python -m sci_adk.adapter.connector_server
"""

from __future__ import annotations

import contextlib
import io
from typing import Any

from sci_adk.adapter import connector


def _invoke(
    tool: str, args: list[str], *, spec_digest: str | None = None
) -> dict[str, Any]:
    """Run one boundary-checked verb, capturing its stdout/stderr.

    Capture matters twice over: it keeps the CLI's prints off the MCP stdio stream
    (which carries the JSON-RPC protocol) and returns the report to the caller.
    """
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = connector.dispatch(tool, args, spec_digest=spec_digest)
    except connector.ConnectorBoundaryError as exc:
        return {"tool": tool, "ok": False, "refused": str(exc)}
    return {
        "tool": result.tool,
        "exit_code": result.exit_code,
        "ok": result.exit_code == 0,
        "stdout": out.getvalue(),
        "stderr": err.getvalue(),
    }


def append_evidence(
    run_dir: str, evidence_path: str, spec_digest: str
) -> dict[str, Any]:
    """Append one typed EvidenceItem (the JSON at ``evidence_path``) to the run's
    append-only Evidence log. ``spec_digest`` is REQUIRED (§7.2): pass the digest from
    your [FROZEN SPEC REFERENCE]; a mismatch with the recorded Spec is refused and
    nothing is written."""
    return _invoke(
        "append-evidence",
        [run_dir, "--evidence", evidence_path],
        spec_digest=spec_digest,
    )


def verify(run_dir: str, strict_science: bool = False) -> dict[str, Any]:
    """Read-only belief audit: re-apply the frozen rules to the recorded Evidence
    (no re-run, no LLM). Advisory only -- the binding verdict is the Stop-hook.
    ``exit_code`` 0 iff every recorded claim reproduces."""
    args = [run_dir, "--strict-science"] if strict_science else [run_dir]
    return _invoke("verify", args)


def status(run_dir: str) -> dict[str, Any]:
    """Read-only session-state snapshot (recorded claim statuses + open decisions)
    for ``run_dir``. Cheap; safe to call every turn."""
    return _invoke("status", [run_dir, "--json"])


def build_server() -> Any:  # -> mcp.server.fastmcp.FastMCP
    """Build the FastMCP server exposing the §7 read/write surface.

    Imports ``mcp`` lazily so the base install stays free of the dependency.
    """
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("sci-adk")
    server.tool()(append_evidence)
    server.tool()(verify)
    server.tool()(status)
    return server


def main() -> None:
    """Console entry (``sci-adk-connector``): serve the tools over stdio."""
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
