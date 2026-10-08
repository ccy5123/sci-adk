"""
A literature-acquisition tool failure must write NOTHING to the append-only record.

Reproduces a real-run bug: ``sci-adk novelty ... --searched <DOIs> --outcome
found-nothing`` was called with broken input (all DOIs joined into ONE argument, and
later a broken paperforge install). paperforge exited 2 and wrote no manifest rows,
yet sci-adk still wrote a LITERATURE item (``acquired: 0, failed: 0``) AND a
NOVELTY_DECISION ``found_nothing`` -- permanently, since the log is append-only.

Contract pinned here:
  * paperforge exit code other than 0/1 -> ``AcquisitionToolError``, no evidence file.
  * exit 0/1 but no requested DOI in this call's manifest -> same error, nothing written.
  * a stale manifest left by an EARLIER call does not count as this call's output.
  * exit 1 with failed rows (the normal partial case) and exit 0 are unchanged.
  * CLI: the four ``--searched`` verbs reject a non-DOI / whitespace-joined argument
    with exit 2 before any acquisition, and surface the tool error with exit 1 and
    "nothing was recorded".
"""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.loop.inquiry import record_inquiry_searched
from sci_adk.loop.literature_acquirer import LiteratureAcquirer
from sci_adk.loop.literature_triggers import record_contested, record_novelty_searched
from sci_adk.loop.prior_work import record_prior_work_searched
from sci_adk.search.paperforge_adapter import (
    AcquisitionRecord,
    AcquisitionResult,
    AcquisitionToolError,
    PaperforgeAdapter,
)

_PROPOSAL = "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n"
_MANIFEST_FIELDS = ["index", "doi", "status", "source", "license", "filename",
                    "origin", "error", "bib"]


def _seed(workspace: Path, spec_id: str):
    result = ResearchCompiler(workspace_dir=workspace).compile(_PROPOSAL, spec_id=spec_id)
    return result.spec, workspace / "runs" / spec_id, result.spec.hypotheses[0].id


def _snapshot(run_dir: Path) -> dict[str, bytes]:
    """Every file under the run dir -> its bytes (evidence + literature artifacts)."""
    return {
        str(p.relative_to(run_dir)): p.read_bytes()
        for p in sorted(run_dir.rglob("*")) if p.is_file()
    }


def _evidence_files(run_dir: Path) -> list[str]:
    ev = run_dir / "evidence"
    return sorted(p.name for p in ev.glob("*.json")) if ev.is_dir() else []


def _evidence_kinds(run_dir: Path) -> list[str]:
    ev = run_dir / "evidence"
    return sorted(
        json.loads(p.read_text(encoding="utf-8"))["kind"] for p in ev.glob("*.json")
    ) if ev.is_dir() else []


class _ScriptedAdapter:
    """A fake adapter returning a fixed (returncode, records); records every call."""

    def __init__(self, returncode: int, records, stderr: str = ""):
        self.returncode = returncode
        self.records = records
        self.stderr = stderr
        self.calls: list[list[str]] = []

    def fetch(self, dois, output_dir, **options):
        output_dir = Path(output_dir)
        self.calls.append(list(dois))
        return AcquisitionResult(
            returncode=self.returncode,
            output_dir=output_dir,
            manifest_path=output_dir / "manifest.csv",
            records=list(self.records),
            provenance={"tool": "paperforge", "pinned_sha": "abc1234",
                        "installed_version": "0.1", "returncode": self.returncode},
            stderr=self.stderr,
        )


_NO_DOI_STDERR = "Ignoring input (not a file or DOI): 10.1/a 10.2/b\nNo DOIs found in the given inputs.\n"


# --------------------------------------------------------------------------- #
# acquirer / recorder level: fail closed, write nothing
# --------------------------------------------------------------------------- #

