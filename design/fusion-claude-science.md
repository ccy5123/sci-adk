# Fusion with Claude Science — sci-adk as the epistemic gate over a research workbench

> Version: 0.2 (DESIGN — transport + connector boundary RESOLVED against source)
> Status: design confirmed on the two open crux decisions (D1 attachment point, D2 transport);
> D3 (advisory channel) still open. Every architectural claim below is traced to code (path:line)
> or to a measured external source (§13 appendix). Supersedes the v0.1 DRAFT.
> Last Updated: 2026-07-01
> Related: `design/rigor-shell-architecture.md` (kernel + seam, F1–F7), `design/sci-adk-as-moai.md`
> (operational layer), `design/tool-policy.md`, `design/science-guards.md`,
> `design/evidence-validity.md`, `design/literature-acquisition.md`

---

## 0. What changed from v0.1

The v0.1 DRAFT proposed the frame and the five seam invariants but left the two load-bearing
integration questions open (D1 attachment, D2 transport) and did not verify its own factual
premises against the codebase. This version closes both, grounded in a 2026-07-01 investigation:

- **Every premise verified.** All nine architectural claims the fusion leans on are CONFIRMED in
  source (§13.1). The operational layer the fusion needs (`/sci` hub, workers, advisory guards,
  `init-session` kit, Stop-hook `verify`) **already exists** — so the fusion is a *thin adapter*,
  not a new system.
- **D2 transport RESOLVED (measured).** Claude Science connectors are MCP-powered and users can
  attach **their own MCP servers**, including **local Desktop Extensions** (§13.2). So the transport
  is a **local MCP connector wrapping sci-adk's existing CLI verbs** — the in-session agent calls
  `append-evidence` directly. File-drop is the fallback, not the primary path.
- **D1 attachment RESOLVED.** Operational-layer delegation first (the session calls sci-adk tools);
  the adapter-seam `ExperimentFn` provider is a later, separate concern.
- **Connector boundary specified from code** (§7) — which verbs to expose, which to block, and why
  FUS-1 holds structurally rather than by connector discipline.

---

## 1. Purpose

On 2026-06-30 Anthropic released **Claude Science**, an interactive AI workbench that integrates the
tools researchers use, orchestrates compute (laptop / HPC over SSH / Modal on demand), generates
figures and manuscripts alongside the code that produced them, and runs a reviewer agent that checks
citations and calculations and self-corrects.

This document decides **how sci-adk composes with a workbench like Claude Science without surrendering
the one property that defines sci-adk**: the verdict path is deterministic, rule-based, and no-LLM.
A third party reproduces the verdict from the record alone, without any vendor's stack.

The frame: **sci-adk is epistemic CI/CD wrapping a Claude Science session.** Claude Science *generates*
belief; sci-adk *judges* belief. This is a layering, not a merge of two reviewers.

---

## 2. Positioning

| | Claude Science | sci-adk |
|---|---|---|
| Role | Player — the workbench that *does* research | Referee — judges whether a claim earned its support |
| Reviewer | LLM reviewer agent, self-correcting (belief checks belief) | `verify`: frozen `DecisionRule` re-applied to the record, offline, model-free |
| Trust model | Model-as-checker | Trust-minimizing; no self-certification |
| Distribution | Product on Pro/Max/Team/Enterprise (beta) | Vendor-neutral, MIT, install-and-extend |

**Now table-stakes (do not compete here):** auditable artifacts, a reviewer agent, reproducible
history. A workbench gives these to every user.

**Durable differentiators (sharpened by the launch):** deterministic no-LLM verdict; record/belief
separation as a kernel-level type system; frozen pre-registered Spec + science guards G1–G5;
vendor-independent verification.

**Domain note (keep the fusion domain-general).** Claude Science's *native* artifacts are life-sciences
(3D proteins, genome tracks, ChEMBL/PDB/UniProt). sci-adk is domain-GENERAL and must stay so — no fusion
surface may assume biology. What the fusion consumes from the workbench is its *domain-general* capability
(gather data, author + run code, orchestrate compute, render figures/manuscript), not its bio artifacts.

