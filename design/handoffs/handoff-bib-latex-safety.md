# Handoff — bib LaTeX-safety (session 2026-06-30)

## Goal

Root-fix the failure where a BibTeX `&amp;` (and friends) breaks `pdflatex`/`bibtex`.
A real manuscript (IEAM-P8) hit it. The fix had to be **systemic** (every future bib clean),
not a one-off edit.

## The flow it establishes (this is the intended design)

```
DOI list   (Claude web_search — discovery is an agent action, NOT a code module;
            only the RESULT list is recorded, not the search rationale — by design)
   │  e.g. dois.txt   (any source: web_search, manual, a spreadsheet column)
   ▼
paperforge bib  dois.txt -o out/          ← `bib` subcommand = references.bib ONLY,
   │                                          no PDF download (orchestrator bib-only path)
   │   • doi.org content-negotiation → registrar's canonical BibTeX (never fabricated)
   │   • latex_safety.sanitize: &amp;→\&, <i>→\textit{}, U+2005-class spaces→ASCII,
   │       first-author <Surname><Year> diacritic keys (Könemann→Konemann)
   │       — PRESERVES \&, en/em-dash, Latin-1 accents (ç ö ø)
   ▼
out/references.bib   (LaTeX-safe by construction; isolated compile = 0 errors)
   │
   ▼  paper-writing / sci-adk verify
sci-adk Phase 2 gate   (re-checks LaTeX-safety; safety net for hand-authored / non-paperforge bibs)
```

`paperforge bib` records each DOI's origin in `out/manifest.csv` (`origin` column:
`dois.txt:lineN` / `cli`); the sci-adk acquire path additionally records a LITERATURE
EvidenceItem under `runs/<spec>/evidence/`.

## What shipped (3 repos, all pushed to github.com/ccy5123/*)

| repo | commit | change |
|------|--------|--------|
| **sci-adk** | `a851e78` | **Phase 2 gate.** `bib_latex_safety_problems()` in `render/pkgreqs_checks.py` (PURE; per-entry HTML entity / `<tag>` / bare `&` / non-standard-Unicode-space detectors via `_HTML_ENTITY_RE`, `_HTML_TAG_RE`, `_BARE_AMP_RE`, `_nonstandard_space_codepoints` using `unicodedata.category=="Zs"`). Wired into `loop/verify.py` per-run (~958) + package (~1185) as blocking FAIL (OD-4: names entry, never rewrites). 6 TDD tests in `tests/test_pkgreqs.py`. Suite 1374 passed, ruff clean. |
| **IEAM-P8** | `7cf1804` | references.bib regenerated via `paperforge bib` (LaTeX-safe + first-author keys + accurate metadata: Lee2026, current Baussant DOI, Crossref author names). main.tex `\citep` synced (Lee2025→Lee2026; synthetic keys OliverNiimi1985→Oliver1985 etc.). Isolated bibtex+pdflatex 0 errors; cite-resolution 17/17. NOTE: this repo IS on GitHub now (old memory said it wasn't). |
| **paperforge** | `b30306d` (user) | `latex_safety.sanitize` + `assert_seam_closed` in `bibtex.py`; `sourcing.py` (habanero wrapper = single network boundary); `bib`/`download`/`all` subcommands. The user implemented this from `TASK-bibtex-latex-escape.md` (left untracked in the repo root — clean up or commit as a record). |

## Key findings / gotchas (so the next session doesn't relearn them)

- **betterbib is REJECTED.** PyPI 7.x is a `stonefish`-licensed compiled binary that fails to
  import; MIT versions are gone from PyPI. Do not reach for it. paperforge uses `habanero` +
  `pylatexenc`-style transforms instead.
- **paperforge bib = doi.org content-negotiation**, not JSON reconstruction — preserves the
  "never fabricate / registrar canonical" property. sanitize touches field values only.
- **The Phase 2 gate has teeth on old runs**: any pre-existing `runs/*/paper/references.bib`
  that an agent built by hand with `&amp;` will now FAIL re-verify — regenerate via `paperforge bib`.
- The non-ASCII split that matters: U+2005-class spaces (Zs) and entities/tags are unsafe;
  en-dash U+2013 / em-dash / Latin-1 accents are SAFE (inputenc utf8) — never normalize those.

## Remaining (not blockers)

1. **betterbib install residue** — the betterbib probe upgraded WSL global `rich` 10→15 and broke
   `jisho-api` deps. betterbib + stonefish pkgs are now unused. Decide whether to `pip uninstall`
   and restore `rich` (user's global env — review-gate it).
2. **paperforge `TASK-bibtex-latex-escape.md`** (+ `out/`) — untracked. Commit as a record or remove.
3. **memory** — `ieam-p8-baf-prediction` says "NOT on GitHub"; it now has an `origin`. Update.
