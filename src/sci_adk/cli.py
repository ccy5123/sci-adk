"""
sci-adk command-line interface.

    sci-adk run <proposal.md> [-o OUTPUT] [--spec-id ID]
    sci-adk run --capability <id> [-o OUTPUT] [--spec-id ID]  # run a capability's demo
    sci-adk run --t1-demo [-o OUTPUT] [--spec-id ID]   # alias for --capability t1-molecular-godel
    sci-adk resolve <run-dir>                          # drive the checkpoint loop
    sci-adk verify <run-dir>                           # headless read-only belief audit
    sci-adk prior-work <run-dir> --searched <dois...>  # record a prior-work decision
    sci-adk prior-work <run-dir> --skip --reason "..." #   (searched or skipped)
    sci-adk novelty <run-dir> --hypothesis <id> --kind {result|method} --searched <dois...>
    sci-adk novelty <run-dir> --hypothesis <id> --kind {result|method} --skip --reason "..."
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
REPRODUCED / DIVERGED / UNRESOLVED. It ALSO re-checks the rendered paper's internal
``\\ref``<->``\\label`` integrity for ``paper/draft.tex`` and ``paper/si.tex`` (each
WITHIN itself; the cross-DOCUMENT main<->SI ref is deferred) -- a Phase-3 HARD gate
(design/paper-figures-and-si.md D4). It re-runs no experiment, calls no LLM/capability,
reads the ``.tex`` read-only, and overwrites no recorded file. It also prints the
record digest (tamper-evidence). Exit 0 iff every recorded claim reproduces AND the
paper is internally consistent -- CI-style re-verification a third party can run
without Claude Code.
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path

from sci_adk.core.spec import Spec
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.loop.compiler import ResearchCompiler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sci-adk",
        description="Research compiler: a four-pane proposal -> paper + code + evidence.",
    )
    try:
        _v = _pkg_version("sci-adk")
    except PackageNotFoundError:  # running from source without an install
        _v = "unknown"
    parser.add_argument("--version", action="version", version=f"sci-adk {_v}")
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
        "--si-prose", default=None, metavar="PATH",
        help="optional JSON file mapping {overview, notes} -> text; agent-authored "
             "narrative WRAPPING the Supporting Information record dump (overview before "
             "the Evidence record, notes after Record integrity) as LaTeX body input "
             "(author it LaTeX-safe, e.g. $\\geq$ / H$_2$O; a unicode safety net is a "
             "fallback, not a license to rely on unicode). The no-authoring record dump "
             "is the spine. Never LLM-generated. Omit -> record dump only",
    )
    run.add_argument(
        "--figures", default=None, metavar="PATH",
        help="optional JSON file: a PaperFigures object {\"figures\": [...]} OR a bare "
             "list of figure specs (native or image). A NATIVE spec names which Evidence "
             "series to plot, the plot kind (line|scatter|bar), a caption, and a stable "
             "id (-> \\label{fig:<id>}); the engine renders a LaTeX-native pgfplots "
             "figure, pulling y FROM the recorded Evidence (record fidelity). An IMAGE "
             "spec ({\"kind\":\"image\",...}) names a caption, id, and a source image "
             "path (an image the experiment/agent already produced with whatever tool "
             "fits its domain) the compiler co-locates into paper/figures/fig<N>. Never "
             "LLM-generated. Omit -> no figures",
    )
    run.add_argument(
        "--no-strict-science", dest="strict_science", action="store_false",
        default=True,
        help="disable the science-guard verdict-gate HALTS (design/science-guards.md: "
             "analyticity / test-power / falsifiability). A real research run is STRICT by "
             "default -- a formal+threshold hypothesis cannot be stamped SUPPORTED without a "
             "falsifying negative control on its declared discriminating cases. Pass this to "
             "run the plumbing leniently (the guards still surface their findings at the spec "
             "gate and in verify; only the HALT is suppressed)",
    )

    # -- Step 2: the 6 standalone CLI verbs (design/sci-adk-as-moai.md §4.6). They
    # decompose `run` into stage verbs for worker fan-out; `run` stays the chained
    # wrapper. Each verb is a thin wrapper over one ResearchCompiler stage function.
    _add_verb_parsers(sub)

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
    verify.add_argument(
        "--strict-science", dest="strict_science", action="store_true",
        default=False,
        help="ALSO re-apply the science-guard verdict gates (design/science-guards.md "
             "G1/G2/G3) read-only -- tamper-evidence: a recorded SUPPORTED formal+threshold "
             "claim whose falsifying negative control was deleted no longer re-derives "
             "(DIVERGED). Opt-in (default off) so a plain audit re-derives belief exactly "
             "as recorded",
    )

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
        help="record a novelty/priority discovery decision for one {hypothesis, kind} "
             "(the High trigger, 2-kind: --kind result|method): searched (--outcome "
             "found-nothing|found-prior-art) -> LITERATURE + NOVELTY_DECISION, or "
             "skipped -> a recorded null. A SUPPORTED kind novelty claim needs a "
             "found-nothing searched decision of THAT kind (B-replace: non-HALT)",
    )
    novelty.add_argument("run_dir", help="path to an existing runs/<spec.id>/ dir")
    novelty.add_argument(
        "--hypothesis", required=True, metavar="ID",
        help="the hypothesis id this novelty decision is bound to",
    )
    novelty.add_argument(
        "--kind", required=True, choices=["result", "method"],
        help="REQUIRED: which novelty axis this decision serves -- result (no prior work "
             "established the hypothesis's RESULT) or method (no prior work used its "
             "METHOD). The two axes are independent; a {hyp, kind} decision derives only "
             "that kind's claim-novelty-{kind}-<hyp>",
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
             "hooks + science-orchestrator persona + CLAUDE.md) into a target "
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


def _add_verb_parsers(sub) -> None:
    """Register the 6 standalone Step-2 verbs (design/sci-adk-as-moai.md §4.6).

    Each verb is a thin CLI wrapper over one ``ResearchCompiler`` stage function. The
    options that OVERLAP ``run`` (capability selection, ``--prose`` / ``--si-prose`` /
    ``--figures``) keep identical surface + help so a worker that knows ``run`` knows the
    verbs.
    """
    # init-spec: author + freeze a Spec into runs/<id>/ (spec.json + prior-work checkpoint).
    init_spec = sub.add_parser(
        "init-spec",
        help="author + freeze a Spec from a proposal/capability into runs/<spec.id>/ "
             "(writes spec.json + the Spec-time prior-work checkpoint). The first stage "
             "of `run`",
    )
    init_spec.add_argument(
        "proposal", nargs="?", default=None,
        help="path to a four-pane proposal (.md/.txt); omit with --t1-demo/--capability "
             "to use a capability's built-in demo Spec",
    )
    init_spec.add_argument(
        "-o", "--output", default=".",
        help="workspace root that holds runs/ (default: cwd)",
    )
    init_spec.add_argument("--spec-id", default=None, help="explicit Spec id")
    init_spec.add_argument(
        "--capability", default=None, metavar="ID",
        help="select an adapter-served capability by id; with no proposal, uses that "
             "capability's built-in demo Spec (capability travels only in Evidence "
             "provenance, never the frozen Spec)",
    )
    init_spec.add_argument(
        "--t1-demo", action="store_true",
        help="alias for --capability t1-molecular-godel (demo mode): freeze the built-in "
             "T-1 Spec",
    )

    # pubreqs: freeze the F1 publishing-requirements contract into runs/<id>/pubreqs.json.
    pubreqs = sub.add_parser(
        "pubreqs",
        help="freeze the publishing-requirements contract (F1) into "
             "runs/<id>/pubreqs.json with its tamper-evidence digest. The umbrella "
             "`verify` gate (paper_requirements_clean) checks the rendered paper against it",
    )
    pubreqs_sub = pubreqs.add_subparsers(dest="pubreqs_command", required=True)
    pubreqs_freeze = pubreqs_sub.add_parser(
        "freeze",
        help="freeze pubreqs.json for an existing run dir (mirrors init-spec): write the "
             "FROZEN publishing contract + its digest beside spec.json (NOT inside paper/, "
             "so render never clobbers it)",
    )
    pubreqs_freeze.add_argument(
        "run_dir", help="path to an existing runs/<spec.id>/ dir (must hold spec.json)"
    )
    pubreqs_freeze.add_argument(
        "--defaults", action="store_true",
        help="use the proposed defaults (IMRaD sections, font policy on, image_min_dpi 300, "
             "reproduction bundle on); the elicitation fast-path",
    )
    pubreqs_freeze.add_argument(
        "--venue", default=None, help="free-text venue label (arXiv/JOSS/journal)"
    )
    pubreqs_freeze.add_argument(
        "--required-section", action="append", default=None, metavar="NAME",
        dest="required_sections",
        help="a section that MUST be present in draft.tex (repeatable). With --defaults, "
             "appends to the IMRaD set; without, replaces it (default: none)",
    )
    pubreqs_freeze.add_argument(
        "--no-font-policy", dest="figure_font_policy", action="store_false",
        default=True, help="disable the F2 figure font policy gate (default on)",
    )
    pubreqs_freeze.add_argument(
        "--image-min-dpi", type=int, default=None, metavar="DPI",
        help="raster figure minimum effective DPI (default 300 with --defaults; omit to "
             "disable the DPI gate)",
    )
    pubreqs_freeze.add_argument(
        "--no-image-dpi", dest="no_image_dpi", action="store_true",
        help="explicitly disable the image DPI gate even under --defaults",
    )
    pubreqs_freeze.add_argument(
        "--reference-style", default=None, metavar="STYLE",
        help="declared bib style checked wired in draft.tex (e.g. plainnat / natbib)",
    )
    pubreqs_freeze.add_argument(
        "--max-pages", type=int, default=None, metavar="N",
        help="ADVISORY page limit (surfaced, never gated -- no page count without a compile)",
    )
    pubreqs_freeze.add_argument(
        "--max-words", type=int, default=None, metavar="N",
        help="deterministic word-count ceiling over the rendered prose (omit to disable)",
    )
    pubreqs_freeze.add_argument(
        "--no-repro-bundle", dest="reproduction_bundle", action="store_false",
        default=True, help="disable the F3 reproduction-bundle gate (default on)",
    )
    pubreqs_freeze.add_argument(
        "--advisory", action="append", default=None, metavar="TEXT",
        help="a free-form advisory condition surfaced in verify but NEVER gated (repeatable)",
    )

    # pkgreqs: freeze the workspace-level PackageReqs contract into <ws>/pkgreqs.json.
    pkgreqs = sub.add_parser(
        "pkgreqs",
        help="freeze the workspace package-requirements contract (design/near-submission-"
             "package.md §2) into <ws>/pkgreqs.json with its tamper-evidence digest. The "
             "umbrella `package`/`verify <ws>` gate (package_requirements_clean) checks the "
             "assembled package against it",
    )
    pkgreqs_sub = pkgreqs.add_subparsers(dest="pkgreqs_command", required=True)
    pkgreqs_freeze = pkgreqs_sub.add_parser(
        "freeze",
        help="freeze pkgreqs.json at the WORKSPACE ROOT (mirrors pubreqs freeze): the FROZEN "
             "package contract + its digest beside runs/ (NOT inside the regenerated package/, "
             "so `package` never clobbers it)",
    )
    pkgreqs_freeze.add_argument(
        "workspace", help="path to a workspace root holding runs/ (pkgreqs.json is written here)"
    )
    pkgreqs_freeze.add_argument(
        "--defaults", action="store_true",
        help="use the proposed defaults (IMRaD required sections); the elicitation fast-path",
    )
    pkgreqs_freeze.add_argument(
        "--venue", default=None, help="free-text venue label (reuses PubReqs.venue semantics)"
    )
    pkgreqs_freeze.add_argument(
        "--required-section", action="append", default=None, metavar="NAME",
        dest="required_sections",
        help="a section that MUST be present in main.tex (repeatable). With --defaults, "
             "appends to the IMRaD set; without, replaces it (default: none)",
    )
    pkgreqs_freeze.add_argument(
        "--no-font-policy", dest="figure_font_policy", action="store_false",
        help="disable the F2 figure font-policy check (default on; mirrors pubreqs freeze)",
    )
    pkgreqs_freeze.add_argument(
        "--image-min-dpi", type=int, default=None, metavar="N",
        help="raster figure minimum effective DPI (default 300 with --defaults; omit to "
             "leave the DPI gate off without --defaults; mirrors pubreqs freeze)",
    )
    pkgreqs_freeze.add_argument(
        "--no-image-dpi", dest="no_image_dpi", action="store_true",
        help="explicitly disable the image DPI gate even under --defaults",
    )
    pkgreqs_freeze.add_argument(
        "--reference-style", default=None, metavar="STYLE",
        help="declared bib style checked wired in main.tex (e.g. plainnat / natbib)",
    )
    pkgreqs_freeze.add_argument(
        "--abstract-max-words", type=int, default=None, metavar="N",
        help="venue abstract word limit (e.g. 300); omit to disable the abstract gate",
    )
    pkgreqs_freeze.add_argument(
        "--body-word-min", type=int, default=None, metavar="N",
        help="ADVISORY body word-range minimum (with --body-word-max; surfaced, never gated)",
    )
    pkgreqs_freeze.add_argument(
        "--body-word-max", type=int, default=None, metavar="N",
        help="ADVISORY body word-range maximum (with --body-word-min; surfaced, never gated)",
    )
    pkgreqs_freeze.add_argument(
        "--run", action="append", default=None, metavar="ID", dest="runs",
        help="restrict the package to these run ids (repeatable); omit to synthesize ALL runs",
    )
    pkgreqs_freeze.add_argument(
        "--advisory", action="append", default=None, metavar="TEXT",
        help="a free-form advisory condition surfaced in verify but NEVER gated (repeatable)",
    )

    # package: assemble the workspace package, then run the package_requirements_clean gate.
    package = sub.add_parser(
        "package",
        help="assemble the workspace near-submission package (the 6-folder package/ from ALL "
             "runs) then run the package_requirements_clean gate (design/near-submission-"
             "package.md §C). Deterministic + read-only gate, no LLM. Exit 0 iff every declared "
             "package requirement is met",
    )
    package.add_argument(
        "workspace", help="path to a workspace root holding runs/ (and optionally pkgreqs.json)"
    )
    package.add_argument(
        "--no-assemble", dest="assemble", action="store_false", default=True,
        help="skip the assembly step and only run the gate over the existing package/ "
             "(verify-only over a previously assembled package)",
    )

    # amend-spec: apply Spec.amend(rationale) + write the checkpoint receipt.
    amend_spec = sub.add_parser(
        "amend-spec",
        help="amend the run's recorded Spec (version+1, S5) and record a human-approved "
             "amendment checkpoint receipt. Wraps Spec.amend -- no new semantics",
    )
    amend_spec.add_argument("run_dir", help="path to an existing runs/<spec.id>/ dir")
    amend_spec.add_argument(
        "--rationale", required=True,
        help="REQUIRED non-empty rationale for the amendment (S5: a Spec change is never "
             "silent; the record must say why)",
    )

    # execute: run the Spec's experiment into Evidence (capability selection like run).
    execute = sub.add_parser(
        "execute",
        help="execute the Spec's experiment into Evidence for an existing run dir "
             "(resolves a capability like `run`). Honors F5 reuse: a second execute over "
             "a populated run replays the recorded Evidence rather than re-running",
    )
    execute.add_argument("run_dir", help="path to an existing runs/<spec.id>/ dir")
    execute.add_argument(
        "--capability", default=None, metavar="ID",
        help="select the adapter-served capability whose demo experiment to run "
             "(must match the capability the Spec was authored for)",
    )
    execute.add_argument(
        "--t1-demo", action="store_true",
        help="alias for --capability t1-molecular-godel (demo mode)",
    )
    execute.add_argument(
        "--force", action="store_true",
        help="re-run the experiment even if Evidence already exists (F5: appends, never "
             "overwrites the append-only log)",
    )

    # append-evidence: append one typed EvidenceItem from a JSON file.
    append_ev = sub.add_parser(
        "append-evidence",
        help="append one typed EvidenceItem (from a JSON file) to the run's append-only "
             "Evidence log (E1). The single-item complement to `execute`",
    )
    append_ev.add_argument("run_dir", help="path to an existing runs/<spec.id>/ dir")
    append_ev.add_argument(
        "--evidence", required=True, metavar="PATH",
        help="path to a JSON file holding one EvidenceItem (its bears_on[] carries the "
             "bearing on the hypotheses)",
    )
    append_ev.add_argument(
        "--spec-digest", default=None, metavar="SHA256",
        help="the frozen Spec digest from the worker's [FROZEN SPEC REFERENCE] (§6.1); "
             "when passed, it must match runs/<id>/spec.json or the verb fails (exit 2) "
             "without writing. Lenient when omitted (no check)",
    )

    # derive-claim: apply each DecisionRule to the recorded Evidence -> Claims.
    derive_claim = sub.add_parser(
        "derive-claim",
        help="apply each hypothesis's frozen DecisionRule to the recorded Evidence -> "
             "Claims (and surface the recording-type checkpoints). Reads spec + evidence "
             "from the run dir; persists claims/",
    )
    derive_claim.add_argument("run_dir", help="path to an existing runs/<spec.id>/ dir")
    derive_claim.add_argument(
        "--no-strict-science", dest="strict_science", action="store_false",
        default=True,
        help="disable the science-guard verdict-gate HALTS (strict by default -- see "
             "`sci-adk run --no-strict-science`)",
    )
    derive_claim.add_argument(
        "--spec-digest", default=None, metavar="SHA256",
        help="the frozen Spec digest from the worker's [FROZEN SPEC REFERENCE] (§6.1); "
             "when passed, it must match runs/<id>/spec.json or the verb fails (exit 2) "
             "without deriving. Lenient when omitted (no check)",
    )

    # render: compile the paper/ artifacts from the recorded spec/evidence/claims.
    render = sub.add_parser(
        "render",
        help="render the paper/ artifacts (draft.tex + si.tex + figures) from the "
             "recorded spec/evidence/claims. The final stage of `run`",
    )
    render.add_argument("run_dir", help="path to an existing runs/<spec.id>/ dir")
    render.add_argument(
        "--prose", default=None, metavar="PATH",
        help="optional JSON file mapping {abstract, introduction, discussion} -> text; "
             "agent-authored narrative injected verbatim into the LaTeX draft (never "
             "LLM-generated). Same as `run --prose`",
    )
    render.add_argument(
        "--si-prose", default=None, metavar="PATH",
        help="optional JSON file mapping {overview, notes} -> text wrapping the SI record "
             "dump (never LLM-generated). Same as `run --si-prose`",
    )
    render.add_argument(
        "--figures", default=None, metavar="PATH",
        help="optional JSON file: a PaperFigures object or a bare list of figure specs "
             "(native or image). Same as `run --figures`",
    )


class _CliError(Exception):
    """A friendly CLI error carrying its intended exit code (2 = usage/input error).

    Lets the shared option loaders signal a user-facing failure without each returning
    a sentinel; the verb handlers catch it, print ``message`` to stderr, and return
    ``exit_code``. This keeps the loaders reusable across ``run`` and the Step-2 verbs.
    """

    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


def _resolve_capability_selection(args: argparse.Namespace):
    """Resolve (spec, experiment, proposal_text) from --capability / --t1-demo / proposal.

    The shared capability-selection logic used by BOTH ``run`` and ``init-spec`` (and the
    experiment half by ``execute``). Capabilities live in the adapter (kernel stays
    domain-free); the CLI is the composition root and MAY import the adapter (design §3.3,
    F4). Importing the registry registers the built-in capabilities (T-1 first).

    Returns ``(spec, experiment, proposal_text)`` where ``spec``/``experiment`` are None on
    the proposal path. Raises :class:`_CliError` on any usage error (unknown capability,
    proposal+capability combo, missing proposal, missing file).
    """
    proposal_text = ""
    spec = None
    experiment = None

    # --t1-demo is an alias for --capability t1-molecular-godel (demo mode). Passing an
    # explicit --capability alongside --t1-demo is contradictory: reject rather than
    # silently pick one. The alias target is the adapter's own constant (imported here,
    # in the composition root) -- no duplicated magic string.
    capability_id = args.capability
    if getattr(args, "t1_demo", False):
        from sci_adk.adapter.t1_capability import T1_CAPABILITY_ID as _t1_id

        if capability_id is not None and capability_id != _t1_id:
            raise _CliError(
                f"--t1-demo is an alias for --capability {_t1_id}; "
                f"it conflicts with --capability {capability_id} (choose one)"
            )
        capability_id = _t1_id

    proposal = getattr(args, "proposal", None)
    if capability_id is not None:
        from sci_adk.adapter.registry import resolve

        try:
            provider = resolve(capability_id)
        except ValueError as e:
            raise _CliError(str(e))

        # Minimal scope: a selected capability runs its built-in DEMO (Spec + options),
        # i.e. the no-proposal path. Authoring an experiment FROM an arbitrary proposal
        # is the agent-authored capability path (design §3.2) -- not built here, and not
        # the same as feeding demo data to a proposal's Spec. So proposal + capability is
        # rejected rather than silently substituting demo molecules.
        if proposal:
            raise _CliError(
                f"--capability {capability_id} runs the capability's built-in "
                f"demo; it cannot be combined with a proposal path yet (proposal-driven "
                f"experiment authoring is not implemented)"
            )
        if not provider.supports_demo:
            raise _CliError(
                f"capability '{capability_id}' has no built-in demo; "
                f"nothing to run without a proposal"
            )
        spec = provider.demo_spec(getattr(args, "spec_id", None) or "t1-godel")
        experiment = provider.experiment_fn(**provider.demo_options())
    else:
        if not proposal:
            raise _CliError(
                "provide a proposal path, --t1-demo, or --capability <id>"
            )
        proposal_path = Path(proposal)
        if not proposal_path.exists():
            raise _CliError(f"proposal not found: {proposal_path}")
        proposal_text = proposal_path.read_text(encoding="utf-8")

    return spec, experiment, proposal_text


def _load_prose(args: argparse.Namespace):
    """Load optional --prose / --si-prose / --figures from JSON files (shared by run +
    render).

    Each is agent-authored INPUT, never autonomous generation (sci-adk never calls an LLM
    to write it). Returns ``(prose, si_prose, figures)`` -- each None when its flag is
    absent. Raises :class:`_CliError` on a missing file or invalid JSON/spec.
    """
    prose = None
    if getattr(args, "prose", None):
        prose_path = Path(args.prose)
        if not prose_path.exists():
            raise _CliError(f"prose file not found: {prose_path}")
        from sci_adk.render.prose import PaperProse

        try:
            prose = PaperProse.model_validate_json(prose_path.read_text(encoding="utf-8"))
        except ValueError as e:
            raise _CliError(f"invalid prose JSON ({prose_path}): {e}")

    si_prose = None
    if getattr(args, "si_prose", None):
        si_prose_path = Path(args.si_prose)
        if not si_prose_path.exists():
            raise _CliError(f"si-prose file not found: {si_prose_path}")
        from sci_adk.render.prose import SIProse

        try:
            si_prose = SIProse.model_validate_json(
                si_prose_path.read_text(encoding="utf-8")
            )
        except ValueError as e:
            raise _CliError(f"invalid si-prose JSON ({si_prose_path}): {e}")

    figures = None
    if getattr(args, "figures", None):
        figures_path = Path(args.figures)
        if not figures_path.exists():
            raise _CliError(f"figures file not found: {figures_path}")
        from pydantic import TypeAdapter

        from sci_adk.render.figures import AnyFigure, PaperFigures

        raw = figures_path.read_text(encoding="utf-8")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise _CliError(f"invalid figures JSON ({figures_path}): {e}")
        try:
            if isinstance(parsed, list):
                # A bare list normalizes through the discriminated AnyFigure union, so a
                # list of native AND/OR image specs both validate (a native item omitting
                # "kind" defaults to native).
                figures = list(TypeAdapter(list[AnyFigure]).validate_python(parsed))
            else:
                figures = list(PaperFigures.model_validate(parsed).figures)
        except ValueError as e:
            raise _CliError(f"invalid figures spec ({figures_path}): {e}")

    return prose, si_prose, figures


def _load_run_spec(run_dir: Path):
    """Load + validate ``run_dir/spec.json`` (shared by the run-dir verbs).

    Returns the Spec. Raises :class:`_CliError` (exit 2) when ``spec.json`` is absent --
    the same friendly message the other run-dir verbs print.
    """
    spec_path = run_dir / "spec.json"
    if not spec_path.exists():
        raise _CliError(f"no spec.json found in run dir: {run_dir}")
    return Spec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))


def _check_spec_digest(spec, run_dir: Path, passed_digest) -> None:
    """Enforce the §6.1 spec-digest boundary for a record-advancing verb.

    Lenient when ``passed_digest`` is ``None``: NO check runs (backward-compat -- a bare
    CLI human user is not blocked; the orchestrator injects the flag for real worker
    sessions per design/sci-adk-as-moai.md §6.1). When a digest IS passed, it must equal
    the recorded Spec's digest; a mismatch raises :class:`SpecDigestMismatch` before any
    record is written, so a worker cannot silently advance past a tampered Spec.

    ``run_dir`` is accepted for context but the digest is taken from the in-memory
    ``spec`` the verb already loaded via ``_load_run_spec`` -- it IS the on-disk
    ``spec.json`` as read, so a silently-tampered file still yields a non-matching
    digest, while avoiding a redundant disk re-read and the ``FileNotFoundError`` path a
    re-read would expose to a TOCTOU race (spec.json deleted between load and check). The
    passed digest is case/whitespace-normalized (sha256 hex is lowercase, but a
    frozen-reference value injected as text may arrive upper-cased or padded); ``actual``
    is canonical and left as-is.
    """
    if passed_digest is None:
        return
    from sci_adk.provenance import SpecDigestMismatch, spec_digest

    # Digest the in-memory Spec the verb operates under (already loaded by _load_run_spec).
    # It IS the on-disk spec.json as loaded, so a silently-tampered spec.json still yields
    # a non-matching digest -- and digesting it here avoids a redundant re-read and the
    # FileNotFoundError path a disk re-read exposes to a TOCTOU race.
    actual = spec_digest(spec)
    if passed_digest.strip().lower() != actual:
        # expected=passed_digest (un-normalized) so the message shows what was passed.
        raise SpecDigestMismatch(spec_id=spec.id, expected=passed_digest, actual=actual)


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        spec, experiment, proposal_text = _resolve_capability_selection(args)
        prose, si_prose, figures = _load_prose(args)
    except _CliError as e:
        print(f"error: {e.message}", file=sys.stderr)
        return e.exit_code

    compiler = ResearchCompiler(
        workspace_dir=Path(args.output), strict_science=args.strict_science
    )
    # Evidence-validity halt (design/evidence-validity.md E3): an inadequate record
    # (e.g. synthetic data fed to an empirical claim) raises before any Claim is
    # written. Surface it as a friendly non-zero exit -- never a raw traceback and
    # never a "compiled ... supported" success line for an ungrounded result.
    from sci_adk.core.validity import ValidityHalt

    try:
        result = compiler.compile(
            proposal_text, spec_id=args.spec_id, spec=spec, experiment=experiment,
            prose=prose, si_prose=si_prose, figures=figures)
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
    if result.science_findings:
        # Spec-gate science audit (design/science-guards.md): ALWAYS surfaced (never silent),
        # never a halt. The verdict-gate HALTS (strict by default) enforce the same concerns
        # at SUPPORTED-stamp time; these are the spec-time reminders.
        print(f"  science-guard findings ({len(result.science_findings)}) "
              f"-> {result.run_dir / 'science.md'}:")
        for sf in result.science_findings:
            tag = sf.hypothesis_id or "(spec-wide)"
            print(f"    - {sf.guard} {tag}: {sf.message[:80]}")
    fc = result.figure_consistency
    if fc is not None and not fc.ok:
        # Non-blocking prose<->figure ref report (D4): a warning, not a gate.
        print("  figure consistency warnings (non-blocking):")
        if fc.dangling:
            print(f"    - dangling \\ref (no such figure): {', '.join(fc.dangling)}")
        if fc.orphan:
            print(f"    - orphan figure (never \\ref'd): {', '.join(fc.orphan)}")
    return 0


# -- Step 2 verbs (design/sci-adk-as-moai.md §4.6): each is a thin wrapper over one
# ResearchCompiler stage function. `run` remains the chained wrapper.

def _cmd_init_spec(args: argparse.Namespace) -> int:
    """Author + freeze a Spec into runs/<spec.id>/ (stage 1 of `run`).

    Resolves the Spec from a capability demo or a proposal (the shared
    ``_resolve_capability_selection``), then runs ``ResearchCompiler.stage_init_spec`` --
    writing spec.json + the Spec-time prior-work checkpoint.
    """
    try:
        spec, _experiment, proposal_text = _resolve_capability_selection(args)
    except _CliError as e:
        print(f"error: {e.message}", file=sys.stderr)
        return e.exit_code

    compiler = ResearchCompiler(workspace_dir=Path(args.output))
    frozen = compiler.stage_init_spec(
        spec=spec, proposal_text=proposal_text, spec_id=args.spec_id
    )
    run_dir = Path(args.output) / "runs" / frozen.id
    print(f"init-spec: froze Spec '{frozen.id}' (v{frozen.version}) -> {run_dir}")
    print(f"  spec: {run_dir / 'spec.json'}")
    # The frozen Spec's digest -- the orchestrator captures this for the worker's
    # [FROZEN SPEC REFERENCE] block (design/sci-adk-as-moai.md §6.1).
    from sci_adk.provenance import spec_digest

    print(f"  spec_digest: {spec_digest(frozen)}")
    print(f"  prior-work checkpoint: {run_dir / 'checkpoints' / 'prior_work.json'}")
    # Spec-gate science audit (design/science-guards.md): ALWAYS surfaced, never a halt.
    from sci_adk.core.spec_science import audit_spec_science

    findings = audit_spec_science(frozen)
    if findings:
        print(f"  science-guard findings ({len(findings)}) -> {run_dir / 'science.md'}:")
        for sf in findings:
            tag = sf.hypothesis_id or "(spec-wide)"
            print(f"    - {sf.guard} {tag}: {sf.message[:80]}")
    print(f"  next: sci-adk execute {run_dir} [--capability <id> | --t1-demo]")
    return 0


def _cmd_pubreqs_freeze(args: argparse.Namespace) -> int:
    """Freeze the F1 publishing-requirements contract into runs/<id>/pubreqs.json.

    Mirrors ``init-spec``: reads the run's recorded ``spec.json`` for the ``spec_id``, builds
    a :class:`PubReqs` from the CLI options (a ``--defaults`` fast-path supplies the IMRaD
    sections + font policy on + image_min_dpi 300 + reproduction bundle on), computes the
    tamper-evidence digest, and writes the FROZEN contract to ``runs/<id>/pubreqs.json`` at the
    RUN ROOT (beside spec.json, NOT inside paper/ so ``render`` never clobbers it). The verify
    umbrella gate (``paper_requirements_clean``) then checks the rendered paper against it.
    """
    from sci_adk.core.pubreqs import (
        DEFAULT_IMAGE_MIN_DPI,
        DEFAULT_REQUIRED_SECTIONS,
        PubReqs,
    )
    from sci_adk.provenance import pubreqs_digest

    run_dir = Path(args.run_dir)
    spec_path = run_dir / "spec.json"
    if not spec_path.exists():
        print(f"error: no spec.json found in run dir: {run_dir}", file=sys.stderr)
        return 2
    try:
        spec = Spec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))
    except ValueError as e:
        print(f"error: malformed spec.json in {run_dir}: {e}", file=sys.stderr)
        return 1

    # Required sections: --defaults seeds the IMRaD set; explicit --required-section entries
    # APPEND under --defaults, or REPLACE (start empty) without it.
    sections: list[str] = list(DEFAULT_REQUIRED_SECTIONS) if args.defaults else []
    if args.required_sections:
        sections.extend(args.required_sections)

    # image_min_dpi: --defaults -> 300 unless --no-image-dpi; an explicit --image-min-dpi
    # always wins; without --defaults and without an explicit value -> None (gate off).
    if args.no_image_dpi:
        image_min_dpi = None
    elif args.image_min_dpi is not None:
        image_min_dpi = args.image_min_dpi
    elif args.defaults:
        image_min_dpi = DEFAULT_IMAGE_MIN_DPI
    else:
        image_min_dpi = None

    pubreqs = PubReqs(
        spec_id=spec.id,
        venue=args.venue,
        required_sections=sections,
        figure_font_policy=args.figure_font_policy,
        image_min_dpi=image_min_dpi,
        reference_style=args.reference_style,
        max_pages=args.max_pages,
        max_words=args.max_words,
        reproduction_bundle=args.reproduction_bundle,
        advisory=list(args.advisory) if args.advisory else [],
    )
    # The digest is computed over the gate-bearing contract and STORED in the artifact
    # (design §1.1), unlike the Spec's on-demand digest. model_copy re-freezes with it set.
    digest = pubreqs_digest(pubreqs)
    frozen = pubreqs.model_copy(update={"digest": digest})

    pubreqs_path = run_dir / "pubreqs.json"
    pubreqs_path.write_text(
        frozen.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    print(f"pubreqs freeze: froze publishing requirements for '{spec.id}' -> {pubreqs_path}")
    print(f"  digest (sha256): {digest}")
    print(
        f"  required_sections: {', '.join(sections) if sections else '(none)'}"
    )
    print(f"  figure_font_policy: {'on' if frozen.figure_font_policy else 'off'}")
    print(
        f"  image_min_dpi: {image_min_dpi if image_min_dpi is not None else 'off'}"
    )
    print(
        "  reference_style: "
        f"{frozen.reference_style if frozen.reference_style else '(none)'}"
    )
    print(f"  max_words: {frozen.max_words if frozen.max_words is not None else '(none)'}")
    print(
        f"  reproduction_bundle: {'on' if frozen.reproduction_bundle else 'off'}"
    )
    if frozen.max_pages is not None:
        print(f"  max_pages (advisory): {frozen.max_pages}")
    if frozen.advisory:
        print(f"  advisory ({len(frozen.advisory)}): surfaced in verify, never gated")
    print(f"  next: sci-adk verify {run_dir}")
    return 0


def _cmd_pkgreqs_freeze(args: argparse.Namespace) -> int:
    """Freeze the workspace PackageReqs contract into <ws>/pkgreqs.json (design §2).

    Mirrors ``pubreqs freeze`` at the WORKSPACE scope: builds a :class:`PackageReqs` from the
    CLI options (a ``--defaults`` fast-path supplies the IMRaD required sections), computes the
    tamper-evidence digest, and writes the FROZEN contract to ``<ws>/pkgreqs.json`` at the
    workspace ROOT (beside runs/, NOT inside package/ so ``package`` never clobbers it). The
    ``package``/``verify <ws>`` umbrella gate then checks the assembled package against it.
    """
    from sci_adk.core.pkgreqs import (
        ALL_RUNS,
        DEFAULT_IMAGE_MIN_DPI,
        DEFAULT_REQUIRED_SECTIONS,
        PackageReqs,
    )
    from sci_adk.provenance import pkgreqs_digest

    workspace = Path(args.workspace)
    if not (workspace / "runs").is_dir():
        print(f"error: no runs/ directory under workspace: {workspace}", file=sys.stderr)
        return 2

    # Required sections: --defaults seeds the IMRaD set; explicit --required-section entries
    # APPEND under --defaults, or REPLACE (start empty) without it (mirrors pubreqs freeze).
    sections: list[str] = list(DEFAULT_REQUIRED_SECTIONS) if args.defaults else []
    if args.required_sections:
        sections.extend(args.required_sections)

    # body_word_range: both bounds required to form the advisory range; one alone is rejected.
    body_word_range = None
    if (args.body_word_min is None) != (args.body_word_max is None):
        print("error: --body-word-min and --body-word-max must be given together",
              file=sys.stderr)
        return 2
    if args.body_word_min is not None and args.body_word_max is not None:
        body_word_range = (args.body_word_min, args.body_word_max)

    # image_min_dpi: --defaults -> 300 unless --no-image-dpi; an explicit --image-min-dpi
    # always wins; without --defaults and without an explicit value -> None (gate off).
    # Mirrors pubreqs freeze.
    if args.no_image_dpi:
        image_min_dpi = None
    elif args.image_min_dpi is not None:
        image_min_dpi = args.image_min_dpi
    elif args.defaults:
        image_min_dpi = DEFAULT_IMAGE_MIN_DPI
    else:
        image_min_dpi = None

    runs: object = list(args.runs) if args.runs else ALL_RUNS

    pkgreqs = PackageReqs(
        venue=args.venue,
        required_sections=sections,
        figure_font_policy=args.figure_font_policy,
        image_min_dpi=image_min_dpi,
        reference_style=args.reference_style,
        abstract_max_words=args.abstract_max_words,
        body_word_range=body_word_range,
        runs=runs,
        advisory=list(args.advisory) if args.advisory else [],
    )
    # The digest is computed over the gate-bearing contract and STORED in the artifact (design
    # §2), unlike the Spec's on-demand digest. model_copy re-freezes with it set.
    digest = pkgreqs_digest(pkgreqs)
    frozen = pkgreqs.model_copy(update={"digest": digest})

    pkgreqs_path = workspace / "pkgreqs.json"
    pkgreqs_path.write_text(frozen.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"pkgreqs freeze: froze package requirements -> {pkgreqs_path}")
    print(f"  digest (sha256): {digest}")
    print(f"  venue: {frozen.venue if frozen.venue else '(unspecified)'}")
    print(f"  required_sections: {', '.join(sections) if sections else '(none)'}")
    print(f"  figure_font_policy: {'on' if frozen.figure_font_policy else 'off'}")
    print(
        "  image_min_dpi: "
        f"{frozen.image_min_dpi if frozen.image_min_dpi is not None else '(off)'}"
    )
    print(
        "  reference_style: "
        f"{frozen.reference_style if frozen.reference_style else '(none)'}"
    )
    print(
        "  abstract_max_words: "
        f"{frozen.abstract_max_words if frozen.abstract_max_words is not None else '(none)'}"
    )
    print(f"  runs: {'all' if frozen.runs == ALL_RUNS else ', '.join(frozen.runs)}")
    if frozen.body_word_range is not None:
        lo, hi = frozen.body_word_range
        print(f"  body_word_range (advisory): {lo}-{hi}")
    if frozen.advisory:
        print(f"  advisory ({len(frozen.advisory)}): surfaced in verify, never gated")
    print(f"  next: sci-adk package {workspace}")
    return 0


def _cmd_package(args: argparse.Namespace) -> int:
    """Assemble the workspace package, then run the package_requirements_clean gate (design §C).

    ``sci-adk package <ws>`` drives the deterministic spine: it assembles the 6-folder
    ``package/`` from ALL runs (unless ``--no-assemble``), then runs the read-only,
    no-LLM ``package_requirements_clean`` gate over it, printing failures the same way the
    other paper gates do. Exit 0 iff every declared package requirement is met.
    """
    from sci_adk.render.package import assemble_package

    workspace = Path(args.workspace)
    if not (workspace / "runs").is_dir():
        print(f"error: no runs/ directory under workspace: {workspace}", file=sys.stderr)
        return 2

    if args.assemble:
        pkgreqs = _load_workspace_pkgreqs(workspace)
        try:
            assembly = assemble_package(workspace, pkgreqs)
        except (FileNotFoundError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(f"package: assembled {assembly.package_dir} from {len(assembly.runs)} run(s)")
        print(f"  runs: {', '.join(assembly.runs)}")
        if not assembly.main_tex_authored:
            print("  manuscript: 01_manuscript/main.tex is the record-derived SKELETON "
                  "(author it via /sci package)")
        for note in assembly.notes:
            print(f"  note: {note}")

    return _run_package_gate(workspace)


def _load_workspace_pkgreqs(workspace: Path):
    """Load <ws>/pkgreqs.json if present (the assembler scaffolds generically without it)."""
    from sci_adk.core.pkgreqs import PackageReqs

    pkgreqs_path = workspace / "pkgreqs.json"
    if not pkgreqs_path.is_file():
        return None
    try:
        return PackageReqs.model_validate(
            json.loads(pkgreqs_path.read_text(encoding="utf-8"))
        )
    except ValueError:
        return None


def _run_package_gate(workspace: Path) -> int:
    """Run the workspace package gate + print its report like the other paper gates.

    Shared by ``package`` and ``verify <ws>``. Exit 0 iff ``package_requirements_clean``.
    """
    from sci_adk.loop.verify import verify_package

    try:
        report = verify_package(workspace)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    pkgdir = workspace / "package"
    if not pkgdir.is_dir():
        print(f"package gate: no package/ at {workspace} -> nothing to gate "
              "(run `sci-adk package` to assemble it)")
        return 0

    print(f"package gate over {pkgdir}")
    if report.runs:
        reproduced = sum(1 for v in report.runs_reproduced.values() if v)
        print(f"  runs synthesized: {len(report.runs)} "
              f"({reproduced}/{len(report.runs)} reproduce)")
    if report.package_requirements_clean:
        print("  package requirements: OK (declared requirements met)")
    else:
        print("  package requirements FAILED (declared requirements not met):",
              file=sys.stderr)
        for problem in report.package_requirements_problems:
            print(f"    - {problem}", file=sys.stderr)
    for note in report.advisory:
        print(f"  package advisory: {note}")
    return 0 if report.passed else 1


def _cmd_amend_spec(args: argparse.Namespace) -> int:
    """Amend the run's recorded Spec + record the checkpoint receipt (S5).

    Wraps ``loop.amend_spec.amend_spec`` (which calls the existing ``Spec.amend`` -- no
    new semantics). A missing run dir / spec.json -> exit 2; a blank --rationale ->
    exit 2 with the S5 message (re-raised ValueError from Spec.amend).
    """
    run_dir = Path(args.run_dir)
    from sci_adk.loop.amend_spec import amend_spec

    try:
        new_spec, receipt = amend_spec(run_dir, rationale=args.rationale)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        # Blank rationale (S5): a Spec amendment is never silent -- the record must say why.
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(f"amend-spec: Spec '{new_spec.id}' amended "
          f"v{receipt.prior_version} -> v{receipt.new_version}")
    print(f"  rationale: {receipt.rationale}")
    print(f"  receipt: {run_dir / 'checkpoints' / f'amendment-v{receipt.new_version}.json'}")
    print(f"  spec.json now holds the amended (v{new_spec.version}) frozen Spec")
    # The amended Spec's NEW digest -- it differs from the pre-amend one, so the worker's
    # stale frozen reference will fail the §6.1 boundary until it re-fetches this value.
    from sci_adk.provenance import spec_digest

    print(f"  spec_digest: {spec_digest(new_spec)}")
    return 0


def _cmd_execute(args: argparse.Namespace) -> int:
    """Execute the run's experiment into Evidence (stage 2 of `run`).

    Reads the recorded Spec from the run dir, resolves the capability's experiment (the
    SAME selection ``run`` uses), and runs ``ResearchCompiler.stage_execute``. Honors F5
    reuse (a second execute over a populated run replays unless --force). The capability
    is HOW, not WHAT -- it is not in the frozen Spec, so it is selected here just as `run`
    does, and must match what the Spec was authored for.
    """
    run_dir = Path(args.run_dir)
    # workspace root holds runs/ (run_dir is <workspace>/runs/<spec.id>).
    workspace = run_dir.parent.parent
    try:
        spec = _load_run_spec(run_dir)
    except _CliError as e:
        print(f"error: {e.message}", file=sys.stderr)
        return e.exit_code

    # Resolve the capability's experiment ONLY when one is selected. Unlike `run`, a bare
    # `execute` (no capability) is legitimate: with recorded Evidence it replays (F5), so
    # "no capability" maps to experiment=None rather than a usage error. The Spec is
    # already frozen on disk, so only the experiment half of the selection is needed.
    experiment = None
    if args.capability is not None or args.t1_demo:
        try:
            _spec, experiment, _proposal = _resolve_capability_selection(args)
        except _CliError as e:
            print(f"error: {e.message}", file=sys.stderr)
            return e.exit_code

    from sci_adk.core.validity import ValidityHalt

    compiler = ResearchCompiler(workspace_dir=workspace)
    try:
        evidence = compiler.stage_execute(
            spec, experiment=experiment, force=args.force
        )
    except ValidityHalt as e:
        print(f"error: evidence-validity halt: {e.reason}", file=sys.stderr)
        return 2

    if not evidence:
        print(f"error: no experiment selected and no recorded Evidence to reuse for "
              f"'{spec.id}'; pass --t1-demo / --capability <id> (or --force to re-run)",
              file=sys.stderr)
        return 2
    print(f"execute: produced {len(evidence)} Evidence item(s) for Spec '{spec.id}' "
          f"-> {run_dir / 'evidence'}")
    print(f"  next: sci-adk derive-claim {run_dir}")
    return 0


def _cmd_append_evidence(args: argparse.Namespace) -> int:
    """Append one typed EvidenceItem (from a JSON file) to the run's log (E1).

    The single-item complement to ``execute``. Loads the EvidenceItem via
    ``EvidenceItem.model_validate`` and runs ``ResearchCompiler.stage_append_evidence``.
    """
    run_dir = Path(args.run_dir)
    workspace = run_dir.parent.parent
    try:
        spec = _load_run_spec(run_dir)
    except _CliError as e:
        print(f"error: {e.message}", file=sys.stderr)
        return e.exit_code

    # §6.1 spec-digest boundary: a worker-passed --spec-digest must match the recorded
    # Spec BEFORE any Evidence is written (a mismatch means the Spec was silently revised).
    from sci_adk.provenance import SpecDigestMismatch

    try:
        _check_spec_digest(spec, run_dir, args.spec_digest)
    except SpecDigestMismatch as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    ev_path = Path(args.evidence)
    if not ev_path.exists():
        print(f"error: evidence file not found: {ev_path}", file=sys.stderr)
        return 2

    from sci_adk.core.evidence import EvidenceItem

    try:
        item = EvidenceItem.model_validate(
            json.loads(ev_path.read_text(encoding="utf-8"))
        )
    except json.JSONDecodeError as e:
        print(f"error: invalid evidence JSON ({ev_path}): {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"error: invalid EvidenceItem ({ev_path}): {e}", file=sys.stderr)
        return 2

    compiler = ResearchCompiler(workspace_dir=workspace)
    compiler.stage_append_evidence(spec, item)
    print(f"append-evidence: appended Evidence '{item.id}' ({item.kind.value}) "
          f"to Spec '{spec.id}' -> {run_dir / 'evidence' / f'{item.id}.json'}")
    print(f"  next: sci-adk derive-claim {run_dir}")
    return 0


def _cmd_derive_claim(args: argparse.Namespace) -> int:
    """Apply each DecisionRule to the recorded Evidence -> Claims (stage of `run`).

    Reads spec + evidence from the run dir and runs ``ResearchCompiler.stage_derive_claim``
    (which persists claims/ and surfaces the recording-type checkpoints). An evidence-
    validity halt (E3) -- e.g. synthetic data backing an empirical claim -- surfaces as a
    friendly non-zero exit, never a traceback and never a spurious "supported" line.
    """
    run_dir = Path(args.run_dir)
    workspace = run_dir.parent.parent
    try:
        spec = _load_run_spec(run_dir)
    except _CliError as e:
        print(f"error: {e.message}", file=sys.stderr)
        return e.exit_code

    # §6.1 spec-digest boundary: a worker-passed --spec-digest must match the recorded
    # Spec BEFORE any Claim is derived (a mismatch means the Spec was silently revised).
    from sci_adk.provenance import SpecDigestMismatch

    try:
        _check_spec_digest(spec, run_dir, args.spec_digest)
    except SpecDigestMismatch as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    from sci_adk.core.validity import ValidityHalt

    compiler = ResearchCompiler(
        workspace_dir=workspace, strict_science=args.strict_science
    )
    try:
        claims, checkpoints, _contested, _novelty = compiler.stage_derive_claim(spec)
    except ValidityHalt as e:
        print(f"error: evidence-validity halt: {e.reason}", file=sys.stderr)
        return 2

    print(f"derive-claim: derived {len(claims)} Claim(s) for Spec '{spec.id}' "
          f"-> {run_dir / 'claims'}")
    for claim in claims:
        print(f"    - {claim.answers}: {claim.status.value}  "
              f"({claim.confidence.basis[:70]})")
    if checkpoints:
        print(f"  agent checkpoints ({len(checkpoints)}) -> "
              f"{run_dir / 'checkpoints.md'}:")
        for c in checkpoints:
            print(f"    - {c.hypothesis_id} ({c.kind}): {c.expression[:60]}")
    print(f"  next: sci-adk render {run_dir}")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    """Render the paper/ artifacts from the recorded spec/evidence/claims (final stage).

    Reads spec + evidence + claims from the run dir and runs
    ``ResearchCompiler.stage_render`` with any agent-authored --prose / --si-prose /
    --figures (the same options as `run`).
    """
    run_dir = Path(args.run_dir)
    workspace = run_dir.parent.parent
    try:
        spec = _load_run_spec(run_dir)
        prose, si_prose, figures = _load_prose(args)
    except _CliError as e:
        print(f"error: {e.message}", file=sys.stderr)
        return e.exit_code

    compiler = ResearchCompiler(workspace_dir=workspace)
    try:
        paper_path, si_path, figure_consistency = compiler.stage_render(
            spec, prose=prose, si_prose=si_prose, figures=figures
        )
    except ValueError as e:
        # A missing image-figure source / malformed figure spec fails loud (record
        # fidelity) -- surface friendly, never a raw traceback.
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(f"render: compiled paper for Spec '{spec.id}' -> {paper_path}")
    if si_path is not None:
        print(f"  supporting information: {si_path}")
    fc = figure_consistency
    if fc is not None and not fc.ok:
        print("  figure consistency warnings (non-blocking):")
        if fc.dangling:
            print(f"    - dangling \\ref (no such figure): {', '.join(fc.dangling)}")
        if fc.orphan:
            print(f"    - orphan figure (never \\ref'd): {', '.join(fc.orphan)}")

    # PF-7 (design/near-submission-package.md): a per-run render is the internal record,
    # not the workspace submission. When the workspace holds more than one run, warn and
    # point to `package` -- route-to-package + warn, never a refuse (single-run and
    # mid-work renders stay unbroken).
    runs_dir = run_dir.parent
    if runs_dir.is_dir():
        n_runs = sum(1 for d in runs_dir.iterdir() if (d / "spec.json").is_file())
        if n_runs > 1:
            print(
                f"  note: this is the per-run internal record, not the submission "
                f"({n_runs} runs in this workspace) -- for the near-submission package run "
                f"`sci-adk package {workspace}` (or /sci package).",
                file=sys.stderr,
            )
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
        # PF-5 (design/near-submission-package.md §6): `verify <ws>` auto-detects a WORKSPACE
        # (no spec.json, but a runs/ dir + a package/ or a frozen pkgreqs.json) and runs the
        # workspace-level package umbrella gate instead of the per-run audit. A target that is
        # neither a run dir nor a package workspace is the original error.
        is_workspace = (run_dir / "runs").is_dir() and (
            (run_dir / "package").is_dir() or (run_dir / "pkgreqs.json").is_file()
        )
        if is_workspace:
            return _run_package_gate(run_dir)
        print(f"error: no spec.json found in run dir: {run_dir}", file=sys.stderr)
        return 2

    # A recorded artifact (spec/evidence/claim/verdict) may be malformed, or two
    # hypotheses may share a rule expression; the kernel raises a clear ValueError in
    # those cases. Surface it as a friendly stderr message rather than a raw traceback
    # (a third party may be auditing a hand-edited run).
    from sci_adk.loop.verify import verify_run

    try:
        report = verify_run(run_dir, strict_science=args.strict_science)
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
    else:
        print("  NOT reproduced: at least one claim DIVERGED or is UNRESOLVED "
              "(see above)", file=sys.stderr)

    # Phase 3 (design/paper-figures-and-si.md D4): paper-consistency is a HARD gate.
    # Report each rendered document's internal \ref<->\label integrity; a broken
    # reference (unresolved \ref) or a duplicate \label fails the combined exit gate
    # EVEN IF every claim reproduces. A run with no paper/ -> empty map -> consistent.
    if report.paper_consistency:
        if report.paper_consistent:
            print("  paper consistency: OK (internal \\ref<->\\label integrity) for "
                  f"{', '.join(sorted(report.paper_consistency))}")
        else:
            print("  paper consistency FAILED (internal \\ref<->\\label integrity):",
                  file=sys.stderr)
            for name in sorted(report.paper_consistency):
                rep = report.paper_consistency[name]
                if rep.ok:
                    continue
                if rep.unresolved_refs:
                    print(f"    - {name}: unresolved \\ref (no such \\label): "
                          f"{', '.join(rep.unresolved_refs)}", file=sys.stderr)
                if rep.duplicate_labels:
                    print(f"    - {name}: duplicate \\label (multiply defined): "
                          f"{', '.join(rep.duplicate_labels)}", file=sys.stderr)

    # Fidelity gate: a residual \evval/\status macro in a rendered .tex (substitution
    # bypassed / .tex hand-edited) fails the combined gate.
    if not report.paper_factref_clean:
        print("  fidelity FAILED (unsubstituted \\evval/\\status fact macros):",
              file=sys.stderr)
        for name in sorted(report.paper_factrefs):
            print(f"    - {name}: {', '.join(report.paper_factrefs[name])}",
                  file=sys.stderr)

    # Tool-vocabulary gate (§10): the PAPER must read as tool-agnostic science (the SI is
    # exempt). A leak in draft.tex fails the combined gate.
    if not report.paper_tool_clean:
        print("  tool-vocabulary FAILED (draft.tex names the toolchain, not the "
              "science -- §10): " + ", ".join(report.paper_tool_vocab), file=sys.stderr)

    # Cross-document gate: a main-paper "Figure/Table S<n>" that points past the SI's float
    # count is a silent dangling cross-reference (a real \ref cannot cross the compile
    # boundary, so the within-document gate never sees it). It fails the combined gate.
    if not report.paper_cross_doc_clean:
        print("  cross-document FAILED (draft.tex cites SI floats that do not exist): "
              + ", ".join(report.paper_cross_doc_refs), file=sys.stderr)

    # Publishing-requirements gate (F1, design §1.3): the umbrella that consumes F2 (font/DPI)
    # + F3 (reproduction bundle) + section/reference/word-count checks the frozen pubreqs.json
    # declared. Absent pubreqs.json -> vacuously clean (no line). advisory/max_pages are
    # surfaced but NEVER gated, so a clean run with a contract is reported OK.
    pubreqs_path = run_dir / "pubreqs.json"
    if pubreqs_path.is_file():
        if report.paper_requirements_clean:
            print("  publishing requirements: OK (declared requirements met)")
        else:
            print("  publishing requirements FAILED (declared requirements not met):",
                  file=sys.stderr)
            for problem in report.paper_requirements_problems:
                print(f"    - {problem}", file=sys.stderr)
        # ADVISORY surfacing (never gated): the contract's free-form advisory + max_pages.
        from sci_adk.core.pubreqs import PubReqs

        try:
            pr = PubReqs.model_validate(
                json.loads(pubreqs_path.read_text(encoding="utf-8"))
            )
        except ValueError:
            pr = None
        if pr is not None:
            if pr.max_pages is not None:
                print(f"  publishing advisory: max_pages {pr.max_pages} "
                      "(advisory only -- no page count without a compile)")
            for note in pr.advisory:
                print(f"  publishing advisory: {note} (advisory only -- not gated)")
        # SPEC-PAPER-GATE-001 OD-5/OD-6 (R1): per-run non-blocking advisories -- an
        # unpublished/DOI-less citation, or an undeclared section order deviating from default
        # IMRaD. Surfaced here, NEVER gated (not in report.passed).
        for note in report.paper_advisory:
            print(f"  publishing advisory: {note} (advisory only -- not gated)")

    # The exit gate is the COMBINED signal: claims reproduce AND the paper is consistent
    # AND no residual fact macro AND the paper is tool-agnostic AND every cross-document
    # "Figure/Table S<n>" resolves AND every declared publishing requirement is met.
    if report.passed:
        return 0
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
    # acquisition (refusing the silently degraded OA run that the degraded-acquisition failure rode past).
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
    """Record a novelty/priority discovery decision for one {hypothesis, kind} (the High
    trigger, 2-kind) into the log.

    Reads the recorded Spec (no LLM); for ``--searched`` it drives the existing acquirer
    (a LITERATURE item) and records a searched NOVELTY_DECISION carrying ``--kind``, for
    ``--skip`` it records a skipped NOVELTY_DECISION null (with kind) and the given reason.
    A skip does NOT satisfy the kind's novelty gate (it is a recorded null, not a search).
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
            spec, workspace, hypothesis_id=args.hypothesis, kind=args.kind,
            reason=args.reason)
        print(f"recorded {args.kind}-novelty decision (skipped) for hypothesis "
              f"'{args.hypothesis}' -> {item.kind.value} evidence {item.id}")
        print(f"  reason: {args.reason.strip()}")
        print(f"  note: a skipped {args.kind} novelty search leaves "
              f"claim-novelty-{args.kind}-{args.hypothesis} PROPOSED")
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
            spec, workspace, hypothesis_id=args.hypothesis, kind=args.kind,
            dois=args.searched, found=found, allow_no_email=args.allow_no_email)
    except ConfigHalt as e:
        print(f"error: {e}", file=sys.stderr)
        print("  - or pass --allow-no-email to proceed with degraded OA acquisition",
              file=sys.stderr)
        return 2
    ev = outcome.evidence
    outcome_str = "found_nothing" if found == "nothing" else "found_something"
    print(f"recorded {args.kind}-novelty decision (searched: {outcome_str}) for "
          f"hypothesis '{args.hypothesis}' -> {ev.kind.value} evidence {ev.id}")
    print(f"  acquired: {len(outcome.result.succeeded)} | "
          f"failed: {len(outcome.result.failed)}")
    if found == "nothing":
        print(f"  note: found-nothing -> claim-novelty-{args.kind}-{args.hypothesis} "
              "derives SUPPORTED on recompile")
    else:
        print(f"  note: found-prior-art -> the {args.kind}-novelty claim stays PROPOSED "
              f"(drop the novelty_{args.kind} flag via a Spec amendment, F7)")
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
    if args.command == "init-spec":
        return _cmd_init_spec(args)
    if args.command == "pubreqs":
        return _cmd_pubreqs_freeze(args)
    if args.command == "pkgreqs":
        return _cmd_pkgreqs_freeze(args)
    if args.command == "package":
        return _cmd_package(args)
    if args.command == "amend-spec":
        return _cmd_amend_spec(args)
    if args.command == "execute":
        return _cmd_execute(args)
    if args.command == "append-evidence":
        return _cmd_append_evidence(args)
    if args.command == "derive-claim":
        return _cmd_derive_claim(args)
    if args.command == "render":
        return _cmd_render(args)
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
