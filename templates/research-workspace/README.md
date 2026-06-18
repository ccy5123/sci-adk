# sci-adk Research-Workspace Enforcement Kit

This kit turns an ordinary Claude Code project into a **sci-adk research
workspace**: a session that *stays* in the sci-adk discipline (record vs
belief; the engine judges, not the player) instead of drifting out of it.

It does this in the harness, not the model's memory — a prompt decays as the
context grows; a hook is re-applied deterministically every turn. See
`design/research-session-enforcement.md` (in the sci-adk repo) for the full
architecture.

## What's in the kit

```
templates/research-workspace/
├── CLAUDE.md                                   # always-loaded research protocol
├── README.md                                   # this file
└── .claude/
    ├── settings.json                           # wires the two hooks + persona
    ├── commands/research.md                    # /research entry point
    ├── output-styles/researcher/researcher.md  # the researcher persona
    └── hooks/sci-adk/
        ├── stop-verify-gate.sh                 # HARD gate: Stop -> sci-adk verify
        └── reanchor.sh                         # re-anchor: UserPromptSubmit -> sci-adk status
```

- **`stop-verify-gate.sh`** (Stop hook) — blocks ending the session while any
  run that has recorded belief (a `runs/<id>/claims/*.json`) fails
  `sci-adk verify`. "Done" stops meaning "the agent said done" and starts
  meaning "`verify` reproduces the recorded belief".
- **`reanchor.sh`** (UserPromptSubmit hook) — every turn, re-injects the
  protocol reminder + the current run's `sci-adk status` into context. The
  direct antidote to compaction drift.
- **`researcher` output style** — the always-on persona contract.
- **`/research`** — the single entry point; "using it correctly" collapses to
  one action.

## Install

1. **Make sure `sci-adk` is on PATH** in the shell Claude Code uses. From the
   sci-adk repo:
   ```bash
   pip install -e .        # provides the `sci-adk` console script
   sci-adk --help          # confirm it resolves
   ```
   (The hooks degrade to a no-op if `sci-adk` is absent — a missing tool never
   bricks a session — but the gate only bites when `sci-adk` is reachable.)

2. **Copy the kit into your research workspace** (the project where research is
   actually done — NOT the sci-adk build repo):
   ```bash
   cp -r templates/research-workspace/.claude  /path/to/research-workspace/.claude
   cp    templates/research-workspace/CLAUDE.md /path/to/research-workspace/CLAUDE.md
   ```
   If the target already has a `.claude/settings.json`, merge the `hooks.Stop`,
   `hooks.UserPromptSubmit`, and `outputStyle` keys from this kit's
   `settings.json` into it rather than overwriting.

3. **Verify the hooks are executable** (they ship with the executable bit set;
   re-apply if your copy step stripped it):
   ```bash
   chmod +x /path/to/research-workspace/.claude/hooks/sci-adk/*.sh
   ```

4. **Start a session** in the research workspace and run
   `/research <proposal.md | research goal>`.

## Two-environment warning [HARD]

Install this into a **research** workspace, never into the sci-adk **build**
repo while that repo is still the workspace for developing sci-adk itself: the
research `verify` gate and the build harness's own Stop/quality hooks would
fight. Research-on-sci-adk, if ever wanted, gets its own separate workspace.

## Coming in Phase 3

A `sci-adk init-session <dir>` installer (design doc D3) will do the copy +
`settings.json` merge in one version-pinned command, keeping the hook and
`verify` contracts in sync with the sci-adk release. Until then, install
manually as above.
