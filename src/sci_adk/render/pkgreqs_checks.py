"""
PURE deterministic checkers for the workspace-PACKAGE gate (design/near-submission-package.md
§3). The package-level siblings of ``render/pubreqs_checks.py`` -- the checks that are SPECIFIC
to the merged-manuscript package (layout presence, cite-key resolution, abstract word count,
figure presence, README submission-readiness), composed with the per-run checkers REUSED from
``pubreqs_checks`` / ``consistency`` / ``paper`` / ``factref``.

Like ``pubreqs_checks`` this module is PURE (text/paths in, verdict out): no LLM, no recompile,
no network. ``loop/verify._check_package_requirements`` orchestrates these against the FROZEN
``pkgreqs.json`` + the assembled ``package/`` and reports the failures the contract declared.

It lives in ``render/`` (the kernel) and imports only stdlib + ``re`` + its sibling render
checkers -- nothing from ``adapter`` / ``loop`` (the F4 seam). It is read-only over the
package's ``.tex`` / ``.bib`` / folder tree, exactly as the per-run paper gates are over
``paper/``.

The checks (design §3 table):
  - :func:`layout_problems`        -- the 6 folders + MANIFEST.md + README.md present;
  - :func:`cite_resolution_problems` -- every ``\\cite*`` key in main.tex resolves in
    references.bib;
  - :func:`abstract_word_count`    -- the word count over the ``\\begin{abstract}`` body;
  - :func:`abstract_max_words_problems` -- that count <= the venue abstract limit;
  - :func:`figure_presence_problems` -- every ``\\includegraphics`` in main.tex resolves to a
    co-located file (the package's manuscript ``figures/`` dir);
  - :func:`readme_submission_readiness_problems` -- the README carries a submission-readiness
    section.

The compile-integrity (ref/label), required-sections, reference-style, tool-vocabulary, and
value-fidelity checks are NOT re-implemented here -- they are the SAME pure checkers the per-run
paper gates use (``consistency.check_latex_ref_consistency``,
``pubreqs_checks.required_sections_problems`` / ``reference_style_problems``,
``paper.check_paper_tool_vocabulary``, ``factref.find_unresolved_factrefs``), invoked over
main.tex/si.tex by the verify orchestrator. Reusing them keeps a single source of truth for
what "compiles", "names the science", and "re-derives from the record" mean.

Reference: design/near-submission-package.md §3, src/sci_adk/render/pubreqs_checks.py (the
per-run sibling), src/sci_adk/render/package.py (the assembler that produces the layout).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from sci_adk.render.pubreqs_checks import word_count

# -- layout ------------------------------------------------------------------

# The 6 canonical package folders (design §2 [2]). The CANONICAL definition lives here in the
# pure gate module (kernel-side, no loop dependency) so both the gate and the assembler
# (render/package.py, which imports it from here) share one source of truth without the
# assembler's verify_run dependency pulling a circular import into the gate.
PACKAGE_FOLDERS: tuple[str, ...] = (
    "01_manuscript",
    "02_data",
    "03_figures",
    "04_scripts",
    "05_inputs",
    "06_provenance",
)

# The two root index files every package must carry (design §2 [2]).
_ROOT_FILES: tuple[str, ...] = ("MANIFEST.md", "README.md")


def layout_problems(package_dir: Path) -> List[str]:
    """Every missing canonical folder / root file (design §3 layout).

    PURE-ish (a directory listing). The package must carry the 6 numbered folders
    (``01_manuscript`` ... ``06_provenance``) plus ``MANIFEST.md`` + ``README.md`` at its root.
    Returns one problem line per missing element (empty = the layout is present).
    """
    problems: List[str] = []
    for folder in PACKAGE_FOLDERS:
        if not (package_dir / folder).is_dir():
            problems.append(f"package layout: missing folder {folder}/")
    for name in _ROOT_FILES:
        if not (package_dir / name).is_file():
            problems.append(f"package layout: missing {name}")
    return problems


# -- citation resolution -----------------------------------------------------

# A \cite / \citep / \citet / \citeauthor / ... key group: capture the braces argument, then
# split on commas (a \cite{a,b,c} is three keys). Matches any \cite-family command.
_CITE_RE = re.compile(r"\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{([^{}]+)\}")
# A bib entry key: @article{KEY, / @book{ KEY , -- the token after the entry-type brace.
_BIB_ENTRY_RE = re.compile(r"@\w+\{\s*([^,\s}]+)\s*,")


def cited_keys(tex: str) -> List[str]:
    """Every distinct ``\\cite*`` key referenced in ``tex`` (sorted). PURE."""
    keys: set[str] = set()
    for group in _CITE_RE.findall(tex):
        for key in group.split(","):
            k = key.strip()
            if k:
                keys.add(k)
    return sorted(keys)


def bib_keys(bib: str) -> List[str]:
    """Every distinct entry key defined in a BibTeX ``bib`` string (sorted). PURE."""
    return sorted({k.strip() for k in _BIB_ENTRY_RE.findall(bib)})


def cite_resolution_problems(tex: str, bib: str) -> List[str]:
    """Every ``\\cite*`` key in ``tex`` that does NOT resolve in ``bib`` (design §3 citations).

    PURE + deterministic. Returns one problem line naming the unresolved cite keys (empty =
    every cite key resolves). An UNCITED bib entry (defined, never cited) is benign and NOT
    reported -- the gate is "every citation has a reference", not "every reference is cited".
    """
    cited = set(cited_keys(tex))
    defined = set(bib_keys(bib))
    missing = sorted(cited - defined)
    if not missing:
        return []
    return [
        "citations: cite key(s) with no entry in references.bib: " + ", ".join(missing)
    ]


# -- abstract word count -----------------------------------------------------

# The \begin{abstract}...\end{abstract} body (the venue abstract whose length venues cap).
_ABSTRACT_BODY_RE = re.compile(
    r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.DOTALL
)


def abstract_body(tex: str) -> Optional[str]:
    """The first ``\\begin{abstract}...\\end{abstract}`` body in ``tex``, or None. PURE."""
    m = _ABSTRACT_BODY_RE.search(tex)
    return m.group(1) if m else None


def abstract_word_count(tex: str) -> Optional[int]:
    """The deterministic word count over the abstract body (or None if no abstract env). PURE.

    Reuses the conservative LaTeX-prose :func:`word_count` (strips control words / braces /
    math) so the count matches the per-run word-count gate's tokeniser -- a single source of
    truth for "how many words".
    """
    body = abstract_body(tex)
    if body is None:
        return None
    return word_count(body)


def abstract_max_words_problems(tex: str, abstract_max_words: Optional[int]) -> List[str]:
    """A single problem line iff the abstract exceeds ``abstract_max_words`` (design §3).

    PURE + deterministic. ``None`` skips the check. When the limit is set but the manuscript
    has NO ``\\begin{abstract}`` env, that is NOT this gate's failure (the required_sections
    gate is what enforces an Abstract is present); this gate measures an abstract that exists.
    Returns ``[]`` when within the limit or no abstract to measure.
    """
    if abstract_max_words is None:
        return []
    count = abstract_word_count(tex)
    if count is None or count <= abstract_max_words:
        return []
    return [
        f"abstract word count: {count} words (> limit {abstract_max_words})"
    ]


# -- figure presence ---------------------------------------------------------

_INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^{}]+)\}")


def figure_presence_problems(tex: str, manuscript_dir: Path) -> List[str]:
    """Every ``\\includegraphics`` path in ``tex`` with no co-located file (design §3 compile).

    PURE-ish + deterministic. The merged manuscript co-locates its figures beside main.tex
    (e.g. ``figures/fig1.png``); a ``\\includegraphics`` whose path does not resolve under
    ``manuscript_dir`` would compile to a missing-figure error. Returns one problem line per
    missing figure (empty = every figure resolves / the manuscript has no figures).
    """
    problems: List[str] = []
    for path_in_tex in _INCLUDEGRAPHICS_RE.findall(tex):
        rel = path_in_tex.strip()
        # LaTeX may omit the extension; accept an exact match OR any extension variant.
        candidate = manuscript_dir / rel
        if candidate.is_file():
            continue
        if _resolves_with_any_extension(candidate):
            continue
        problems.append(f"figure: \\includegraphics{{{rel}}} has no co-located file")
    return problems


def _resolves_with_any_extension(candidate: Path) -> bool:
    """True iff ``candidate`` resolves with some common graphics extension appended.

    LaTeX picks the extension at compile time when ``\\includegraphics{figures/fig1}`` omits
    it; this mirrors that for the read-only presence check (deterministic directory probe).
    """
    if candidate.suffix:
        return False
    parent = candidate.parent
    if not parent.is_dir():
        return False
    stem = candidate.name
    for ext in (".pdf", ".png", ".jpg", ".jpeg", ".eps"):
        if (parent / (stem + ext)).is_file():
            return True
    return False


# -- README submission-readiness ---------------------------------------------

# The submission-readiness self-assessment heading (design §3 self-assessment / §1 [4]). The
# assembler writes "## Submission-readiness self-assessment"; we match the phrase tolerantly
# (case-insensitive, hyphen-or-space) so a hand-edited README that keeps the SECTION passes.
_SUBMISSION_READINESS_RE = re.compile(r"submission[-\s]?readiness", re.IGNORECASE)


def readme_submission_readiness_problems(readme: str) -> List[str]:
    """A single problem line iff the README lacks a submission-readiness section (design §3).

    PURE + deterministic. Returns ``[]`` when the README names a submission-readiness section
    (the record-external-gaps self-assessment the spec [4] requires), else one problem line.
    """
    if _SUBMISSION_READINESS_RE.search(readme):
        return []
    return [
        "README: missing a submission-readiness self-assessment section "
        "(naming the record-external gaps)"
    ]


__all__ = [
    "PACKAGE_FOLDERS",
    "layout_problems",
    "cited_keys",
    "bib_keys",
    "cite_resolution_problems",
    "abstract_body",
    "abstract_word_count",
    "abstract_max_words_problems",
    "figure_presence_problems",
    "readme_submission_readiness_problems",
]