**The invariant of the fusion:** the two reviewers are not fused. Claude Science produces Evidence and
belief-narrative; the rule engine produces the verdict. Layer, do not blend.

---

## 3. Seam invariants (FUS-1 … FUS-5)

Non-negotiables that make the composition safe. Each now carries its code anchor.

- **FUS-1 (verdict purity).** No LLM in the verdict path. Claude Science may generate Evidence; it may
  never author a `Verdict` or set a `Claim` status. The binding verdict is the Stop-hook
  `sci-adk verify` — offline, model-free, record-derived
  (`src/sci_adk/templates/research-workspace/.claude/hooks/sci-adk/stop-verify-gate.sh`;
  `cli.py:149-156` read-only, no re-run, no LLM). Load-bearing.
- **FUS-2 (record before belief).** The Spec — its per-hypothesis `DecisionRule`, its G1–G5
  declarations — is frozen *before* Claude Science touches data. No success criterion is authored after
  seeing results (anti-HARKing). A frozen Spec is only changed by `amend-spec` (`cli.py:493-503`,
  version+1, mandatory rationale, S5 human-only).
- **FUS-3 (Evidence source, adapter-mediated).** Claude Science attaches only through the connector
  (an MCP server, §6) or operational-layer delegation. The kernel never imports a Claude-Science symbol;
  the F4 lint (`tests/test_kernel_adapter_seam.py`, kernel-cannot-import-adapter) continues to hold.
- **FUS-4 (reviewer demotion).** Claude Science's reviewer agent is an **advisory guard** — peer to
  `evaluator-rigor` / `evaluator-novelty` / `evaluator-validity`
  (`.../research-workspace/.claude/agents/evaluator-*.md`). It flags early; it never grants a pass.
- **FUS-5 (provenance completeness).** Every Evidence item from a Claude Science session carries full
  provenance — generating code, environment, git commit, timestamp, and a message-history reference —
  or it is not admitted as `measured` (`core/evidence.py:128` Provenance; referent-typed validity at
  `core/validity.py`). Because the transport is agent-mediated (§6), this gate is the load-bearing
  enforcement, not a formality.

---

## 4. The three gates (before / during / after)

**Before — Spec freeze.** `sci-adk run proposal.md` (or the Stage-2 `init-spec`) compiles the four-pane
proposal into a frozen Spec. G1–G5 write initial findings to `runs/<id>/science.md` *before any
experiment runs*. `sci-adk prior-work` / `sci-adk novelty` record prior-art and novelty decisions. The
researcher fixes the *design* here, where it is cheap.

**During — Claude Science as execution backend.** Delegate the labor Claude Science is good at: gather
data, author and run experiment code, orchestrate compute, render figures. Its outputs are piped into
the append-only Evidence log via the connector's `append-evidence` tool (§6), provenance intact (FUS-5).
Null and negative results enter as first-class `EvidenceItem`s (`BearingDirection` refutes / inconclusive
/ neutral, `core/evidence.py:87`).

**After — verify is the sole verdict.** The Stop hook runs `sci-adk verify`: the frozen `DecisionRule`
is re-applied to the recorded Evidence (numeric autonomously; non-numeric via a `RecordedJudge` re-reading
recorded verdict trails — no LLM). Per Claim: `REPRODUCED / DIVERGED / UNRESOLVED`, plus a record digest.
Exit 0 iff every recorded claim reproduces; `DIVERGED` blocks the Stop (exit 2) and is traced.

### Workflow swim-lane

