"""Claude Science connector boundary — §7 of design/fusion-claude-science.md.

A thin, SDK-free policy core that maps a workbench (Claude Science session) tool
call onto a curated sci-adk CLI verb, enforcing the connector boundary:

  - default-deny allowlist: only the verbs below are exposed; everything else
    (amend-spec, init-spec, the *reqs freezes, package, run, execute,
    derive-claim, resolve, render, ...) is refused, so an in-session agent can
    never mutate the frozen criteria or the S5 autonomy carve-out;
  - ``append-evidence`` is exposed for the §5 Evidence mapping but REQUIRES the
    worker's frozen-spec digest (§7.2) -- the connector refuses it when absent and
    passes it through as ``--spec-digest``, so a session cannot append Evidence
    against a silently-revised Spec;
  - ``verify`` / ``status`` are exposed read-only (advisory).

FUS-1 (verdict purity) holds structurally, not by this connector: the binding
verdict is the Stop-hook ``sci-adk verify``, which the session cannot suppress, and
nothing exposed here bypasses the deterministic engine. This module is the policy
core only; the MCP wire transport (a local Desktop Extension) is a separate shell
that pulls the ``mcp`` dependency and is deferred pending tool-policy approval.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sci_adk.cli import main as _cli_main

# §7.1 -- read-only (advisory) verbs.
EXPOSED_READONLY: frozenset[str] = frozenset({"verify", "status"})

# §7.1 -- record-write verbs the session may drive.
EXPOSED_WRITE: frozenset[str] = frozenset(
    {"append-evidence", "prior-work", "novelty", "contested", "inquiry"}
)

# The full exposed surface. Default-deny: anything not here is refused.
EXPOSED: frozenset[str] = EXPOSED_READONLY | EXPOSED_WRITE

# §7.2 -- verbs the connector must not run without the worker's frozen-spec digest.
REQUIRE_SPEC_DIGEST: frozenset[str] = frozenset({"append-evidence"})


class ConnectorBoundaryError(Exception):
    """A tool call was refused at the connector boundary (§7).

    Raised before any CLI verb runs, so a refused call has no side effect on the
    record.
    """


@dataclass(frozen=True)
class ToolResult:
    """The outcome of a permitted verb: the verb name and the CLI exit code."""

    tool: str
    exit_code: int


def is_readonly(tool: str) -> bool:
    """True iff ``tool`` is one of the read-only advisory verbs (§7.1)."""
    return tool in EXPOSED_READONLY


def dispatch(
    tool: str,
    args: Sequence[str] = (),
    *,
    spec_digest: str | None = None,
    _runner: Callable[[list[str]], int] = _cli_main,
) -> ToolResult:
    """Run one exposed verb through the §7 boundary.

    ``args`` are the verb's own CLI arguments (e.g. the run dir + ``--evidence``).
    ``spec_digest`` is the worker's frozen-spec digest, required for
    ``append-evidence`` (§7.2) and injected as ``--spec-digest``.

    Raises ``ConnectorBoundaryError`` for a non-exposed verb (default-deny) or an
    ``append-evidence`` call with no digest -- in both cases nothing runs.
    """
    if tool not in EXPOSED:
        raise ConnectorBoundaryError(
            f"verb '{tool}' is not exposed by the connector "
            f"(§7 default-deny; exposed: {sorted(EXPOSED)})"
        )

    argv: list[str] = [tool, *args]

    if tool in REQUIRE_SPEC_DIGEST and not spec_digest:
        raise ConnectorBoundaryError(
            f"verb '{tool}' requires spec_digest (§7.2): the connector must pass "
            f"the worker's frozen-spec digest so Evidence cannot be appended "
            f"against a silently-revised Spec"
        )
    if tool in REQUIRE_SPEC_DIGEST:
        argv += ["--spec-digest", spec_digest]  # type: ignore[list-item]

    return ToolResult(tool=tool, exit_code=_runner(argv))
