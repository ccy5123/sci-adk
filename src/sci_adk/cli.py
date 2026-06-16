"""
sci-adk command-line interface.

    sci-adk run <proposal.md> [-o OUTPUT] [--spec-id ID]
    sci-adk run --t1-demo [-o OUTPUT] [--spec-id ID]   # run the built-in T-1 capability
    sci-adk resolve <run-dir>                          # drive the checkpoint loop

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


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "resolve":
        return _cmd_resolve(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
