"""What ``sci-adk verify`` prints.

Found by the trial session on run SPEC-BCFKOW-001:

  - the tool-vocabulary failure said "draft.tex names the toolchain" although the gate
    scans si.tex as well (REQ-SA-204), so a leak in si.tex sent the author to the wrong
    file;
  - with stdout and stderr merged through a pipe, the stderr block "deposit INCOMPLETE"
    landed in the middle of a stdout advisory line (stdout is block-buffered on a pipe,
    stderr is not), and every stderr failure block came out before the run header;
  - the result-novelty claim of H2 printed as a second, indistinguishable
    "H2: REPRODUCED".
"""

from __future__ import annotations

import io
import sys

from sci_adk.cli import main
from sci_adk.core.claim import ClaimStatus
from sci_adk.loop.verify import VerifyOutcome
from tests.test_verify import (
    _freeze_minimal_pubreqs,
    _numeric_experiment,
    _numeric_spec,
    _seed,
    _write_paper,
)
from tests.test_verify_novelty import _experiment_with_found_nothing, _novelty_spec

_CLEAN_DRAFT = r"\label{fig:a}\ref{fig:a} The point estimate is 0.95."
_LEAKY_SI = r"\label{tab:s1} The frozen Spec; the verdicts."


def _block(text: str, header: str) -> list[str]:
    """The ``    - `` item lines printed under the line containing ``header``."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if header in line)
    items = []
    for line in lines[start + 1:]:
        if not line.startswith("    - "):
            break
        items.append(line)
    return items


# -- per-document tool vocabulary ------------------------------------------------------


def test_cli_tool_vocabulary_names_the_document_that_leaks(tmp_path, capsys):
    spec = _numeric_spec("cli-toolvocab-si", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex", _CLEAN_DRAFT)
    _write_paper(run_dir, "si.tex", _LEAKY_SI)
    _freeze_minimal_pubreqs(run_dir)

    rc = main(["verify", str(run_dir)])
    err = capsys.readouterr().err

    assert rc == 1
    assert "draft.tex names the toolchain" not in err
    assert _block(err, "tool-vocabulary FAILED") == [
        "    - si.tex: frozen spec, verdicts, Spec"
    ]


def test_cli_tool_vocabulary_lists_each_leaking_document(tmp_path, capsys):
    spec = _numeric_spec("cli-toolvocab-both", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex",
                 r"\label{fig:a}\ref{fig:a} The point estimate 0.95 is engine-derived.")
    _write_paper(run_dir, "si.tex", _LEAKY_SI)
    _freeze_minimal_pubreqs(run_dir)

    main(["verify", str(run_dir)])
    err = capsys.readouterr().err

    assert _block(err, "tool-vocabulary FAILED") == [
        "    - draft.tex: engine-derived",
        "    - si.tex: frozen spec, verdicts, Spec",
    ]


# -- one stream order ------------------------------------------------------------------


class _Merged:
    """The single byte stream a caller sees after ``2>&1`` into a pipe."""

    def __init__(self) -> None:
        self.chunks: list[str] = []

    def text(self) -> str:
        return "".join(self.chunks)


class _PipeStdout(io.TextIOBase):
    """stdout on a pipe: held in a buffer until flushed."""

    def __init__(self, merged: _Merged) -> None:
        self._merged = merged
        self._buf: list[str] = []

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        self._buf.append(s)
        return len(s)

    def flush(self) -> None:
        if self._buf:
            self._merged.chunks.append("".join(self._buf))
            self._buf = []


class _PipeStderr(io.TextIOBase):
    """stderr: reaches the merged stream at once."""

    def __init__(self, merged: _Merged) -> None:
        self._merged = merged

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        self._merged.chunks.append(s)
        return len(s)

    def flush(self) -> None:
        pass


def test_cli_verify_output_keeps_its_order_when_stdout_is_buffered(tmp_path, monkeypatch):
    spec = _numeric_spec("cli-order", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))
    _write_paper(run_dir, "draft.tex", _CLEAN_DRAFT)
    _write_paper(run_dir, "si.tex", _LEAKY_SI)   # a stderr failure block
    _freeze_minimal_pubreqs(run_dir)
    # the seeded record.tex carries no availability statement -> "deposit INCOMPLETE"

    merged = _Merged()
    stdout = _PipeStdout(merged)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", _PipeStderr(merged))
    main(["verify", str(run_dir)])
    stdout.flush()   # what the interpreter does at exit
    lines = merged.text().splitlines()

    def index(prefix: str) -> int:
        return next(i for i, line in enumerate(lines) if line.startswith(prefix))

    header = index("verified run ")
    tool = index("  tool-vocabulary FAILED")
    deposit = index("  deposit INCOMPLETE")
    assert header < tool < deposit
    # the deposit block is one whole line, not glued onto the end of another
    assert sum("deposit INCOMPLETE" in line for line in lines) == 1


def test_cli_deposit_incomplete_is_printed_with_the_advisories_on_stdout(tmp_path, capsys):
    spec = _numeric_spec("cli-deposit-stdout", value=0.9)
    run_dir = _seed(tmp_path, spec, _numeric_experiment(0.95))

    main(["verify", str(run_dir)])
    captured = capsys.readouterr()

    assert "  deposit INCOMPLETE (record-side, advisory -- not gated):" in captured.out
    assert _block(captured.out, "deposit INCOMPLETE")
    assert "deposit INCOMPLETE" not in captured.err


# -- novelty claims labelled by claim --------------------------------------------------


def test_verify_outcome_label_names_the_novelty_kind():
    common = dict(recorded_status=ClaimStatus.SUPPORTED,
                  rederived_status=ClaimStatus.SUPPORTED,
                  result="REPRODUCED", rederived_basis="b")
    assert VerifyOutcome(hypothesis_id="H2", **common).label == "H2"
    assert (VerifyOutcome(hypothesis_id="H2", novelty_kind="result", **common).label
            == "H2 (novelty, result)")
    assert (VerifyOutcome(hypothesis_id="H2", novelty_kind="method", **common).label
            == "H2 (novelty, method)")


def test_cli_labels_the_novelty_claim_apart_from_the_experiment_claim(tmp_path, capsys):
    spec = _novelty_spec("cli-novelty-label", value=0.9)
    run_dir = _seed(tmp_path, spec, _experiment_with_found_nothing(0.95))

    main(["verify", str(run_dir)])
    out = capsys.readouterr().out
    outcome_lines = [line.strip() for line in out.splitlines() if ": REPRODUCED" in line]

    assert sorted(line.split("  ")[0] for line in outcome_lines) == [
        "- hyp-n (novelty, result): REPRODUCED",
        "- hyp-n: REPRODUCED",
    ]


def test_package_verify_log_labels_the_novelty_claim(tmp_path):
    from sci_adk.render.package import _write_verify_logs

    spec = _novelty_spec("pkg-novelty-label", value=0.9)
    _seed(tmp_path, spec, _experiment_with_found_nothing(0.95))
    package_dir = tmp_path / "package"

    _write_verify_logs(tmp_path, package_dir, [spec.id])
    log = (package_dir / "06_provenance" / "verify_logs" / f"{spec.id}.txt").read_text(
        encoding="utf-8")

    assert "    - hyp-n (novelty, result): REPRODUCED " in log
    assert "    - hyp-n: REPRODUCED " in log


def test_a_novelty_claim_whose_hypothesis_left_the_spec_keeps_its_kind(tmp_path):
    # A recorded claim whose hypothesis is absent from spec.json is reported DIVERGED
    # before any re-derivation; the novelty claim must still be told apart from the
    # experiment claim of the same hypothesis.
    import json

    from sci_adk.loop.verify import verify_run

    spec = _novelty_spec("verify-novelty-orphan", value=0.9)
    run_dir = _seed(tmp_path, spec, _experiment_with_found_nothing(0.95))
    spec_path = run_dir / "spec.json"
    on_disk = json.loads(spec_path.read_text(encoding="utf-8"))
    on_disk["hypotheses"][0]["id"] = "hyp-renamed"
    on_disk["target_claims"][0]["answers"] = "hyp-renamed"
    spec_path.write_text(json.dumps(on_disk, indent=2), encoding="utf-8")

    report = verify_run(run_dir)

    assert sorted(o.label for o in report.outcomes) == ["hyp-n", "hyp-n (novelty, result)"]
    assert all(o.result == "DIVERGED" for o in report.outcomes)
