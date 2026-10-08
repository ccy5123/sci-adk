"""
``--search-log FILE [FILE ...]`` on the literature-decision verbs
(design/parallel-literature-search.md §4.4).

The flag is valid only on the searched path. Every file is validated BEFORE any
acquisition or write (fail-closed: a bad log records nothing). For ``novelty`` /
``contested`` a file's ``hypothesis_id`` / ``kind``, when present, must match the CLI.
No network: the acquirer is swapped for one driving a fake adapter.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sci_adk.cli import main
from sci_adk.core.claim import Claim, ClaimStatus, Confidence, ConfidenceType
from sci_adk.core.evidence import EvidenceItem, EvidenceKind
from sci_adk.core.spec import HypothesisMode
from sci_adk.loop.compiler import ResearchCompiler
from sci_adk.search.paperforge_adapter import AcquisitionRecord, AcquisitionResult

_PROPOSAL = "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n"


def _seed(workspace: Path, spec_id: str) -> tuple[Path, str]:
    result = ResearchCompiler(workspace_dir=workspace).compile(_PROPOSAL, spec_id=spec_id)
    return workspace / "runs" / spec_id, result.spec.hypotheses[0].id


def _evidence(run_dir: Path) -> list[EvidenceItem]:
    ev_dir = run_dir / "evidence"
    if not ev_dir.is_dir():
        return []
    return [EvidenceItem.model_validate(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(ev_dir.glob("*.json"))]


class _FakeAdapter:
    calls = 0

    def fetch(self, dois, out_dir, **opts):
        type(self).calls += 1
        out_dir = Path(out_dir)
        return AcquisitionResult(
            returncode=0, output_dir=out_dir, manifest_path=out_dir / "manifest.csv",
            records=[AcquisitionRecord(doi=d, status="success", source="arxiv",
                                       license="cc-by", filename=f"{i}.pdf")
                     for i, d in enumerate(dois)],
            provenance={"pinned_sha": "abc1234", "installed_version": "0.1"},
        )


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """No email, no network: every module's acquirer drives the fake adapter."""
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "xdg").mkdir(parents=True, exist_ok=True)
    _FakeAdapter.calls = 0

    import sci_adk.loop.inquiry as inq_mod
    import sci_adk.loop.literature_triggers as lt_mod
    import sci_adk.loop.prior_work as pw_mod

    for mod in (lt_mod, pw_mod, inq_mod):
        real = mod.LiteratureAcquirer

        class _FakeAcquirer(real):  # type: ignore[misc, valid-type]
            def __init__(self, spec, workspace_dir=None, adapter=None, email=None):
                super().__init__(spec, workspace_dir, adapter=_FakeAdapter(), email=email)

        monkeypatch.setattr(mod, "LiteratureAcquirer", _FakeAcquirer)
    return _FakeAdapter


def _log(tmp_path: Path, name: str, **overrides) -> Path:
    data = {
        "searched_at": "2026-10-08T05:12:44Z",
        "queries": [
            {"index": "openalex", "query": "q one", "status": "ok", "n_results": 3},
            {"index": "arxiv", "query": "q two", "status": "ok"},
        ],
        "candidates": [],
    }
    data.update(overrides)
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# searched path only
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("verb", ["novelty", "prior-work", "inquiry"])
def test_search_log_rejected_with_skip(tmp_path, capsys, verb):
    run_dir, hyp_id = _seed(tmp_path, f"cli-sl-skip-{verb}")
    log = _log(tmp_path, "log.json")
    argv = [verb, str(run_dir)]
    if verb == "novelty":
        argv += ["--hypothesis", hyp_id, "--kind", "result"]
    if verb == "inquiry":
        argv += ["--question", "has anyone measured Z?"]
    argv += ["--skip", "--reason", "r", "--search-log", str(log)]
    before = len(_evidence(run_dir))
    rc = main(argv)
    err = capsys.readouterr().err
    assert rc == 2
    assert "--search-log" in err
    assert len(_evidence(run_dir)) == before