```
  sci-adk  (referee lane — deterministic, no-LLM verdict)     Claude Science  (player lane)
  ═════════════════════════════════════════════════════       ════════════════════════════
  ┌──────────────────────────────┐
  │ P1 · Spec freeze             │
  │    frozen Spec · G1–G5 guards│
  └───────────────┬──────────────┘
                  │                                ┌──────────────────────────────┐
                  ├──── delegate ───────────────► │ P2 · Gather + run            │
                  │                                │    connectors·code·compute   │
                  │  ◄── append-evidence (MCP) ──  └──────────────────────────────┘
                  ▼
  ┌──────────────────────────────┐
  │ P3 · Capture Evidence        │
  │    append-only · provenance  │
  └───────────────┬──────────────┘
                  ▼
  ┌──────────────────────────────┐
  │ P4 · Verdict — verify        │  ◄── sole verdict, model-free, Stop-hook
  │    no-LLM · frozen rule      │
  └───────────────┬──────────────┘
                  │  DIVERGED → halt & re-enter (loop)
                  │                                ┌──────────────────────────────┐
                  ├──── delegate ───────────────► │ P5 · Author paper            │
                  │                                │    IMRaD prose · figures     │
                  ▼                                └──────────────────────────────┘
  ┌──────────────────────────────┐
  │ P6 · Package                 │
  │    fidelity gate + bundle    │
  └──────────────────────────────┘
  Boundary: Claude Science produces Evidence + belief-narrative; the rule engine
  produces the verdict. The spine never delegates the verdict path (FUS-1).
```

---

## 5. Data mapping — session output → `EvidenceItem` (the crux)

This thin adapter is the practical crux and the real work of the connector (§6/§7). It runs at the
`append-evidence` tool boundary. If a session output does not map losslessly into the Evidence type
system, the gate leaks.

| Claude Science session output | sci-adk record | Governing rule |
|---|---|---|
| Measured value + generating code | `EvidenceItem(kind=measured)` with `provenance{code, env, commit, ts, msg_ref}` | FUS-5; `core/evidence.py:128` |
| Simulated / generated data | `EvidenceItem` with **formal** referent | Referent-typed validity: cannot ground an empirical `SUPPORTED` claim (`core/validity.py`) |
| Value extracted from a figure | `digitized` `EvidenceItem`, `proposed → verified` gate | Extractor ≠ verifier; never auto-promoted to `measured` (`core/validity.py:61-100`) |
| Literature finding (central claim + quantitative result) | `LITERATURE` `EvidenceItem` | Feeds `claim-novelty-<hyp>`; 2-kind result/method |
| Reviewer-agent flag | Advisory note (not Evidence) | FUS-4 — informs `science.md` (D3), never a Claim |
| Figure / manuscript prose | Belief NARRATIVE input to the render spine | Agent authors IMRaD; engine substitutes `\evval{<id>}{<field>}` / `\status{<hyp>}` FAIL-LOUD (`render/factref.py`) |

**Ingress ≠ judgment (verified in code).** `append-evidence` at write time enforces only the spec-digest
boundary + Pydantic schema (`cli.py:1256-1281`); it does **not** run the validity gate. The validity gate
(`ValidityHalt`) fires at `derive-claim` / `verify` (`cli.py:1319-1323`). This is correct: the record
honestly accepts even mislabeled Evidence (E1), and *belief* is where forgery fails — a synthetic item
cannot yield a SUPPORTED empirical Claim. The connector inherits this two-layer defense for free.

---

## 6. Transport & attachment (D1 / D2 — RESOLVED)

**D2 — transport = a local MCP connector wrapping sci-adk's CLI verbs.** Measured (§13.2): Claude Science
connectors are MCP-powered and users may attach their own MCP servers, including **local Desktop
Extensions**. So sci-adk ships a thin **local** MCP server exposing a curated subset of its existing CLI
verbs as tools; the in-session Claude Science agent calls `append-evidence` (and read-only `status` /
`verify`) directly. The §5 mapping happens at that tool boundary.

- **Local Desktop Extension is preferred over Remote MCP.** Local keeps the record (`runs/<id>/`) on the
  researcher's machine with zero inbound network surface. Remote MCP (Anthropic cloud calls your server
  over HTTPS + OAuth) would expose the record to the internet and add an auth surface — strictly worse for
  a single-researcher local workflow. Reserve remote for a hosted/multi-user deployment.
- **File-drop remains the fallback** when the connector is unavailable: Claude Science writes code + env +
  figures + manuscript to the local/remote filesystem; a watcher maps those into `append-evidence`.

