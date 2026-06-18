# Research-Session Enforcement Architecture

> Status: v0.2 DESIGN (2026-06-18) — architecture + decisions D1-D4 resolved; implementation pending
> Purpose: make a Claude Code research session *stay* in the sci-adk discipline instead of drifting out of it
> Scope: design only. No code/hook/harness is changed by this document.

---

## 1. Problem

sci-adk is used by pointing a Claude session at the repo ("read the constitution and run the
research") and then driving `sci-adk run / resolve / verify`. In practice the session **drifts**:
it uses sci-adk for a while, then reverts to ad-hoc "the agent just concludes" behaviour.

Two root causes:

1. **A prompt is advice, not a control surface.** Instructions delivered once (a CLAUDE.md read,
   a first-message brief) lose weight as the context grows and as auto-compaction summarises away
   the early turns. The model reverts to its default behaviour. This is expected — adherence to a
   far-back instruction decays.
2. **"The agent remembers to use sci-adk" re-inserts belief into the agent.** That is the exact
   thing sci-adk exists to remove (record vs belief; *the engine judges, not the player*). If
   discipline depends on the agent *choosing* to invoke the tool, the discipline is only as strong
   as the agent's memory — which decays (cause 1).

**Therefore**: enforcement must live in the **harness** (deterministic, re-applied every turn,
unskippable by the model), not in the model's memory. And sci-adk already owns the deterministic
gate — `sci-adk verify` exits non-zero when recorded belief does not reproduce from the record
(README: "Exit 0 iff every recorded claim reproduces"). Enforcement = wiring that gate (and a
re-anchor) into Claude Code's hook layer.

---

## 2. Reference model — how MoAI-ADK enforces (measured in this repo)

MoAI-ADK is itself a Claude Code harness with strong, non-drifting discipline. Its enforcement is a
single repeatable pattern, worth copying:

**`settings.json` wires ~25 hook events → each to a thin `.sh` wrapper → the wrapper pipes the
event's stdin JSON to the `moai` binary (`moai hook <event>`) and propagates the exit code. Exit 2
= BLOCK.** Policy is data (config), judgement is the binary, wiring is `settings.json`.

| Lever | Where (this repo) | What it enforces |
|-------|-------------------|------------------|
| Hook wiring | `.claude/settings.json` (`hooks` block) | ~25 events; 9 can block via exit 2 (PreToolUse, Stop, SubagentStop, UserPromptSubmit, TeammateIdle, TaskCompleted, ...) |
| Thin hook wrappers | `.claude/hooks/moai/handle-*.sh` | each `exec moai hook <event> < stdin`; graceful exit 0 if the binary is absent |
| Config-driven thresholds | `.moai/config/sections/quality.yaml` (`enforce_quality: true`, `lsp_quality_gates.run.max_errors: 0`), `gate.yaml` | the binary reads these; breaching them → exit 2 |
| Persona contract | `.claude/output-styles/moai/moai.md` + `settings.json` `outputStyle: "MoAI"` | an always-on persona (4-stage state machine, cannot-do limits) applied to every turn |
| Path-anchored rules | `.claude/rules/moai/**` with path-glob frontmatter | a rule auto-loads whenever a matching file is touched — deterministic re-anchoring |
| Single entry point | `.claude/commands/moai/*.md` → `Skill("moai")` (<20 LOC, audited by a Go test) | one correct entry; the thin-command pattern cannot rot (test-enforced) |

Key caveat (honest record): the *decision logic* inside `moai hook stop` / `teammate-idle` lives in
the compiled `moai` Go binary, not in this repo — so we can quote the **wiring** (visible) and the
**config-declared intent**, but not the binary's exact branches. The wrappers degrade to exit 0 when
the binary is missing, so a missing tool never bricks a session.

---

## 3. sci-adk enforcement architecture (the mapping)

The same pattern, with `sci-adk` standing in for the `moai` binary. sci-adk already provides the
"exit-2 engine" half (`verify` + the CLI halts: ConfigHalt / ValidityHalt). What is missing is the
wiring + a persona + an entry point. Five layers, strongest first:

### Layer 1 — Hard gate: `Stop` hook → `sci-adk verify`
A `Stop` hook runs `sci-adk verify <run>`; if any recorded Claim is `DIVERGED` or a checkpoint is
unresolved, the hook exits 2 → **the session cannot end while its belief is not reproducible from the
record**. This is the sci-adk-native equivalent of MoAI's `Stop → quality.yaml` gate, and it is the
spine: "done" stops meaning "the agent said done" and starts meaning "`verify` reproduces."

### Layer 2 — Re-anchor: `UserPromptSubmit` hook
On every user turn, inject a short protocol reminder **plus the current run state** (open
checkpoints, unresolved claims, pending halts) into context. This re-delivers the discipline each
turn rather than relying on the model to remember it — the direct antidote to compaction drift.
(Requires a read-only state read; see Open Question O1.)

### Layer 3 — Persona: a `researcher` output style
An always-on output style encoding the contract: *record vs belief*, *referee not player*, *null
results are results*, *no conclusion outside the engine*. Mirrors `outputStyle: "MoAI"`. Soft, but
loaded every turn (unlike a one-shot prompt).

### Layer 4 — Single entry point: `/research` thin command
`/research <proposal>` → a skill that drives `run → (experiments) → resolve → verify`. "Using it
correctly" collapses to one action (invoke the skill), not sustained vigilance. Mirrors `/moai`.

### Layer 5 — Policy = the Spec's own DecisionRules + halts (already exists)
sci-adk's per-hypothesis `DecisionRule` and the validity/novelty/evidence halts ARE the
config-equivalent of `quality.yaml` — the policy the gate enforces. No new policy layer is needed;
Layers 1-2 just make that policy unskippable.

| MoAI lever | sci-adk equivalent | status |
|------------|--------------------|--------|
| `Stop → moai hook stop → quality.yaml` | `Stop → sci-adk verify <run>` (exit 2 on DIVERGED/unresolved) | gate exists; wrapper missing |
| `UserPromptSubmit → inject HARD rules` | `UserPromptSubmit → inject protocol + run state` | wrapper + read-only state verb missing |
| `quality.yaml enforce_quality/max_errors` | Spec `DecisionRule` + ConfigHalt/ValidityHalt | exists |
| `outputStyle: MoAI` persona | `researcher` output style | missing |
| `/moai → Skill`, Go-test-audited | `/research → skill` | missing |

---

## 4. The two-environment boundary [HARD]

These enforcement artifacts govern a **research session**, which is a *different environment* from
sci-adk's own build harness. Per the sci-adk constitution's two-environment rule:

- They MUST live in the **research workspace's** `.claude/` (the project where research is actually
  done), NOT in this repo's MoAI build harness (`.claude/`, root `CLAUDE.md`) — that harness stays
  untouched.
