"""
sci-adk command-line interface.

    sci-adk run <proposal.md> [-o OUTPUT] [--spec-id ID] [--t1-molecules H2O,CO2,CH4]

Compiles a four-pane proposal into ``runs/<spec.id>/`` (spec.json, evidence/,
claims/, paper/draft.md). The numeric path runs autonomously at zero LLM cost;
proof/qualitative hypotheses are surfaced as agent checkpoints (resolved
in-session, never via an autonomous claude -p / API call).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sci_adk.loop.compiler import ResearchCompiler, t1_molecular_experiment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sci-adk",
        description="Research compiler: a four-pane proposal -> paper + code + evidence.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="compile a proposal into runs/<spec.id>/")
    run.add_argument("proposal", help="path to a four-pane proposal (.md / .txt)")
    run.add_argument("-o", "--output", default=".",
                     help="workspace root that holds runs/ (default: cwd)")
    run.add_argument("--spec-id", default=None, help="explicit Spec id")
    run.add_argument(
        "--t1-molecules", default=None,
        help="comma-separated molecules to run the built-in T-1 Docker experiment "
             "(e.g. H2O,CO2,CH4); omit to compile without running an experiment",
    )
    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    proposal_path = Path(args.proposal)
    if not proposal_path.exists():
        print(f"error: proposal not found: {proposal_path}", file=sys.stderr)
        return 2
    proposal_text = proposal_path.read_text(encoding="utf-8")

    experiment = None
    if args.t1_molecules:
        molecules = [m.strip() for m in args.t1_molecules.split(",") if m.strip()]
        if molecules:
            experiment = t1_molecular_experiment(molecules)

    compiler = ResearchCompiler(workspace_dir=Path(args.output))
    result = compiler.compile(
        proposal_text, spec_id=args.spec_id, experiment=experiment)

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


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return _cmd_run(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