def test_contested_search_log_requires_searched(tmp_path, capsys):
    run_dir, hyp_id = _seed(tmp_path, "cli-sl-con-note")
    log = _log(tmp_path, "log.json")
    before = len(_evidence(run_dir))
    rc = main(["contested", str(run_dir), "--hypothesis", hyp_id, "--note", "n",
               "--search-log", str(log)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "--search-log" in err
    assert len(_evidence(run_dir)) == before


# --------------------------------------------------------------------------- #
# novelty: happy path + fail-closed validation
# --------------------------------------------------------------------------- #

def test_novelty_searched_with_search_log_records_queries(tmp_path, capsys, offline):
    run_dir, hyp_id = _seed(tmp_path, "cli-sl-nov-ok")
    a = _log(tmp_path, "a.json", hypothesis_id=hyp_id, kind="method")
    b = _log(tmp_path, "b.json", searched_at="2026-10-08T06:00:00Z",
             queries=[{"index": "crossref", "query": "q three", "status": "failed",
                       "detail": "timeout"}])
    rc = main(["novelty", str(run_dir), "--hypothesis", hyp_id, "--kind", "method",
               "--searched", "10.1/x", "--outcome", "found-nothing", "--allow-no-email",
               "--search-log", str(a), str(b)])
    assert rc == 0, capsys.readouterr().err
    (decision,) = [i for i in _evidence(run_dir)
                   if i.kind is EvidenceKind.NOVELTY_DECISION]
    log = decision.provenance.search_log
    assert log is not None
    assert [q.index for q in log.queries] == ["openalex", "arxiv", "crossref"]
    assert log.searched_at == ["2026-10-08T05:12:44Z", "2026-10-08T06:00:00Z"]


@pytest.mark.parametrize("field,value", [("hypothesis_id", "hyp-other"),
                                         ("kind", "result")])
def test_novelty_search_log_mismatch_rejected_nothing_written(
        tmp_path, capsys, offline, field, value):
    run_dir, hyp_id = _seed(tmp_path, f"cli-sl-nov-mismatch-{field}")
    log = _log(tmp_path, "log.json", **{field: value})
    before = len(_evidence(run_dir))
    rc = main(["novelty", str(run_dir), "--hypothesis", hyp_id, "--kind", "method",
               "--searched", "10.1/x", "--outcome", "found-nothing", "--allow-no-email",
               "--search-log", str(log)])
    err = capsys.readouterr().err
    assert rc == 2
    assert field in err and "log.json" in err
    assert len(_evidence(run_dir)) == before
    assert offline.calls == 0


def test_novelty_invalid_search_log_rejected_before_acquisition(tmp_path, capsys, offline):
    run_dir, hyp_id = _seed(tmp_path, "cli-sl-nov-invalid")
    log = _log(tmp_path, "bad.json", queries=[])
    before = len(_evidence(run_dir))
    rc = main(["novelty", str(run_dir), "--hypothesis", hyp_id, "--kind", "result",
               "--searched", "10.1/x", "--outcome", "found-nothing", "--allow-no-email",
               "--search-log", str(log)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "bad.json" in err
    assert "Traceback" not in err
    assert len(_evidence(run_dir)) == before
    assert offline.calls == 0
    assert not (run_dir / "literature").exists() or not any(
        (run_dir / "literature").rglob("manifest.csv"))


# --------------------------------------------------------------------------- #
# the other three verbs thread the log
# --------------------------------------------------------------------------- #

def test_prior_work_and_inquiry_searched_with_search_log(tmp_path, capsys, offline):
    run_dir, _ = _seed(tmp_path, "cli-sl-pw")
    log = _log(tmp_path, "log.json")
    assert main(["prior-work", str(run_dir), "--searched", "10.1/x", "--allow-no-email",
                 "--search-log", str(log)]) == 0
    assert main(["inquiry", str(run_dir), "--question", "has anyone measured Z?",
                 "--searched", "10.1/y", "--allow-no-email",
                 "--search-log", str(log)]) == 0
    items = _evidence(run_dir)
    for kind in (EvidenceKind.PRIOR_WORK_DECISION, EvidenceKind.INQUIRY_DECISION):
        (d,) = [i for i in items if i.kind is kind]
        assert d.provenance.search_log is not None
        assert {q.index for q in d.provenance.search_log.queries} == {"openalex", "arxiv"}


def _contested_claim(run_dir: Path, spec_id: str, hyp_id: str) -> None:
    claims_dir = run_dir / "claims"
    claims_dir.mkdir(parents=True, exist_ok=True)
    claim = Claim(
        id=f"claim-{hyp_id}", spec_id=spec_id, answers=hyp_id, statement="c",
        status=ClaimStatus.CONTESTED,
        confidence=Confidence(type=ConfidenceType.GRADED, level="moderate", basis="mixed"),
        mode=HypothesisMode.CONFIRMATORY,
    )
    (claims_dir / f"claim-{hyp_id}.json").write_text(
        json.dumps(claim.model_dump(mode="json")), encoding="utf-8")


def test_contested_searched_with_search_log(tmp_path, capsys, offline):
    run_dir, hyp_id = _seed(tmp_path, "cli-sl-con")
    _contested_claim(run_dir, "cli-sl-con", hyp_id)
    log = _log(tmp_path, "log.json", hypothesis_id=hyp_id)
    assert main(["contested", str(run_dir), "--hypothesis", hyp_id,
                 "--searched", "10.1/x", "--allow-no-email",
                 "--search-log", str(log)]) == 0
    (rec,) = [i for i in _evidence(run_dir) if i.kind is EvidenceKind.CONTESTED_RECORD]
    assert rec.provenance.search_log is not None


def test_contested_search_log_hypothesis_mismatch_rejected(tmp_path, capsys, offline):
    run_dir, hyp_id = _seed(tmp_path, "cli-sl-con-mm")
    _contested_claim(run_dir, "cli-sl-con-mm", hyp_id)
    log = _log(tmp_path, "log.json", hypothesis_id="hyp-other")
    before = len(_evidence(run_dir))
    rc = main(["contested", str(run_dir), "--hypothesis", hyp_id,
               "--searched", "10.1/x", "--allow-no-email", "--search-log", str(log)])
    assert rc == 2
    assert "hypothesis_id" in capsys.readouterr().err
    assert len(_evidence(run_dir)) == before
    assert offline.calls == 0