- sci-adk SHIPS them as templates the research workspace installs. Proposed home:
  `templates/research-workspace/.claude/` (hooks, settings fragment, output style, `/research`
  command) — installed manually or by a future `sci-adk init-session` verb (Open Question O3).
- Dogfooding caveat: do **not** install the research gate into *this* repo while it is still the
  build workspace for sci-adk — the MoAI Stop/quality hooks and the sci-adk verify gate would fight.
  Research-on-sci-adk, if ever wanted, gets its own workspace.

---

## 5. What sci-adk already provides vs. what is missing

| Piece | Status |
|-------|--------|
| Deterministic gate (`sci-adk verify`, exit 0 iff reproduced + record digest) | EXISTS (`loop/verify.py`) |
| Deterministic refusals (ConfigHalt, ValidityHalt, novelty/evidence-validity, prior-work) | EXISTS |
| Append-only Evidence / revisable Claim / frozen Spec | EXISTS |
| Read-only **session-state** read for the re-anchor (open checkpoints, unresolved claims) | DECIDED (D1) — add a terse read-only `sci-adk status <run>` verb; to build |
| `Stop` + `UserPromptSubmit` hook wrappers | MISSING |
| `settings.json` fragment wiring them + `outputStyle` | MISSING |
| `researcher` output style | MISSING |
| `/research` thin command + skill | MISSING |
| Template packaging + installer | DECIDED (D3) — `templates/research-workspace/` + `sci-adk init-session <dir>`; to build |

