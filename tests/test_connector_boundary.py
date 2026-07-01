"""Connector boundary tests -- design/fusion-claude-science.md §7.

The connector's job is only the boundary: which verbs are exposed (default-deny),
and that ``append-evidence`` always carries the spec digest. The digest ENFORCEMENT
itself (wrong digest -> exit 2 + no write) is proven by ``test_spec_digest_boundary``;
here we prove the connector always SUPPLIES it and refuses when it is absent, and
that criteria-mutation / autonomy-carveout verbs are never exposed.
"""

from __future__ import annotations

import pytest

from sci_adk.adapter.connector import (
    EXPOSED,
    ConnectorBoundaryError,
    ToolResult,
    dispatch,
    is_readonly,
)


def _spy() -> tuple[list[list[str]], object]:
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> int:
        calls.append(list(argv))
        return 0

    return calls, runner


# -- default-deny allowlist --------------------------------------------------


@pytest.mark.parametrize(
    "blocked",
    [
        "amend-spec", "init-spec", "pubreqs", "pkgreqs", "package", "run",
        "execute", "derive-claim", "resolve", "render", "init-session",
    ],
)
def test_criteria_and_carveout_verbs_are_blocked(blocked: str) -> None:
    calls, runner = _spy()
    with pytest.raises(ConnectorBoundaryError):
        dispatch(blocked, ["runs/x"], _runner=runner)
    assert calls == [], "a refused verb must not run (no side effect)"


def test_unknown_verb_default_denied() -> None:
    calls, runner = _spy()
    with pytest.raises(ConnectorBoundaryError):
        dispatch("rm-the-record", [], _runner=runner)
    assert calls == []


def test_exposed_surface_excludes_mutation() -> None:
    # regression: the exposed set never grows to include criteria mutation / S5.
    for v in ("amend-spec", "init-spec", "pubreqs", "pkgreqs", "derive-claim"):
        assert v not in EXPOSED


# -- append-evidence requires the spec digest (§7.2) -------------------------


def test_append_evidence_without_digest_refused() -> None:
    calls, runner = _spy()
    with pytest.raises(ConnectorBoundaryError) as exc:
        dispatch(
            "append-evidence", ["runs/x", "--evidence", "e.json"], _runner=runner
        )
    assert "spec_digest" in str(exc.value)
    assert calls == [], "no digest -> nothing runs"


def test_append_evidence_injects_digest() -> None:
    calls, runner = _spy()
    result = dispatch(
        "append-evidence",
        ["runs/x", "--evidence", "e.json"],
        spec_digest="deadbeef",
        _runner=runner,
    )
    assert result == ToolResult(tool="append-evidence", exit_code=0)
    assert calls == [
        ["append-evidence", "runs/x", "--evidence", "e.json",
         "--spec-digest", "deadbeef"]
    ]


# -- read-only + write verbs exposed -----------------------------------------


@pytest.mark.parametrize("tool", ["verify", "status"])
def test_readonly_verbs_exposed(tool: str) -> None:
    calls, runner = _spy()
    result = dispatch(tool, ["runs/x"], _runner=runner)
    assert result.exit_code == 0
    assert is_readonly(tool)
    assert calls == [[tool, "runs/x"]]


@pytest.mark.parametrize("tool", ["prior-work", "novelty", "contested"])
def test_write_verbs_exposed_without_digest(tool: str) -> None:
    calls, runner = _spy()
    result = dispatch(tool, ["runs/x", "--skip", "--reason", "r"], _runner=runner)
    assert result.exit_code == 0
    assert not is_readonly(tool)
    assert calls and calls[0][0] == tool