def test_exit2_empty_manifest_novelty_writes_nothing(tmp_path):
    spec, run_dir, hyp = _seed(tmp_path, "rc2-novelty")
    before = _snapshot(run_dir)
    adapter = _ScriptedAdapter(2, [], stderr=_NO_DOI_STDERR)

    with pytest.raises(AcquisitionToolError) as exc:
        record_novelty_searched(
            spec, tmp_path, hypothesis_id=hyp, kind="result", dois=["10.1/a", "10.2/b"],
            found="nothing", adapter=adapter, allow_no_email=True)

    assert exc.value.returncode == 2
    assert "No DOIs found" in exc.value.stderr_tail
    assert _snapshot(run_dir) == before   # no LITERATURE, no NOVELTY_DECISION


def test_exit2_empty_manifest_prior_work_writes_nothing(tmp_path):
    spec, run_dir, _ = _seed(tmp_path, "rc2-prior")
    before = _snapshot(run_dir)
    adapter = _ScriptedAdapter(2, [], stderr=_NO_DOI_STDERR)

    with pytest.raises(AcquisitionToolError):
        record_prior_work_searched(
            spec, tmp_path, dois=["10.1/a"], adapter=adapter, allow_no_email=True)

    assert _snapshot(run_dir) == before


def test_exit2_contested_and_inquiry_write_nothing(tmp_path):
    spec, run_dir, hyp = _seed(tmp_path, "rc2-other")
    before = _snapshot(run_dir)

    with pytest.raises(AcquisitionToolError):
        record_contested(spec, tmp_path, hypothesis_id=hyp, dois=["10.1/a"],
                         adapter=_ScriptedAdapter(2, []), allow_no_email=True)
    with pytest.raises(AcquisitionToolError):
        record_inquiry_searched(spec, tmp_path, question="has anyone measured X?",
                                dois=["10.1/a"], adapter=_ScriptedAdapter(2, []),
                                allow_no_email=True)

    assert _snapshot(run_dir) == before


def test_unexpected_returncode_is_fatal_even_with_rows(tmp_path):
    """Any exit code outside {0, 1} is a tool failure, whatever the manifest says."""
    spec, run_dir, _ = _seed(tmp_path, "rc3")
    rows = [AcquisitionRecord(doi="10.1/a", status="success", filename="A.pdf")]
    with pytest.raises(AcquisitionToolError) as exc:
        LiteratureAcquirer(spec, tmp_path, adapter=_ScriptedAdapter(3, rows)).acquire(
            ["10.1/a"])
    assert exc.value.returncode == 3
    assert _evidence_files(run_dir) == []


def test_exit0_but_no_requested_doi_in_manifest_writes_nothing(tmp_path):
    spec, run_dir, hyp = _seed(tmp_path, "rc0-miss")
    before = _snapshot(run_dir)
    unrelated = [AcquisitionRecord(doi="10.9/other", status="success", filename="O.pdf")]

    with pytest.raises(AcquisitionToolError) as exc:
        record_novelty_searched(
            spec, tmp_path, hypothesis_id=hyp, kind="result", dois=["10.1/a"],
            found="nothing", adapter=_ScriptedAdapter(0, unrelated), allow_no_email=True)

    assert exc.value.returncode == 0
    assert "10.1/a" in str(exc.value)
    assert _snapshot(run_dir) == before


def test_exit1_partial_is_unchanged(tmp_path):
    """The NORMAL partial case: evidence + decision written, halt surfaced."""
    spec, run_dir, hyp = _seed(tmp_path, "rc1-partial")
    rows = [
        AcquisitionRecord(doi="10.1/a", status="success", source="arxiv", filename="A.pdf"),
        AcquisitionRecord(doi="10.2/b", status="failed", error="no OA PDF"),
    ]
    outcome = record_novelty_searched(
        spec, tmp_path, hypothesis_id=hyp, kind="result", dois=["10.1/a", "10.2/b"],
        found="nothing", adapter=_ScriptedAdapter(1, rows), allow_no_email=True)

    assert outcome.should_halt
    assert [i.doi for i in outcome.halt.items] == ["10.2/b"]
    assert _evidence_kinds(run_dir) == ["literature", "novelty_decision"]


