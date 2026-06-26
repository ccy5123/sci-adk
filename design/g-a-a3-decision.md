# G-A / A3 Decision Record — does IEAM-P8 discharge the generalization gate?

> Status: DECIDED (2026-06-26)
> Classification: DECISION RECORD (single source for the A3 verdict)
> Verdict: **Split A1 → A1a DONE (verification-kernel generality on a 2nd domain) /
> A1b scoped OUT of the 1.0 claim (autonomous experiment adapter-seam generality, T-1 only)**
> Supersedes the `[TBD]` status of `design/release-readiness.md` §3 A3.

## 0. What this resolves

`design/release-readiness.md` §3 left A3 as `[TBD]`: *"Decide whether IEAM-P8
(ecotoxicology) satisfies A1"* — A1 being *"a 2nd domain plugs into the kernel via
the adapter seam with no kernel edit."* This record makes that decision, grounded in
measurement of both the kernel and the IEAM-P8 workspace, and states exactly what is
and is not validated.

## 1. The contract being judged against (verbatim)

The generalization gate (`design/adoption-roadmap.md` §6, near line 266):

> *"the general seam (A3) is only **proven** when a 2nd, different domain plugs in with
> no kernel edit ... This gate precedes any claim of domain-generality."*

The seam itself (A3 plug-seam, `design/adoption-roadmap.md` §A3): the kernel knows only
**three interfaces** — **Verifier** (`DecisionEngine`), **Experiment** (`ExperimentFn`
hook), **Judge** (injected) — never domain content. A capability registry + `--capability`
selector resolves the experiment at runtime; an F4 lint makes `kernel → adapter` imports a
build-failing invariant.

Key consequence: "plugging into the seam" is not one act. The seam is three interfaces,
and a domain can exercise some without others.

## 2. Measured facts (basis for the verdict)

### 2.1 The kernel is domain-free; the adapter is the experiment-author half

- The kernel (`sci_adk.core` + `sci_adk.loop` + `sci_adk.render`) MUST NOT import the
  adapter — enforced on every `pytest` by an AST lint, `tests/test_kernel_adapter_seam.py`
  (one-way `adapter → kernel` only). `src/sci_adk/loop/status.py:26-27` restates it.
- The adapter (`src/sci_adk/adapter/`) holds **T-1 only**: `t1_capability.py` +
  `t1_encoding.py` + `registry.py`. What it provides is the in-loop
  `ExperimentFn: (Spec, Path) -> [EvidenceItem]` — i.e. *how an experiment is run
  autonomously* (`src/sci_adk/adapter/__init__.py:9-13`, `t1_capability.py` header).
- `sci-adk verify` / record / package never touch the adapter — they are the domain-free
  **Verifier** + typed-store kernel.

So the two halves of the seam are separable:
- **Verifier** interface (`DecisionEngine` / `sci-adk verify`) + the typed Spec/Evidence/
  Claim store — domain-free kernel; needs no adapter.
- **Experiment** interface (`ExperimentFn` registered via `adapter/registry.py`,
  `--capability`) — the autonomous experiment-author half; T-1 is its only provider.

### 2.2 What IEAM-P8 actually exercised

IEAM-P8 (`~/research/ieam-followup-p8`, NOT in this repo) is a separate research workspace
that used the installed `sci-adk` as a tool. Domain: environmental toxicology /
bioaccumulation on a Dynamic Energy Budget toxicokinetic (DEB-TK) core — a genuinely
different domain from T-1 (molecular Gödel encoding).

Measured in that workspace:
- **27 full kernel runs** under `runs/ieam-p8-*/`, each a typed-store run dir:
  `spec.json` (typed `Spec`: `raw_proposal` / `hypotheses` / `version`), `claims/`,
  `evidence/`, `checkpoints/`, `paper/`. → the kernel's **typed store (A4)** was used.
- **Verifier interface exercised**: `package/06_provenance/verify_all.txt` ends
  `"SUMMARY: 27/27 runs reproduce all recorded claims (DIVERGED/UNRESOLVED -> RED)"`.
  A `contested` claim reproduces as contested (non-monotone belief working).
- `package/02_data/claims_all.csv` carries **100 Claims** in the kernel schema
  (`run_id,hyp_id,mode,referent,status,point_statistic,op,threshold,statement`),
  status 81 supported / 17 refuted / 2 contested (refuted/contested first-class).
- **Zero kernel edits** — the installed binary was used unchanged.
- **Experiment adapter-registry NOT used**: evidence provenance records a `method` field,
  not a `capability` id; no `t2_*` provider is registered in `adapter/registry.py`. The
  experiments were authored via the **operational / borrow path** (in-session-authored
  analysis scripts) — which is exactly A5's sanctioned substrate model
  (`design/adoption-roadmap.md` §A5: in-session agent; no autonomous API).

