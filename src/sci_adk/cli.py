"""
sci-adk command-line interface.

    sci-adk run <proposal.md> [-o OUTPUT] [--spec-id ID]
    sci-adk run --t1-demo [-o OUTPUT] [--spec-id ID]   # run the built-in T-1 capability
    sci-adk resolve <run-dir>                          # drive the checkpoint loop
    sci-adk prior-work <run-dir> --searched <dois...>  # record a prior-work decision
    sci-adk prior-work <run-dir> --skip --reason "..." #   (searched or skipped)

Compiles a four-pane proposal into ``runs/<spec.id>/`` (spec.json, evidence/,
claims/, paper/draft.md). The numeric path runs autonomously at zero LLM cost;
proof/qualitative hypotheses are surfaced as agent checkpoints (resolved
in-session, never via an autonomous claude -p / API call).

The T-1 molecular Gödel-encoding experiment is provided by the capability adapter
(``sci_adk.adapter``), not the kernel (design/rigor-shell-architecture.md §3.3).
``--t1-demo`` runs that capability over its designed molecule test set using the
adapter's real T-1 Spec (a numeric injectivity threshold rule), producing an
autonomous supported/refuted verdict via the DecisionEngine -- no judge needed.

``resolve`` (design/rigor-shell-architecture.md §7.1) drives the §5 turnkey
checkpoint loop over an EXISTING run dir: it recompiles the recorded run with a
``RecordedJudge`` (reading any ``verdicts/<hyp-id>.json`` the in-session agent
authored), then reports which checkpoints are still unresolved and which Claims the
recorded verdicts resolved. No LLM is invoked.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sci_adk.core.spec import Spec
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.loop.compiler import ResearchCompiler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sci-adk",
        description="Research compiler: a four-pane proposal -> paper + code + evidence.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="compile a proposal into runs/<spec.id>/")
    run.add_argument("proposal", nargs="?", default=None,
                     help="path to a four-pane proposal (.md / .txt); "
                          "omit with --t1-demo to use the built-in T-1 Spec")
    run.add_argument("-o", "--output", default=".",
                     help="workspace root that holds runs/ (default: cwd)")
    run.add_argument("--spec-id", default=None, help="explicit Spec id")
    run.add_argument(
        "--t1-demo", action="store_true",
        help="run the built-in T-1 molecular Gödel-encoding capability (adapter) "
             "over its designed test set; yields an autonomous injectivity verdict",
    )

    resolve = sub.add_parser(
        "resolve",
        help="drive the checkpoint loop over an existing run dir (re-enter with "
             "recorded verdicts; report unresolved checkpoints + resolved claims)",
    )
    resolve.add_argument("run_dir", help="path to an existing runs/<spec.id>/ dir")

    prior_work = sub.add_parser(
        "prior-work",
        help="record the Spec-time prior-work decision into the Evidence log "
             "(searched -> LITERATURE, or skipped -> a recorded null)",
    )
    prior_work.add_argument("run_dir", help="path to an existing runs/<spec.id>/ dir")
    group = prior_work.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--searched", nargs="+", metavar="DOI",
        help="prior work WAS searched: acquire these DOIs (discovery via the agent's "
             "web_search is upstream) -> a LITERATURE EvidenceItem",
    )
    group.add_argument(
        "--skip", action="store_true",
        help="prior work was NOT searched: record a PRIOR_WORK_DECISION null "
             "(requires --reason)",
    )
    prior_work.add_argument(
        "--reason", default=None,
        help="why prior-art search was skipped (required with --skip)",
    )
    prior_work.add_argument(
        "--target-id", default=None,
        help="optional Hypothesis/Claim id the survey relates to (searched path)",
    )
    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    # The T-1 capability lives in the adapter (kernel stays domain-free). Imported
    # here, in the CLI, so the kernel never depends on it.
    proposal_text = ""
    spec = None
    experiment = None

    if args.t1_demo:
        from sci_adk.adapter.t1_capability import (
            build_t1_demo_molecules,
            build_t1_spec,
            t1_experiment,
        )

        spec = build_t1_spec(spec_id=args.spec_id or "t1-godel")
        experiment = t1_experiment(build_t1_demo_molecules())
    else:
        if not args.proposal:
            print("error: provide a proposal path or use --t1-demo", file=sys.stderr)
            return 2
        proposal_path = Path(args.proposal)
        if not proposal_path.exists():
            print(f"error: proposal not found: {proposal_path}", file=sys.stderr)
            return 2
        proposal_text = proposal_path.read_text(encoding="utf-8")

    compiler = ResearchCompiler(workspace_dir=Path(args.output))
    result = compiler.compile(
        proposal_text, spec_id=args.spec_id, spec=spec, experiment=experiment)

    print(f"compiled Spec '{result.spec.id}' -> {result.run_dir}")
    print(f"  evidence: {len(result.evidence)} | claims: {len(result.claims)}")
    for claim in result.claims:
        status = claim.status.value
        print(f"    - {claim.answers}: {status}  ({claim.confidence.basis[:70]})")
    if result.needs_agent:
        print(f"  agent checkpoints ({len(result.checkpoints)}) "
              f"-> {result.run_dir / 'checkpoints.md'}:")
        for c in result.checkpoints:
            print(f"    - {c.hypothesis_id} ({c.kind}): {c.expression[:60]}")
    print(f"  paper draft: {result.paper_path}")
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    """Drive the checkpoint loop over an existing run dir (design §7.1)."""
    run_dir = Path(args.run_dir)
    spec_path = run_dir / "spec.json"
    if not spec_path.exists():
        print(f"error: no spec.json found in run dir: {run_dir}", file=sys.stderr)
        return 2

    spec = Spec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))
    # No experiment is passed: resolve operates on the RECORDED run, reusing the
    # Evidence already on disk (F5). The loop injects a RecordedJudge so any
    # agent-authored verdicts/<hyp-id>.json move the Claims.
    #
    # A hand-authored verdict file may be malformed (truncated / typo / wrong schema)
    # or two hypotheses may share a rule expression; RecordedJudge raises a clear
    # ValueError in those cases. Surface it as a friendly stderr message naming the
    # offending file rather than a raw traceback (a third party authors these files).
    try:
        result = run_checkpoint_loop(run_dir=run_dir, spec=spec)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"resolved run '{result.spec.id}' ({result.iterations} iteration(s)) "
          f"-> {result.run_dir}")
    print(f"  claims: {len(result.claims)}")
    for claim in result.claims:
        print(f"    - {claim.answers}: {claim.status.value}  "
              f"({claim.confidence.basis[:70]})")
    if result.unresolved:
        print(f"  unresolved checkpoints ({len(result.unresolved)}) -- author "
              f"verdicts/<hyp-id>.json for each, then resolve again:")
        for hyp_id in result.unresolved:
            print(f"    - {hyp_id}")
    else:
        print("  all checkpoints resolved")
    return 0


def _cmd_prior_work(args: argparse.Namespace) -> int:
    """Record the Spec-time prior-work decision into the single Evidence log.

    Reads the recorded Spec (no LLM); for ``--searched`` it drives the existing
    acquirer (a LITERATURE item), for ``--skip`` it records a PRIOR_WORK_DECISION
    null with the given reason. Either closes the prior_work checkpoint.
    """
    run_dir = Path(args.run_dir)
    spec_path = run_dir / "spec.json"
    if not spec_path.exists():
        print(f"error: no spec.json found in run dir: {run_dir}", file=sys.stderr)
        return 2

    spec = Spec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))
    # workspace root holds runs/ (run_dir is <workspace>/runs/<spec.id>).
    workspace = run_dir.parent.parent

    # Imported here so the kernel CLI stays thin and the import cost is paid only
    # when this verb runs.
    from sci_adk.loop.prior_work import (
        record_prior_work_searched,
        record_prior_work_skip,
    )

    if args.skip:
        if not args.reason or not args.reason.strip():
            print("error: --skip requires a non-empty --reason (a skipped "
                  "prior-work search is a recorded null; the record must say why)",
                  file=sys.stderr)
            return 2
        item = record_prior_work_skip(spec, workspace, reason=args.reason)
        print(f"recorded prior-work decision (skipped) for Spec '{spec.id}' "
              f"-> {item.kind.value} evidence {item.id}")
        print(f"  reason: {args.reason.strip()}")
        return 0

    # searched path: discovery (DOIs) is upstream; acquire + record LITERATURE.
    outcome = record_prior_work_searched(
        spec, workspace, dois=args.searched, target_id=args.target_id)
    ev = outcome.evidence
    print(f"recorded prior-work decision (searched) for Spec '{spec.id}' "
          f"-> {ev.kind.value} evidence {ev.id}")
    print(f"  acquired: {len(outcome.result.succeeded)} | "
          f"failed: {len(outcome.result.failed)}")
    if outcome.should_halt:
        # Some DOIs had no OA PDF: surface the halt feedback (the orchestrator would
        # present this to the human). The decision is still recorded.
        print("  halt (human input needed):", file=sys.stderr)
        print(outcome.halt.feedback(), file=sys.stderr)
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "resolve":
        return _cmd_resolve(args)
    if args.command == "prior-work":
        return _cmd_prior_work(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