def test_exit1_every_doi_failed_is_still_a_recorded_null(tmp_path):
    """All requested DOIs present as ``failed`` rows = a real (null) result, not a tool error."""
    spec, run_dir, _ = _seed(tmp_path, "rc1-allfail")
    rows = [AcquisitionRecord(doi="10.1/A", status="failed", error="no OA PDF")]
    outcome = record_prior_work_searched(
        spec, tmp_path, dois=["https://doi.org/10.1/a"],
        adapter=_ScriptedAdapter(1, rows), allow_no_email=True)
    assert outcome.should_halt
    assert _evidence_kinds(run_dir) == ["literature", "prior_work_decision"]


def test_exit0_normal_is_unchanged(tmp_path):
    spec, run_dir, _ = _seed(tmp_path, "rc0-ok")
    rows = [AcquisitionRecord(doi="10.1/a", status="success", filename="A.pdf")]
    outcome = record_prior_work_searched(
        spec, tmp_path, dois=["10.1/a"], adapter=_ScriptedAdapter(0, rows),
        allow_no_email=True)
    assert not outcome.should_halt
    assert _evidence_kinds(run_dir) == ["literature", "prior_work_decision"]


# --------------------------------------------------------------------------- #
# real adapter (subprocess mocked): a stale manifest is not this call's output
# --------------------------------------------------------------------------- #

def _write_manifest(path: Path, dois: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_MANIFEST_FIELDS)
        w.writeheader()
        for i, d in enumerate(dois, start=1):
            w.writerow({"index": i, "doi": d, "status": "success", "source": "arxiv",
                        "filename": f"{i}.pdf"})


@pytest.mark.parametrize("returncode", [1, 2])
def test_stale_manifest_from_earlier_call_does_not_mask_failure(
        tmp_path, monkeypatch, returncode):
    """An earlier successful call left manifest.csv + references.bib holding the very
    DOIs requested now. This call crashes without writing (a broken install exits 1 with
    a traceback; a usage error exits 2): the stale rows must not pass for its output,
    and the earlier artifacts must be left byte-identical."""
    spec, run_dir, _ = _seed(tmp_path, f"stale-{returncode}")
    lit = run_dir / "literature"
    _write_manifest(lit / "manifest.csv", ["10.1/a"])
    (lit / "references.bib").write_text("@article{Joe2020, doi={10.1/a}}\n",
                                        encoding="utf-8")
    before = _snapshot(run_dir)

    def crashed_run(cmd, **kw):
        return subprocess.CompletedProcess(
            cmd, returncode, stdout="",
            stderr="Traceback (most recent call last):\nModuleNotFoundError: paperforge\n")

    monkeypatch.setattr("sci_adk.search.paperforge_adapter.subprocess.run", crashed_run)
    adapter = PaperforgeAdapter(paperforge_bin="/fake/paperforge")

    with pytest.raises(AcquisitionToolError) as exc:
        LiteratureAcquirer(spec, tmp_path, adapter=adapter).acquire(["10.1/a"])

    assert exc.value.returncode == returncode
    assert "ModuleNotFoundError" in exc.value.stderr_tail
    assert _snapshot(run_dir) == before


def test_real_adapter_fresh_manifest_still_parsed(tmp_path, monkeypatch):
    spec, run_dir, _ = _seed(tmp_path, "fresh")
    out = run_dir / "literature"

    def ok_run(cmd, **kw):
        _write_manifest(out / "manifest.csv", ["10.1/a"])
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("sci_adk.search.paperforge_adapter.subprocess.run", ok_run)
    adapter = PaperforgeAdapter(paperforge_bin="/fake/paperforge")
    outcome = LiteratureAcquirer(spec, tmp_path, adapter=adapter).acquire(["10.1/a"])
    assert [r.doi for r in outcome.result.records] == ["10.1/a"]
    assert _evidence_kinds(run_dir) == ["literature"]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _swap_adapter(monkeypatch, adapter):
    """Route every recorder's acquirer to ``adapter`` (all four verbs import the class)."""
    import sci_adk.loop.inquiry as inq_mod
    import sci_adk.loop.literature_triggers as lt_mod
    import sci_adk.loop.prior_work as pw_mod

    real = LiteratureAcquirer

    class _Acq(real):
        def __init__(self, spec, workspace_dir=None, adapter=None, email=None):
            super().__init__(spec, workspace_dir, adapter=spy, email=email)

    spy = adapter
    for mod in (lt_mod, pw_mod, inq_mod):
        monkeypatch.setattr(mod, "LiteratureAcquirer", _Acq)