**D1 — attachment = operational layer first.** The session calls sci-adk tools (the connector);
`expert-experimentalist` / the `/sci` hub delegate to the workbench. The adapter-seam `ExperimentFn`
provider (rigor-shell §3.2, capability registry) is a later, lower-priority path — it couples the kernel's
Interface B to the workbench and is not needed for the MVP fusion.

---

## 7. Connector boundary spec (code-grounded)

The MCP connector is a *tool surface*. FUS-1 is preserved by **structure** (the frozen engine + the
Stop-hook), not by the connector — but the connector must still be curated so the session cannot mutate
the frozen criteria or the autonomy carve-outs.

### 7.1 Verb classification

| CLI verb | Connector exposure | Rationale (code) |
|---|---|---|
| `amend-spec` | **BLOCK** | S5 human-only; changes frozen criteria = anti-HARKing hole (`cli.py:493-503`) |
| `init-spec` freeze, `pubreqs` freeze, `pkgreqs` freeze | **BLOCK / human-gate** | Freezing criteria / publishing / package contracts is a human prereg act |
| `append-evidence` | **EXPOSE (write) — MUST enforce `--spec-digest`** | The §5 mapping tool (`cli.py:529-545`); digest is lenient-when-omitted (`cli.py:544`), so the connector must always pass it |
| `execute` | EXPOSE (optional) | Deterministic experiment run, provenance auto-recorded (`cli.py:506`); redundant if the workbench runs its own code and pipes via `append-evidence` |
| `prior-work` / `novelty` / `contested` | EXPOSE | Recording verbs (prereg decisions into the Evidence log) |
| `verify` | **EXPOSE (read-only, advisory)** | No re-run, no LLM (`cli.py:149-156`); binding verify is the Stop-hook |
| `status` | EXPOSE (read-only) | Session-state snapshot |
| `derive-claim` | Exposable (deterministic) — prefer NOT to | Frozen-rule application, no LLM (`cli.py:548-560`); cleaner to leave binding derive+verify to the gate |
| `resolve` | Exposable | Re-entry only; verdict authoring is file-writing + engine-bounded (rigor-shell §5) |

### 7.2 The spec-digest enforcement rule [HARD]

`append-evidence` (and `derive-claim`) accept `--spec-digest`, which fails the verb (exit 2, no write)
on mismatch but is **lenient when omitted** (`cli.py:544`). The connector MUST always pass the recorded
Spec digest, so a session cannot append Evidence against a silently-revised Spec. This is a connector-side
HARD requirement layered on the §6.1 boundary guard.

### 7.3 Why FUS-1 holds without trusting the connector

- The binding verdict is the Stop-hook `sci-adk verify`, which the harness runs on Stop and the session
  cannot suppress. A session-initiated `verify` via the connector is advisory only.
- The connector exposes **no tool that bypasses the deterministic engine**. Belief is produced only by
  applying the frozen `DecisionRule` (numeric) or by the engine bounding a `RecordedJudge` (non-numeric,
  with the F2 trail gate + `proof` human spot-check, rigor-shell §2.3).
- The one LLM entry into belief — the non-numeric Judge verdict (`verdicts/*.json`) — is a *proposal* the
  engine bounds, never a binding verdict.

---

## 8. User scenarios

### Scenario A — mechanistic model + validation study
1. Four-pane proposal → `sci-adk run proposal.md` freezes the Spec; G1–G5 → `science.md`. Researcher
   revises the *design* here.
2. In Claude Science, with the sci-adk connector attached, delegate: *"Gather measured values for this
   compound set, implement this mechanistic model, run predicted-vs-measured regression."* The workbench
   handles data, code, compute, figures — attaching code + environment + message history.
3. The session calls `append-evidence` per result (measured values + provenance, §5). Null/negative
   results recorded as-is.
4. On Stop, the hook runs `sci-adk verify` → per-claim `REPRODUCED / DIVERGED / UNRESOLVED`. A `DIVERGED`
   claim blocks the Stop and is traced.
5. On a clean pass, `sci-adk pubreqs freeze` → `sci-adk package`. A reviewer reproduces the verdict with
   `sci-adk verify` — no Claude, no vendor.

