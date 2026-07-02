"""
Watch-folder scan for dropped PDFs (design/literature-acquisition.md): scan_new_pdfs
reports watch-folder PDFs NOT already in the run's literature store (content-hash dedup),
the config resolves the watch dirs (default ~/Downloads), and the `scan-literature` CLI
verb lists candidates read-only (no move, no ingest).
"""

from __future__ import annotations

from pathlib import Path

from sci_adk.search.literature_scan import file_sha256, scan_new_pdfs


def _pdf(path: Path, body: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n" + body)
    return path


def test_scan_reports_new_pdf_not_in_store(tmp_path):
    watch = tmp_path / "Downloads"
    store = tmp_path / "runs" / "s" / "literature" / "pdfs"
    _pdf(watch / "paper.pdf", b"alpha")

    new = scan_new_pdfs(store, [watch])
    assert [p.name for p in new] == ["paper.pdf"]


def test_scan_skips_already_ingested_by_content_hash(tmp_path):
    # A watch-folder PDF whose BYTES already sit in the store (renamed to a bibkey) is
    # NOT reported -- filename differs, content matches (shutil.copy2 preserves bytes).
    watch = tmp_path / "Downloads"
    store = tmp_path / "runs" / "s" / "literature" / "pdfs"
    _pdf(watch / "Niimi1986_download.pdf", b"same-bytes")
    _pdf(store / "Niimi1986.pdf", b"same-bytes")  # already ingested under its bibkey
    assert file_sha256(watch / "Niimi1986_download.pdf") == file_sha256(store / "Niimi1986.pdf")

    assert scan_new_pdfs(store, [watch]) == []


def test_scan_dedups_same_content_within_watch(tmp_path):
    watch = tmp_path / "Downloads"
    store = tmp_path / "runs" / "s" / "literature" / "pdfs"
    _pdf(watch / "a.pdf", b"dup")
    _pdf(watch / "b.pdf", b"dup")   # identical bytes -> one candidate only
    _pdf(watch / "c.pdf", b"unique")

    names = [p.name for p in scan_new_pdfs(store, [watch])]
    assert names == ["a.pdf", "c.pdf"]  # b.pdf deduped (same content as a.pdf)


def test_scan_missing_watch_dir_is_graceful(tmp_path):
    store = tmp_path / "runs" / "s" / "literature" / "pdfs"
    assert scan_new_pdfs(store, [tmp_path / "does-not-exist"]) == []


def test_config_watch_dirs_default_is_downloads(tmp_path):
    from sci_adk.config import watch_dirs
    # No config file under this root -> default ~/Downloads (expanded).
    dirs = watch_dirs(config_root=tmp_path)
    assert dirs == [Path("~/Downloads").expanduser()]


def test_config_watch_dirs_reads_literature_section(tmp_path):
    from sci_adk.config import watch_dirs
    cfg = tmp_path / "sci-adk"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.toml").write_text(
        '[literature]\nwatch_dirs = ["/mnt/c/Users/me/Downloads", "~/papers"]\n',
        encoding="utf-8",
    )
    dirs = watch_dirs(config_root=tmp_path)
    assert dirs == [Path("/mnt/c/Users/me/Downloads"), Path("~/papers").expanduser()]


def test_cli_scan_literature_lists_candidates(tmp_path, capsys):
    from sci_adk.cli import main
    from sci_adk.loop.compiler import ResearchCompiler
    from sci_adk.core.spec import (
        DecisionRule, DecisionRuleKind, Hypothesis, HypothesisMode,
        MethodPlan, RawProposal, Spec, TargetClaim,
    )

    spec = Spec(
        id="scan-cli", version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[Hypothesis(
            id="hyp-n", statement="s", mode=HypothesisMode.CONFIRMATORY,
            decision_rule=DecisionRule(kind=DecisionRuleKind.THRESHOLD,
                                       expression="point >= t => support",
                                       params={"statistic": "point", "op": ">=", "value": 0.9}))],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="hyp-n")],
    )
    ResearchCompiler(workspace_dir=tmp_path).stage_init_spec(spec=spec)
    run_dir = tmp_path / "runs" / spec.id

    watch = tmp_path / "inbox"
    _pdf(watch / "dropped.pdf", b"new-paper")

    rc = main(["scan-literature", str(run_dir), "--dir", str(watch)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "dropped.pdf" in out
    assert "1 new candidate" in out
    # read-only: the store is untouched (nothing ingested/moved).
    assert not (run_dir / "literature" / "pdfs").exists()