def _verb_argv(verb: str, run_dir: Path, hyp: str, searched: list[str]) -> list[str]:
    base = {
        "novelty": ["novelty", str(run_dir), "--hypothesis", hyp, "--kind", "result",
                    "--outcome", "found-nothing"],
        "prior-work": ["prior-work", str(run_dir)],
        "contested": ["contested", str(run_dir), "--hypothesis", hyp],
        "inquiry": ["inquiry", str(run_dir), "--question", "has anyone measured X?"],
    }[verb]
    return base + ["--searched", *searched, "--allow-no-email"]


_VERBS = ["novelty", "prior-work", "contested", "inquiry"]


@pytest.mark.parametrize("verb", _VERBS)
def test_cli_joined_doi_string_rejected_before_acquisition(
        tmp_path, monkeypatch, capsys, verb):
    _, run_dir, hyp = _seed(tmp_path, f"cli-joined-{verb}")
    spy = _ScriptedAdapter(0, [])
    _swap_adapter(monkeypatch, spy)
    before = _snapshot(run_dir)

    rc = main(_verb_argv(verb, run_dir, hyp, ["10.1/a 10.2/b"]))
    err = capsys.readouterr().err

    assert rc == 2
    assert "10.1/a 10.2/b" in err
    assert spy.calls == []
    assert _snapshot(run_dir) == before


@pytest.mark.parametrize("verb", _VERBS)
def test_cli_non_doi_token_rejected(tmp_path, monkeypatch, capsys, verb):
    _, run_dir, hyp = _seed(tmp_path, f"cli-nondoi-{verb}")
    spy = _ScriptedAdapter(0, [])
    _swap_adapter(monkeypatch, spy)

    rc = main(_verb_argv(verb, run_dir, hyp, ["10.1/a", "Smith2020"]))
    err = capsys.readouterr().err

    assert rc == 2
    assert "Smith2020" in err
    assert spy.calls == []


def test_cli_accepts_prefixed_doi(tmp_path, monkeypatch, capsys):
    _, run_dir, hyp = _seed(tmp_path, "cli-prefixed")
    rows = [AcquisitionRecord(doi="10.1021/c160017a018", status="success", filename="A.pdf")]
    spy = _ScriptedAdapter(0, rows)
    _swap_adapter(monkeypatch, spy)

    rc = main(_verb_argv("prior-work", run_dir, hyp,
                         ["https://doi.org/10.1021/c160017a018"]))
    assert rc == 0, capsys.readouterr().err
    assert len(spy.calls) == 1


@pytest.mark.parametrize("verb", _VERBS)
def test_cli_tool_failure_exits_nonzero_and_says_nothing_recorded(
        tmp_path, monkeypatch, capsys, verb):
    _, run_dir, hyp = _seed(tmp_path, f"cli-toolfail-{verb}")
    _swap_adapter(monkeypatch, _ScriptedAdapter(2, [], stderr=_NO_DOI_STDERR))
    before = _snapshot(run_dir)

    rc = main(_verb_argv(verb, run_dir, hyp, ["10.1/a"]))
    err = capsys.readouterr().err

    assert rc == 1
    assert "returncode 2" in err or "exit code 2" in err
    assert "No DOIs found" in err
    assert "nothing was recorded" in err.lower()
    assert _snapshot(run_dir) == before