### Scenario B — literature meta-analysis (disciplining the workbench)
1. Spec declares the hypothesis + a `DecisionRule`, frozen before the search; `prior-work` / `novelty`
   record the decisions.
2. Claude Science sub-agents extract central claim + quantitative finding per paper → each becomes a
   `LITERATURE` (or `digitized`) `EvidenceItem` via `append-evidence`. Figure digitization runs the
   `proposed → verified` gate.
3. `sci-adk verify` re-derives the synthesis Claim from the frozen rule; mixed evidence yields
   `contested`. The conclusion holds because the recorded evidence satisfies the rule — not because a
   reviewer agent said so.

---

## 9. Tool-policy delta (append to `design/tool-policy.md`)

**Belief layer — Claude Science permitted:** data gathering, experiment/code authoring, compute
orchestration (HPC / Modal), figure generation, manuscript prose drafting, advisory review (demoted per
FUS-4).

**Record / verdict layer — sci-adk only, Claude Science excluded:** Spec freeze; `DecisionRule`
application; `Claim` status derivation; `Verdict` authoring; `sci-adk verify`; record digest.

**The line:** *Claude Science produces Evidence and belief-narrative; the rule engine produces the
verdict.* Enforced structurally by §7.

---

## 10. Product / positioning

**Bring-your-own-workbench is the moat.** Position sci-adk not as a Claude-Science *add-on* but as a
**vendor-neutral rigor layer** over any workbench. The property that makes `verify` offline and model-free
is what lets it sell "verification not locked to a vendor" — a position Anthropic can never claim for its
own product. That Claude Science exposes *no* programmatic export/API (§13.2) is not a friction for this
design; it makes the connector/file boundary the clean vendor-neutral seam anyway.

**Beachhead — where self-certification is not acceptable:** regulatory submission, contested claims,
replication audit, methods papers. Bench biology is well served by the workbench's LLM reviewer; sci-adk
is decisive where third-party reproduction is required.

**One-line framing (README / JOSS):** *A rigor layer that judges the claims produced by any agentic
workbench with a deterministic, vendor-independent verdict a third party can reproduce. Where a reviewer
agent self-corrects, sci-adk adjudicates against frozen criteria.*

---

## 11. Risks & disciplines

- **The seduction of the second reviewer.** With a capable workbench in the loop, the pull to "let it
  verify too" is strong — exactly the self-certification sci-adk refuses. FUS-1 + §7 are the guard.
- **Adapter fidelity is the operational risk (§5).** If session output does not map losslessly to
  `EvidenceItem`, the gate leaks. The thin adapter, not the kernel, is where correctness lives.
- **Provenance `msg_ref` — raw material confirmed, export stability is the residual (FUS-5).** Measured
  2026-07-01: Claude Science attaches to *every* artifact the generating code, the environment, a
  plain-language description, **and the conversation that led there** (§13.2) — a near-1:1 match to
  sci-adk's `Provenance` (code_ref / env / description / msg_ref). The residual risk is narrower than v0.1
  feared: not "does the reference exist" (it does) but "does the connector capture it as a stable, exportable
  field." Confirm at build time; the `measured` gate must reject items lacking it.
- **Strategic — Anthropic adds a deterministic verify mode.** Low likelihood (against an LLM-native
  product). Defense: standardize the record/belief type system + G1–G5 as a *vendor-neutral standard* via
  the JOSS paper, so the moat is a standard, not code.
- **Distribution asymmetry.** Millions of workbench users vs. a single-star repo. Path is not "compete for
  the same user" but "the rigor layer serious labs / journals / regulators bolt on."

---

## 12. Shippable artifacts

