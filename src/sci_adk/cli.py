"""
sci-adk command-line interface.

    sci-adk run <proposal.md> [-o OUTPUT] [--spec-id ID]
    sci-adk run --capability <id> [-o OUTPUT] [--spec-id ID]  # run a capability's demo
    sci-adk run --t1-demo [-o OUTPUT] [--spec-id ID]   # alias for --capability t1-molecular-godel
    sci-adk resolve <run-dir>                          # drive the checkpoint loop
    sci-adk verify <run-dir>                           # headless read-only belief audit
    sci-adk prior-work <run-dir> --searched <dois...>  # record a prior-work decision
    sci-adk prior-work <run-dir> --skip --reason "..." #   (searched or skipped)
    sci-adk novelty <run-dir> --hypothesis <id> --searched <dois...>  # novelty trigger
    sci-adk novelty <run-dir> --hypothesis <id> --skip --reason "..." #   (searched/skip)
    sci-adk contested <run-dir> --hypothesis <id> [--searched <dois...> | --note "..."]

Compiles a four-pane proposal into ``runs/<spec.id>/`` (spec.json, evidence/,
claims/, paper/draft.tex). The paper artifact is LaTeX (Overleaf default pdflatex):
when a references.bib exists it is co-located into paper/ so the folder uploads
as-is. The numeric path runs autonomously at zero LLM cost; proof/qualitative
hypotheses are surfaced as agent checkpoints (resolved in-session, never via an
autonomous claude -p / API call).

Experiment capabilities are served by the capability adapter (``sci_adk.adapter``),
NOT the kernel (design/rigor-shell-architecture.md §3.2/§3.3, F3/F4). ``--capability
<id>`` resolves an ``ExperimentFn`` provider from the adapter registry at runtime
(capability is HOW, not WHAT -- resolved outside the frozen Spec, recorded only in
Evidence provenance). With no proposal it runs that capability's built-in demo.
``--t1-demo`` is an alias for ``--capability t1-molecular-godel``: it runs the T-1
molecular Gödel-encoding capability over its designed molecule test set using the
adapter's real T-1 Spec (a numeric injectivity threshold rule), producing an
autonomous supported/refuted verdict via the DecisionEngine -- no judge needed.

``resolve`` (design/rigor-shell-architecture.md §7.1) drives the §5 turnkey
checkpoint loop over an EXISTING run dir: it recompiles the recorded run with a
``RecordedJudge`` (reading any ``verdicts/<hyp-id>.json`` the in-session agent
authored), then reports which checkpoints are still unresolved and which Claims the
recorded verdicts resolved. No LLM is invoked.

``verify`` (design/rigor-shell-architecture.md §6.2/§7.1, §8 F6) is the headless,
READ-ONLY belief audit: it re-applies the frozen ``DecisionRule`` to the RECORDED
Evidence (numeric autonomously; non-numeric via a ``RecordedJudge`` re-reading the
recorded trails + the F2 gate -- still no LLM) and reports, per recorded Claim,
REPRODUCED / DIVERGED / UNRESOLVED. It re-runs no experiment, calls no LLM/capability,
and overwrites no recorded file. It also prints the record digest (tamper-evidence).
Exit 0 iff every recorded claim is reproduced -- CI-style re-verification a third
party can run without Claude Code.
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
        "--capability", default=None, metavar="ID",
        help="select an adapter-served experiment capability by id (e.g. "
             "'t1-molecular-godel'); with no proposal, runs that capability's built-in "
             "demo Spec + options. Capability is resolved at runtime, outside the "
             "frozen Spec (it travels only in Evidence provenance)",
    )
    run.add_argument(
        "--t1-demo", action="store_true",
        help="alias for --capability t1-molecular-godel (demo mode): run the built-in "
             "T-1 molecular Gödel-encoding capability over its designed test set; "
             "yields an autonomous injectivity verdict",
    )
    run.add_argument(
        "--prose", default=None, metavar="PATH",
        help="optional JSON file mapping {abstract, introduction, discussion} -> text; "
             "agent-authored narrative injected verbatim into the LaTeX draft as "
             "LaTeX body input (author it LaTeX-safe, e.g. $\\geq$ / H$_2$O; a unicode "
             "safety net is a fallback, not a license to rely on unicode). Never "
             "LLM-generated. Omit -> structural skeleton only",
    )
    run.add_argument(
        "--figures", default=None, metavar="PATH",
        help="optional JSON file: a PaperFigures object {\"figures\": [...]} OR a bare "
             "list of FigureSpecs. Each spec names which Evidence series to plot, the "
             "plot kind (line|scatter|bar), a caption, and a stable id (-> "
             "\\label{fig:<id>}); the engine renders a LaTeX-native pgfplots figure, "
             "pulling y FROM the recorded Evidence (record fidelity). Never "
             "LLM-generated. Omit -> no figures",
    )

    resolve = sub.add_parser(
        "resolve",
        help="drive the checkpoint loop over an existing run dir (re-enter with "
             "recorded verdicts; report unresolved checkpoints + resolved claims)",
    )
    resolve.add_argument("run_dir", help="path to an existing runs/<spec.id>/ dir")

    verify = sub.add_parser(
        "verify",
        help="headless read-only belief audit: re-apply the frozen rules to the "
             "recorded Evidence + verdict trails (no re-run, no LLM); report "
             "REPRODUCED/DIVERGED/UNRESOLVED + the record digest. Exit 0 iff all "
             "recorded claims reproduce",
    )
    verify.add_argument("run_dir", help="path to an existing runs/<spec.id>/ dir")

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
    prior_work.add_argument(
        "--allow-no-email", action="store_true",
        help="searched path only: proceed with DEGRADED Open-Access acquisition when "
             "no contact email is set (default: refuse and halt). By default the "
             "searched path requires a contact email (arg/config/$UNPAYWALL_EMAIL)",
    )

    novelty = sub.add_parser(
        "novelty",
        help="record a novelty/priority discovery decision for a hypothesis (the High "
             "trigger): searched (--outcome found-nothing|found-prior-art) -> LITERATURE "
             "+ NOVELTY_DECISION, or skipped -> a recorded null. A SUPPORTED novelty "
             "claim needs a found-nothing searched decision (B-replace: non-HALT)",
    )
    novelty.add_argument("run_dir", help="path to an existing runs/<spec.id>/ dir")
    novelty.add_argument(
        "--hypothesis", required=True, metavar="ID",
        help="the hypothesis id this novelty decision is bound to",
    )
    nov_group = novelty.add_mutually_exclusive_group(required=True)
    nov_group.add_argument(
        "--searched", nargs="+", metavar="DOI",
        help="prior art WAS searched: acquire these DOIs (discovery via web_search is "
             "upstream) -> a LITERATURE item + a NOVELTY_DECISION. REQUIRES --outcome",
    )
    nov_group.add_argument(
        "--skip", action="store_true",
        help="prior art was NOT searched: record a skipped NOVELTY_DECISION null "
             "(requires --reason). NOTE: a skip leaves the novelty claim PROPOSED",
    )
    novelty.add_argument(
        "--outcome", choices=["found-nothing", "found-prior-art"], default=None,
        help="REQUIRED with --searched: found-nothing (no prior art -> the novelty claim "
             "derives SUPPORTED) | found-prior-art (prior art exists -> stays PROPOSED)",
    )
    novelty.add_argument(
        "--reason", default=None,
        help="why the prior-art search was skipped (required with --skip)",
    )
    novelty.add_argument(
        "--allow-no-email", action="store_true",
        help="searched path only: proceed with DEGRADED OA acquisition when no contact "
             "email is set (default: refuse and halt)",
    )

    contested = sub.add_parser(
        "contested",
        help="record the post-conflict literature decision for a CONTESTED hypothesis "
             "(the Medium trigger): a timestamp so papers found after the conflict stay "
             "visible. Recording only -- never gates or halts",
    )
    contested.add_argument("run_dir", help="path to an existing runs/<spec.id>/ dir")
    contested.add_argument(
        "--hypothesis", required=True, metavar="ID",
        help="the contested hypothesis id this record is bound to",
    )
    con_group = contested.add_mutually_exclusive_group(required=False)
    con_group.add_argument(
        "--searched", nargs="+", metavar="DOI",
        help="also acquire these DOIs (the searched-contested path) -> a LITERATURE "
             "item referenced by the CONTESTED_RECORD",
    )
    con_group.add_argument(
        "--note", default=None,
        help="a free-text note about the conflict / what was found (pure-record path)",
    )
    contested.add_argument(
        "--allow-no-email", action="store_true",
        help="searched path only: proceed with DEGRADED OA acquisition when no contact "
             "email is set (default: refuse and halt)",
    )

    status = sub.add_parser(
        "status",
        help="terse, read-only session-state snapshot of a run dir (recorded claim "
             "statuses + open decisions). No recompile / experiment / LLM / write / "
             "re-derivation -- cheap enough to call every turn. Exit 0 ALWAYS (it is a "
             "report, not a gate; a missing run dir -> a 'nothing recorded' report)",
    )
    status.add_argument("run_dir", help="path to a runs/<spec.id>/ dir (may not exist)")
    status.add_argument(
        "--json", action="store_true", dest="as_json",
        help="emit the StatusReport as indented JSON instead of the human view",
    )

    init_session = sub.add_parser(
        "init-session",
        help="install the research-workspace enforcement kit (Stop/UserPromptSubmit "
             "hooks + researcher persona + /research command + CLAUDE.md) into a target "
             "dir. Non-clobbering and idempotent: never overwrites the user's files, "
             "merges settings.json, and re-running is a clean no-op. Exit 0 on success "
             "(a conflict is a warning, not a failure)",
    )
    init_session.add_argument(
        "dir", help="an existing research-workspace directory to install into "
                    "(NOT the sci-adk build repo -- the two Stop gates would fight)",
    )
    init_session.add_argument(
        "--dry-run", action="store_true",
        help="compute and report every planned action but write NOTHING to disk",
    )
    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    # Capabilities live in the adapter (kernel stays domain-free). The CLI is the
    # composition root and MAY import the adapter; the kernel may not (design §3.3, F4).
    # Importing the registry registers the built-in capabilities (T-1 first).
    proposal_text = ""
    spec = None
    experiment = None

    # --t1-demo is an alias for --capability t1-molecular-godel (demo mode). Passing an
    # explicit --capability alongside --t1-demo is contradictory: reject rather than
    # silently pick one. The alias target is the adapter's own constant (imported here,
    # in the composition root) -- no duplicated magic string.
    capability_id = args.capability
    if args.t1_demo:
        from sci_adk.adapter.t1_capability import T1_CAPABILITY_ID as _t1_id

        if capability_id is not None and capability_id != _t1_id:
            print(
                f"error: --t1-demo is an alias for --capability {_t1_id}; "
                f"it conflicts with --capability {capability_id} (choose one)",
                file=sys.stderr,
            )
            return 2
        capability_id = _t1_id

    if capability_id is not None:
        from sci_adk.adapter.registry import resolve

        try:
            provider = resolve(capability_id)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2

        # Minimal scope: a selected capability runs its built-in DEMO (Spec + options),
        # i.e. the no-proposal path. Authoring an experiment FROM an arbitrary proposal
        # is the agent-authored capability path (design §3.2) -- not built here, and not
        # the same as feeding demo data to a proposal's Spec. So proposal + capability is
        # rejected rather than silently substituting demo molecules.
        if args.proposal:
            print(
                f"error: --capability {capability_id} runs the capability's built-in "
                f"demo; it cannot be combined with a proposal path yet (proposal-driven "
                f"experiment authoring is not implemented)",
                file=sys.stderr,
            )
            return 2
        if not provider.supports_demo:
            print(
                f"error: capability '{capability_id}' has no built-in demo; "
                f"nothing to run without a proposal",
                file=sys.stderr,
            )
            return 2
        spec = provider.demo_spec(args.spec_id or "t1-godel")
        experiment = provider.experiment_fn(**provider.demo_options())
    else:
        if not args.proposal:
            print(
                "error: provide a proposal path, --t1-demo, or --capability <id>",
                file=sys.stderr,
            )
            return 2
        proposal_path = Path(args.proposal)
        if not proposal_path.exists():
            print(f"error: proposal not found: {proposal_path}", file=sys.stderr)
            return 2
        proposal_text = proposal_path.read_text(encoding="utf-8")

    # Optional agent-authored prose (abstract/introduction/discussion) injected into
    # both drafts. Loaded from a JSON file -- this is input, NOT autonomous generation
    # (sci-adk never calls an LLM to write it).
    prose = None
    if args.prose:
        prose_path = Path(args.prose)
        if not prose_path.exists():
            print(f"error: prose file not found: {prose_path}", file=sys.stderr)
            return 2
        from sci_adk.render.prose import PaperProse

        try:
            prose = PaperProse.model_validate_json(prose_path.read_text(encoding="utf-8"))
        except ValueError as e:
            print(f"error: invalid prose JSON ({prose_path}): {e}", file=sys.stderr)
            return 2

    # Optional agent-authored figure specs (paper-figures Phase 1). Accepts either a
    # PaperFigures object ({"figures": [...]}) or a bare list of FigureSpecs -- both
    # normalize to a figure list. Input, NOT autonomous generation (no LLM at render
    # time; the engine pulls each y FROM the recorded Evidence).
    figures = None
    if args.figures:
        figures_path = Path(args.figures)
        if not figures_path.exists():
            print(f"error: figures file not found: {figures_path}", file=sys.stderr)
            return 2
        from sci_adk.render.figures import FigureSpec, PaperFigures

        raw = figures_path.read_text(encoding="utf-8")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"error: invalid figures JSON ({figures_path}): {e}", file=sys.stderr)
            return 2
        try:
            if isinstance(parsed, list):
                figures = [FigureSpec.model_validate(item) for item in parsed]
            else:
                figures = list(PaperFigures.model_validate(parsed).figures)
        except ValueError as e:
            print(f"error: invalid figures spec ({figures_path}): {e}", file=sys.stderr)
            return 2

    compiler = ResearchCompiler(workspace_dir=Path(args.output))
    # Evidence-validity halt (design/evidence-validity.md E3): an inadequate record
    # (e.g. synthetic data fed to an empirical claim) raises before any Claim is
    # written. Surface it as a friendly non-zero exit -- never a raw traceback and
    # never a "compiled ... supported" success line for an ungrounded result.
    from sci_adk.core.validity import ValidityHalt

    try:
        result = compiler.compile(
            proposal_text, spec_id=args.spec_id, spec=spec, experiment=experiment,
            prose=prose, figures=figures)
    except ValidityHalt as e:
        print(f"error: evidence-validity halt: {e.reason}", file=sys.stderr)
        return 2

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
    fc = result.figure_consistency
    if fc is not None and not fc.ok:
        # Non-blocking prose<->figure ref report (D4): a warning, not a gate.
        print("  figure consistency warnings (non-blocking):")
        if fc.dangling:
            print(f"    - dangling \\ref (no such figure): {', '.join(fc.dangling)}")
        if fc.orphan:
            print(f"    - orphan figure (never \\ref'd): {', '.join(fc.orphan)}")
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
    # A recompile inside the loop can raise the evidence-validity halt (E3) -- e.g. a
    # recorded run whose Evidence is inadequate for an empirical Claim. Surface it as a
    # friendly non-zero exit alongside the malformed-verdict ValueError.
    from sci_adk.core.validity import ValidityHalt

    try:
        result = run_checkpoint_loop(run_dir=run_dir, spec=spec)
    except ValidityHalt as e:
        print(f"error: evidence-validity halt: {e.reason}", file=sys.stderr)
        return 2
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


def _cmd_verify(args: argparse.Namespace) -> int:
    """Headless read-only belief audit over an existing run dir (design §6.2/§7.1, F6).

    Re-derives belief from the RECORDED run (numeric autonomously; non-numeric via a
    RecordedJudge re-reading the recorded trails -- no LLM) and reports, per recorded
    Claim, whether it REPRODUCED / DIVERGED / UNRESOLVED, plus the record digest. Exit
    0 iff every recorded claim reproduces. Nothing on disk is modified.
    """
    run_dir = Path(args.run_dir)
    spec_path = run_dir / "spec.json"
    if not spec_path.exists():
        print(f"error: no spec.json found in run dir: {run_dir}", file=sys.stderr)
        return 2

    # A recorded artifact (spec/evidence/claim/verdict) may be malformed, or two
    # hypotheses may share a rule expression; the kernel raises a clear ValueError in
    # those cases. Surface it as a friendly stderr message rather than a raw traceback
    # (a third party may be auditing a hand-edited run).
    from sci_adk.loop.verify import verify_run

    try:
        report = verify_run(run_dir)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"verified run '{report.spec_id}' -> {run_dir}")
    print(f"  record digest (sha256): {report.digest}")
    if not report.outcomes:
        print("  no recorded claims to verify")
    for o in report.outcomes:
        rederived = o.rederived_status.value if o.rederived_status is not None else "n/a"
        print(f"    - {o.hypothesis_id}: {o.result}  "
              f"(recorded={o.recorded_status.value}, re-derived={rederived})")
    if report.all_reproduced:
        print("  all recorded claims reproduced from the record")
        return 0
    print("  NOT reproduced: at least one claim DIVERGED or is UNRESOLVED "
          "(see above)", file=sys.stderr)
    return 1


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
    # By default a contact email is REQUIRED (E4): a missing one halts BEFORE any
    # acquisition (refusing the silently degraded OA run that the rice case rode past).
    # --allow-no-email is the explicit escape hatch to proceed degraded.
    from sci_adk.config import ConfigHalt

    try:
        outcome = record_prior_work_searched(
            spec, workspace, dois=args.searched, target_id=args.target_id,
            allow_no_email=args.allow_no_email)
    except ConfigHalt as e:
        # The generic config message names the env var + config file; add the verb's
        # own escape hatch so the user sees every way to proceed.
        print(f"error: {e}", file=sys.stderr)
        print("  - or pass --allow-no-email to proceed with degraded OA acquisition",
              file=sys.stderr)
        return 2
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


def _cmd_novelty(args: argparse.Namespace) -> int:
    """Record a novelty/priority discovery decision (the High trigger) into the log.

    Reads the recorded Spec (no LLM); for ``--searched`` it drives the existing acquirer
    (a LITERATURE item) and records a searched NOVELTY_DECISION, for ``--skip`` it records
    a skipped NOVELTY_DECISION null with the given reason. A skip does NOT satisfy the
    novelty gate (it is a recorded null, not a search).
    """
    run_dir = Path(args.run_dir)
    spec_path = run_dir / "spec.json"
    if not spec_path.exists():
        print(f"error: no spec.json found in run dir: {run_dir}", file=sys.stderr)
        return 2

    spec = Spec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))
    workspace = run_dir.parent.parent

    from sci_adk.loop.literature_triggers import (
        record_novelty_searched,
        record_novelty_skip,
    )

    if args.skip:
        if not args.reason or not args.reason.strip():
            print("error: --skip requires a non-empty --reason (a skipped novelty "
                  "search is a recorded null; the record must say why)", file=sys.stderr)
            return 2
        item = record_novelty_skip(
            spec, workspace, hypothesis_id=args.hypothesis, reason=args.reason)
        print(f"recorded novelty decision (skipped) for hypothesis '{args.hypothesis}' "
              f"-> {item.kind.value} evidence {item.id}")
        print(f"  reason: {args.reason.strip()}")
        print("  note: a skipped novelty search leaves the novelty claim PROPOSED")
        return 0

    # searched path: --outcome is REQUIRED with --searched (a search has an outcome).
    if not args.outcome:
        print("error: --searched requires --outcome {found-nothing|found-prior-art} "
              "(a recorded prior-art search must record what it found)", file=sys.stderr)
        return 2
    found = "nothing" if args.outcome == "found-nothing" else "something"

    # same contact-email policy as prior-work (E4).
    from sci_adk.config import ConfigHalt

    try:
        outcome = record_novelty_searched(
            spec, workspace, hypothesis_id=args.hypothesis, dois=args.searched,
            found=found, allow_no_email=args.allow_no_email)
    except ConfigHalt as e:
        print(f"error: {e}", file=sys.stderr)
        print("  - or pass --allow-no-email to proceed with degraded OA acquisition",
              file=sys.stderr)
        return 2
    ev = outcome.evidence
    outcome_str = "found_nothing" if found == "nothing" else "found_something"
    print(f"recorded novelty decision (searched: {outcome_str}) for hypothesis "
          f"'{args.hypothesis}' -> {ev.kind.value} evidence {ev.id}")
    print(f"  acquired: {len(outcome.result.succeeded)} | "
          f"failed: {len(outcome.result.failed)}")
    if found == "nothing":
        print("  note: found-nothing -> the novelty claim derives SUPPORTED on recompile")
    else:
        print("  note: found-prior-art -> the novelty claim stays PROPOSED "
              "(drop the novelty flag via a Spec amendment, F7)")
    if outcome.should_halt:
        print("  halt (human input needed):", file=sys.stderr)
        print(outcome.halt.feedback(), file=sys.stderr)
    return 0


def _cmd_contested(args: argparse.Namespace) -> int:
    """Record the post-conflict literature decision for a CONTESTED hypothesis.

    Recording only -- never gates or halts. ``--searched`` also acquires DOIs (same
    email policy as the other searched paths); ``--note`` is the pure-record path.
    """
    run_dir = Path(args.run_dir)
    spec_path = run_dir / "spec.json"
    if not spec_path.exists():
        print(f"error: no spec.json found in run dir: {run_dir}", file=sys.stderr)
        return 2

    spec = Spec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))
    workspace = run_dir.parent.parent

    from sci_adk.loop.literature_triggers import record_contested

    # The searched path uses the polite pool, so it honors the contact-email policy.
    from sci_adk.config import ConfigHalt

    try:
        item = record_contested(
            spec, workspace, hypothesis_id=args.hypothesis,
            reason_or_note=args.note or "", dois=args.searched,
            allow_no_email=args.allow_no_email)
    except ConfigHalt as e:
        print(f"error: {e}", file=sys.stderr)
        print("  - or pass --allow-no-email to proceed with degraded OA acquisition",
              file=sys.stderr)
        return 2
    print(f"recorded contested decision for hypothesis '{args.hypothesis}' "
          f"-> {item.kind.value} evidence {item.id}")
    if args.searched:
        print(f"  acquired DOIs: {len(args.searched)}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    """Print a terse, read-only session-state snapshot of a run dir (design §6 D1).

    Reports the RECORDED claim statuses + open decisions (prior-work / novelty /
    contested / checkpoints awaiting a verdict). It re-derives nothing (that is
    ``verify``'s job), runs no experiment, calls no LLM, and writes nothing. Exit 0
    ALWAYS -- it is a report consumed every turn by the re-anchor hook, not a gate; a
    nonexistent run dir yields a graceful "nothing recorded" report rather than an error.
    """
    from sci_adk.loop.status import render_status_text, session_status

    report = session_status(Path(args.run_dir))
    if args.as_json:
        print(report.model_dump_json(indent=2))
    else:
        print(render_status_text(report))
    return 0


def _cmd_init_session(args: argparse.Namespace) -> int:
    """Install the research-workspace enforcement kit into a target dir (D3).

    Calls :func:`sci_adk.init_session.install_session`, prints the structured
    report, and picks the exit code: 0 on success (including when everything was
    already current or only conflicts were reported -- a conflict is a *warning*,
    not a failure), non-zero only on a hard error (target dir missing / not a dir,
    or the shipped templates cannot be located). The installer is imported lazily
    so its import cost (and the templates lookup) is paid only when this verb runs.
    """
    from sci_adk.init_session import install_session

    target = Path(args.dir)
    try:
        report = install_session(target, dry_run=args.dry_run)
    except NotADirectoryError as e:
        # missing / not-a-dir target, OR a build-harness target the guard refused.
        print(f"error: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        # the shipped templates are missing (non-editable install -- a follow-up).
        print(f"error: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        # a malformed existing settings.json (clean message, no traceback).
        print(f"error: {e}", file=sys.stderr)
        return 2

    head = "DRY RUN (nothing written) -- " if report.dry_run else ""
    print(f"{head}init-session -> {target}")
    for line in report.lines():
        print(line)
    if report.conflicts:
        print(f"  ({len(report.conflicts)} conflict(s) above are warnings, not "
              f"failures -- resolve them manually; the install still succeeded)")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "resolve":
        return _cmd_resolve(args)
    if args.command == "verify":
        return _cmd_verify(args)
    if args.command == "prior-work":
        return _cmd_prior_work(args)
    if args.command == "novelty":
        return _cmd_novelty(args)
    if args.command == "contested":
        return _cmd_contested(args)
    if args.command == "status":
        return _cmd_status(args)
    if args.command == "init-session":
        return _cmd_init_session(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