## 3. Verdict

IEAM-P8 plugged a 2nd, different domain into the kernel's **Verifier** interface
(+ typed store) with **zero kernel edits**, producing 27 reproducing runs and 100
deterministically-judged Claims. It did **not** plug into the **Experiment**
adapter-registry interface; experiments came via the operational/borrow path.

A1 is therefore **split**, because it conflated two separable claims:

| Sub-gate | Claim | Status | Basis |
|----------|-------|--------|-------|
| **A1a** | Verifier-seam + record/belief generality on a 2nd domain | **`[DONE]`** | IEAM-P8: 27/27 reproduce, 100 Claims, ecotox/DEB-TK, zero kernel edits |
| **A1b** | Autonomous Experiment adapter-registry (`ExperimentFn`/`--capability`) generality on a 2nd domain | **scoped OUT of the 1.0 claim** | T-1 is the only registered capability; IEAM-P8 used the operational path, not the registry |

**A1a is what G-A exists to protect.** sci-adk's public identity is a *domain-general rigor
/ verification ADK* — "referee, not player"; "agents propose, the engine judges;
`sci-adk verify` is the sole verdict path." The property under that claim is the
**verification kernel's** domain-generality, and IEAM-P8 validates exactly that, end-to-end,
on a real 2nd domain.

**A1b is the de-emphasized "player" half.** The autonomous in-loop experiment-author
(`ExperimentFn` registry) is the part sci-adk deliberately minimizes (A5 in-session-only;
LLM-as-verdict permanently CUT in `design/adoption-roadmap.md`). Its cross-domain generality
remaining T-1-only does not undercut the public verification claim — and IEAM-P8 used the
sanctioned operational substrate in its place, so nothing is missing for the claim sci-adk
actually makes. It is **scoped out of the 1.0 claim** (not silently claimed, not blocked on).

### Confidence
- Facts (§2): **HIGH** — measured in both repos.
- Interpretation (which reading governs the gate): **MEDIUM-HIGH**.

### Devil's-advocate (recorded, per CC meta-rule #3)
*"On a strict reading the seam IS the adapter/`ExperimentFn` mechanism; IEAM-P8 went around
it, so it proves nothing about the seam — only that the verify kernel is domain-general."*
The split accepts this for **A1b** (the experiment adapter-registry is genuinely unproven on
a 2nd domain) while recognizing that **A1a** — verification-kernel generality reached through
the Verifier interface — is the property the public claim is actually about. The strict
reading narrows what "seam" means to its experiment half; the public claim is broader than
that half, and is discharged.

## 4. Implications

- **G-A keystone**: substantively validated **for the verification claim** (A1a). The
  external-1.0 blocker in `design/release-readiness.md` §9 ("an external 1.0 that advertises
  domain-generality would violate G-E") is resolved for the verification framing.
- **G-E (honesty)**: the prepared honest wording in `design/release-readiness.md` §7 can now
  be relaxed toward an *evidence-backed* "domain-general rigor/verification, validated
  end-to-end on a 2nd domain (ecotox) via the verify gate; the autonomous experiment seam is
  validated on T-1." Applying that wording to README/pyproject/CITATION remains a **separate
  one-step edit** (still DEFERRED here; do it as the G-E apply step).
- **A2** (`release-readiness.md` §3): in-repo `runs/` are still all T-1; the 2nd-domain
  evidence is **external** (IEAM-P8 workspace). A2-as-worded ("in-repo runs not a single
  family") stays `[OPEN]`; the generality it gates is discharged externally (A1a). An in-repo
  T-2 run would close A2 cosmetically but adds no new validation.
- **A4** (in-repo T-2 adapter): needed only if A1b is later pursued. Under this verdict A1b is
  scoped out, so A4 is **optional / future**, not a 1.0 blocker.
- **Sequencing**: G-B (methods paper) and G-C/G-D (hygiene, version) are no longer gated by an
  unresolved keystone; they can proceed. T-1 remains the paper's primary case study; IEAM-P8
  is available as the cross-domain *verification* evidence (not as an adapter-seam case).

## 5. Scope note (honest limits of this record)

This record does not itself edit any public surface (README/pyproject/CITATION) — that is the
G-E apply step. It does not run new science or write into the IEAM-P8 workspace. It records a
judgment over already-existing evidence. IEAM-P8 evidence lives outside this repo and is not
re-vendored here; the citations in §2.2 point to that external workspace as the basis.

---

Version: 1.0
Created: 2026-06-26 (sci-adk session 8)
Related: `design/release-readiness.md` §3/§7/§9 (G-A, G-E, DoD),
`design/adoption-roadmap.md` §A3/§6 (plug-seam, generalization gate),
`design/sci-adk-as-moai.md` + `design/rigor-shell-architecture.md` (kernel/adapter seam, F4).