- **(a) sci-adk MCP connector (local Desktop Extension).** A thin local MCP server wrapping the §7.1
  exposed verbs, enforcing §7.2 spec-digest. This is the §5 adapter. Directly reuses the existing CLI.
  *Status (2026-07-01): BUILT. The SDK-free boundary core is at `src/sci_adk/adapter/connector.py`
  (default-deny allowlist, `append-evidence` digest requirement, read-only classification), and the MCP
  wire transport (stdio Desktop Extension) is at `src/sci_adk/adapter/connector_server.py` — a FastMCP
  server exposing `append_evidence` / `verify` / `status`, capturing the CLI's stdout so it cannot corrupt
  the JSON-RPC stream. Console entry `sci-adk-connector`; `mcp` is an optional extra
  (`pip install -e ".[connector]"`, user-approved 2026-07-01, recorded in `design/tool-policy.md`). Tested
  by `tests/test_connector_boundary.py` + `tests/test_connector_server.py`.*
- **(b) `init-session` Stop-hook template.** Already exists (`stop-verify-gate.sh`); the fusion packages it
  as the one-command way to turn any Claude Science project into a gated one — *"done" requires passing
  `verify`.*

---

## 13. Verification appendix (measured 2026-07-01)

### 13.1 Architectural premises — all CONFIRMED in source
- CLI verbs (run/verify/append-evidence/prior-work/novelty/pubreqs/package/init-session/render/resolve +
  more): `src/sci_adk/cli.py`.
- F4 kernel⊥adapter lint: `tests/test_kernel_adapter_seam.py` (asserts kernel modules never import
  `sci_adk.adapter`).
- Referent-typed validity: `src/sci_adk/core/validity.py` (`check_evidence_adequacy`, `ValidityHalt`).
- EvidenceItem: `src/sci_adk/core/evidence.py` (`EvidenceKind` incl. MEASURED/DIGITIZED/LITERATURE:30;
  `BearingDirection`:87; `Provenance`:128).
- Digitized proposed→verified gate: `src/sci_adk/core/validity.py:61-100` (extractor ≠ verifier).
- `\evval`/`\status` FAIL-LOUD render: `src/sci_adk/render/factref.py`; verify residual-macro gate at
  `cli.py:514`.
- Stop-hook sole verdict: `.../research-workspace/.claude/hooks/sci-adk/stop-verify-gate.sh` (exit 2 blocks
  Stop when a recorded conclusion fails `sci-adk verify`).
- Advisory guards: `.../research-workspace/.claude/agents/evaluator-{rigor,novelty,validity}.md`.
- Science guards G1–G5 → `runs/<id>/science.md`: `src/sci_adk/loop/compiler.py` +
  `src/sci_adk/core/spec_science.py`.

### 13.2 External facts — measured via web (sources below)
- Claude Science = interactive workbench, local macOS/Linux or remote over SSH/HPC; **no public
  programmatic/API/export surface**.
- Connectors are **MCP-powered**; users can **build and connect their own MCP servers** — Remote MCP
  (Streamable HTTP from Anthropic cloud) or **local Desktop Extensions**. Helix exposed genomic data to
  Claude Science via an MCP server (existence proof).
- Available on Pro/Max/Team/Enterprise (beta); Team/Enterprise need admin enablement.
- Reviewer agent checks citations + calculations, flags untraceable numbers + figures that don't match
  their code, self-corrects.
- Modal = built-in compute connector (Settings → connect Modal workspace).
- Heavily life-sciences focused (proteins/genomics/BioNeMo/UniProt/PDB/ChEMBL).

Sources:
- Anthropic — Claude Science: https://www.anthropic.com/news/claude-science-ai-workbench
- Claude Science beta: https://claude.com/product/claude-science
- Build custom connectors via remote MCP: https://support.claude.com/en/articles/11503834-build-custom-connectors-via-remote-mcp-servers
- Get started with custom connectors (remote MCP): https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp
- Modal × Claude Science: https://modal.com/blog/modal-integration-brings-scalable-compute-to-claude-science
- Claude Science provenance (per-artifact code + env + description + conversation): https://coursiv.io/blog/claude-science

### 13.3 Validation record (2026-07-01, before commit)

The two load-bearing behavioral claims are not merely logic-level — they are **test-proven** against the
current tree (172 tests green in the boundary subset):