The gap is *wiring + packaging*, not a new engine. This is why the verify-gate is high-leverage:
the hard part (a deterministic, tamper-evident gate) is already built.

---

## 6. Resolved design decisions (D1–D4, decided 2026-06-18)

- **D1 — Re-anchor data source → a new read-only `sci-adk status <run>` verb.** It prints a terse
  session-state summary (open checkpoints, unresolved/contested claims, pending halts); the
  `UserPromptSubmit` hook echoes it. Keeps the state-reading logic in one tested place (mirrors the
  `verify` precedent and MoAI's "logic in the binary, wrapper is thin"), not parsed in bash.
- **D2 — Stop-gate strictness → block only when a run dir exists AND has ≥1 recorded Claim.**
  Exploratory turns with no run pass (exit 0); the verify gate bites only when there is recorded
  belief to protect — low noise, so the gate stays enabled. The "you never started a run" nudge is
  Layer 2 (re-anchor) + Layer 4 (`/research`), not a hard Stop block.
- **D3 — Distribution → `templates/research-workspace/` + a `sci-adk init-session <dir>` installer.**
  The kit ships as templates and installs (copy + settings.json merge) with one command, version-
  pinned to the sci-adk release so the hook/`verify` contracts stay in sync. The settings.json merge
  is the fiddly part; phasing (ship templates first, add the installer second) is acceptable.
- **D4 — Hook portability → bash `.sh` (WSL/bash).** Matches the current WSL ubuntu setup and the
  MoAI wrapper pattern; the hook only needs `sci-adk` reachable from the shell. Revisit only if
  research sessions move to a non-WSL machine (then a Python-based portable hook).

These decisions imply two new, additive sci-adk CLI verbs to build (no kernel change): a read-only
`sci-adk status <run>` (D1) and `sci-adk init-session <dir>` (D3).

---

## 7. Non-goals / honest caveats

- The gate enforces **reproducibility of recorded belief**, not the *correctness of the science* —
  that remains the judge's job (a `verify`-passing run can still rest on a weak rubric). The gate
  stops *drift and self-certification*, not bad judgement.
- Hooks degrade gracefully: if `sci-adk` is not on PATH the wrapper exits 0, so a missing tool never
  bricks a session (same contract as the MoAI wrappers).
- This is enforcement of *process*, layered on top of the existing *substance* gates (DecisionRule,
  halts). It adds no new scientific authority; it makes the existing authority unskippable.

---

## 8. Reference anchors (measured 2026-06-18)

- MoAI hook wiring: `.claude/settings.json` (`hooks` block, `outputStyle`, `permissions`).
- MoAI thin wrappers: `.claude/hooks/moai/handle-stop.sh`, `handle-user-prompt-submit.sh`
  (`exec moai hook <event> < stdin`).
- MoAI quality policy: `.moai/config/sections/quality.yaml` (`enforce_quality`,
  `lsp_quality_gates.run.max_errors: 0`), `gate.yaml`.
- MoAI persona: `.claude/output-styles/moai/moai.md` (`outputStyle: "MoAI"`).
- MoAI entry point: `.claude/commands/moai/*.md` → `Skill("moai")` (thin-command pattern).
- sci-adk gate: `sci-adk verify` (README §Usage; `src/sci_adk/loop/verify.py`; exit 0 iff all
  claims reproduce + record digest).

---

Version: 0.2.0
Status: DESIGN (decisions D1-D4 resolved; implementation pending)
Relates to: `design/rigor-shell-architecture.md` (kernel + seam), `.claude/rules/sci-adk-constitution.md` (two-environment rule), `design/tool-policy.md`.