- **§5 forgery defense** — a synthetic / generated Evidence item cannot yield a SUPPORTED empirical Claim:
  `tests/test_evidence_validity.py::test_synthetic_proxy_on_empirical_halts`,
  `::test_synthetic_proxy_on_empirical_halts_even_when_neutral`,
  `::test_empirical_binding_with_no_measured_halts`, `::test_empirical_binding_with_none_source_halts`
  (referent frozen, fail-closed default `empirical`, `ValidityHalt` at the Evidence→Claim chokepoint).
- **§7.2 spec-digest boundary** — a wrong `--spec-digest` exits 2 and writes nothing; absent digest is
  lenient (backward-compat): `tests/test_spec_digest_boundary.py::test_append_evidence_wrong_digest_blocks_and_writes_nothing`,
  `::test_append_evidence_correct_digest_succeeds`. The lenient-when-omitted behavior is confirmed —
  **justifying the §7.2 HARD requirement that the connector always pass the digest.**
- **FUS-5 provenance** — Claude Science's own per-artifact provenance (code + env + description +
  conversation) supplies the raw material for the `measured` gate (§13.2). Residual: field-level export
  stability, a build-time measurement.

Not re-validated here (accepted as already covered / design decisions, not behavioral claims): F4 lint,
digitized gate, verify/hook (all green in the same run); D3 advisory-channel choice; remote-MCP security.

---

## 14. Open decisions

- **D1 attachment — RESOLVED:** operational layer first; adapter `ExperimentFn` provider later.
- **D2 transport — RESOLVED:** local MCP connector (Desktop Extension) wrapping CLI verbs; file-drop
  fallback.
- **D3 advisory channel — OPEN:** does the reviewer-agent flag feed into `runs/<id>/science.md` alongside
  G1–G5, or a separate channel, to keep guard provenance legible? (Recommendation to decide at build time:
  separate `science.advisory.md` so engine-authored G1–G5 provenance is not intermixed with LLM-authored
  flags.)

---

## 15. Registering the connector with Claude Science (local Desktop Extension)

Verified live 2026-07-01 against Claude Science `operon` (`0.1.0-dev.20260630`). Claude Science runs
local MCP servers inside a bubblewrap sandbox. Registration is UI-driven (Capabilities → Connectors →
Custom → **+ Add connector → Local command**; the UI also offers Remote URL and Browse Directory); there
is no CLI verb and no hand-editable server list (custom servers live in the daemon's DB). Two sandbox
facts drive the setup:

1. **The home dir is hidden from the MCP sandbox.** Grant the paths the server needs in
   `~/.claude-science/config.toml`, then restart the daemon (`operon stop && operon serve --detached
   --no-browser`; re-login via `operon url`):
   ```toml
   [sandbox]
   user_read_paths  = ["<launcher dir>", "<user site-packages>", "<sci-adk repo>"]
   user_write_paths = ["<workspace>/runs"]
   ```
2. **The sandbox does not process the user-site `.pth`,** so an editable install's `import sci_adk` fails
   with `ModuleNotFoundError` even when the files are granted. Point the connector's **Command** at a tiny
   launcher that sets `sys.path` explicitly before importing (machine-specific, git-ignored):
   ```python
   import sys
   sys.path.insert(0, "<user site-packages>"); sys.path.insert(0, "<sci-adk>/src")
   from sci_adk.adapter.connector_server import main; main()
   ```
   A non-editable, system-path install (`/usr/local`, `/opt`) needs neither workaround — the sandbox sees
   system paths by default. The launcher is the zero-sudo, dev-friendly path.

Once loaded, the connector exposes `append_evidence` / `verify` / `status`. `append_evidence` writes (and
any out-of-sandbox host access) surface as approval cards under Customize → Permissions. Live smoke test:
`status` → exit 0 + record snapshot; `verify` → the no-LLM audit (UNRESOLVED for an un-judged claim, plus
the record digest); `append_evidence` with a wrong `spec_digest` → exit 2, refused, nothing written (§7.2).

---

Version: 0.2
Source: fusion investigation 2026-07-01 (premises verified against source; D1/D2 resolved from measured
Claude Science integration surface; §15 added after the live end-to-end run). Supersedes v0.1 DRAFT.
