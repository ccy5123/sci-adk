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
import unicodedata
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


# -- citation-key shape + disambiguation (P3, REQ-PG-301/302/303) -------------

# The canonical citation-key shape sci-adk's acquisition path emits (search/citation_keys.py):
# <NormalizedSurname><Year>(+a/b). Surname = ASCII alnum starting with a letter; the convention
# PRESERVES author casing ("McKay", "vanderBerg"), so the gate does NOT force a leading capital
# (which would reject legitimate lower-cased compound surnames). Year = 4 digits OR the "nd"
# no-date fallback. Optional lower-case a/b/c... disambiguation suffix. The gate VALIDATES the
# manuscript against this convention -- OD-4: FAIL and name the key, never re-key (author files
# are not mutated; the acquisition path search/citation_keys.py owns deterministic re-keying).
_CITEKEY_SHAPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:\d{4}|nd)[a-z]*$")
# Split a CONFORMING key into (base=<surname><year>, suffix=<a/b/...>) for the disambiguation
# check. The base ends at the LAST 4-digit year or "nd" so a surname containing digits is safe.
_CITEKEY_BASE_RE = re.compile(r"^(.*(?:\d{4}|nd))([a-z]*)$")


def citation_key_conforms(key: str) -> bool:
    """True iff ``key`` matches the canonical ``<Surname><Year>(+a/b)`` shape. PURE."""
    return bool(_CITEKEY_SHAPE_RE.match(key))


def citation_key_shape_problems(tex: str, bib: str) -> List[str]:
    """Every ``\\cite`` key and ``.bib`` entry key NOT matching the canonical shape (REQ-PG-301/302).

    PURE + deterministic. Validates BOTH the cited keys and the defined ``.bib`` keys against
    ``<Surname><Year>(+a/b)`` (the convention ``search/citation_keys.py`` owns); non-conforming
    keys are named in a single sorted problem line (OD-4: FAIL -- the author fixes them, the gate
    never re-keys). Returns ``[]`` when every key conforms (or there are no keys).
    """
    offenders = sorted(
        k for k in set(cited_keys(tex)) | set(bib_keys(bib))
        if not citation_key_conforms(k)
    )
    if not offenders:
        return []
    return [
        "citation key shape: key(s) not matching <Surname><Year>(+a/b): "
        + ", ".join(offenders)
    ]


def _letter_suffix(index: int) -> str:
    """0 -> 'a', 1 -> 'b', ... 25 -> 'z', 26 -> 'aa' (bijective base-26; matches acquisition)."""
    letters = ""
    n = index + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("a") + rem) + letters
    return letters


def citation_disambiguation_problems(tex: str, bib: str) -> List[str]:
    """Mis-disambiguated ``<Surname><Year>`` groups among the cite + ``.bib`` keys (REQ-PG-303).

    PURE + deterministic. Groups every CONFORMING key by its base (``<surname><year>``); a group
    is mis-disambiguated when a bare base coexists with a suffixed sibling (the bare one should be
    "...a"), OR the suffixes present are not the contiguous ``a, b, c, ...`` from "a" (a "...b"
    with no "...a", or a gap). Names each offending group's keys. Non-conforming keys are skipped
    (the shape gate names them). A lone bare key or a complete ``a, b, c, ...`` run is well-formed.
    """
    groups: dict[str, list[str]] = {}
    for key in set(cited_keys(tex)) | set(bib_keys(bib)):
        m = _CITEKEY_BASE_RE.match(key)
        if m is None or not citation_key_conforms(key):
            continue
        groups.setdefault(m.group(1), []).append(key)
    problems: List[str] = []
    for base in sorted(groups):
        keys = sorted(groups[base])
        suffixes = {_CITEKEY_BASE_RE.match(k).group(2) for k in keys}  # type: ignore[union-attr]
        nonbare = sorted(s for s in suffixes if s)
        if not nonbare:
            continue  # only a bare key -> well-formed
        has_bare = "" in suffixes
        contiguous = nonbare == [_letter_suffix(i) for i in range(len(nonbare))]
        if has_bare or not contiguous:
            problems.append(
                f"citation disambiguation: base '{base}' is mis-disambiguated: keys {keys}"
            )
    return problems


# -- unpublished / DOI-less citation warning (P3, REQ-PG-304, OD-5: WARN) -----

# A bib entry's head + its body (up to the next entry or EOF), to detect a per-entry doi field.
_BIB_ENTRY_BODY_RE = re.compile(
    r"@\w+\s*\{\s*([^,\s}]+)\s*,(.*?)(?=@\w+\s*\{|\Z)", re.DOTALL
)
_BIB_DOI_RE = re.compile(r"\bdoi\s*=\s*[{\"]\s*([^}\"]+?)\s*[}\"]", re.IGNORECASE)


def _bib_entry_has_doi(bib: str) -> dict[str, bool]:
    """Map each defined ``.bib`` key -> whether its entry carries a non-empty ``doi`` field. PURE."""
    out: dict[str, bool] = {}
    for m in _BIB_ENTRY_BODY_RE.finditer(bib):
        out[m.group(1).strip()] = bool(_BIB_DOI_RE.search(m.group(2)))
    return out


def unpublished_citation_warnings(tex: str, bib: str) -> List[str]:
    """Every load-bearing (cited) reference with NO DOI -> a WARNING (REQ-PG-304, OD-5: WARN).

    PURE + deterministic. A cited key whose ``.bib`` entry EXISTS but declares no ``doi`` is an
    unpublished / preprint / in-prep citation -- surfaced as a NON-BLOCKING warning (OD-5), never
    a gate failure. A cited key with NO entry at all is a resolution FAILURE
    (:func:`cite_resolution_problems`), not this warning. Returns sorted warning lines (empty =
    every cited reference has a DOI, or nothing is cited).
    """
    has_doi = _bib_entry_has_doi(bib)
    return sorted(
        f"citation warning: load-bearing cite '{k}' has no DOI in references.bib "
        "(unpublished/preprint/in-prep)"
        for k in cited_keys(tex)
        if k in has_doi and not has_doi[k]
    )


# -- bib LaTeX-safety (Phase 2: the compile blind spot the cite/key gates miss) -----

# HTML entities that arrive from XML-rooted registrar metadata (Crossref/DataCite) and are
# invalid in LaTeX: &amp; &lt; &gt; &quot; &apos; &nbsp; &#NN; &#xNN;.
_HTML_ENTITY_RE = re.compile(r"&(?:amp|lt|gt|quot|apos|nbsp|#\d+|#[xX][0-9a-fA-F]+);")
# HTML markup tags (e.g. <i>...</i> from a JATS/JSON title). Requires a letter after '<' so a
# legacy bracketed DOI fragment like ``<1175:BOPACB>`` (digit-led) is NOT a false positive.
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*\s*>")
# A bare '&' that is neither an escaped '\&' nor the start of an HTML entity -- the LaTeX
# column separator, which errors in running text.
_BARE_AMP_RE = re.compile(
    r"(?<!\\)&(?!(?:amp|lt|gt|quot|apos|nbsp|#\d+|#[xX][0-9a-fA-F]+);)"
)


def _nonstandard_space_codepoints(s: str) -> set:
    """Codepoints in ``s`` that are spaces ``inputenc(utf8)`` will not render. PURE.

    Any Space-Separator (Unicode category ``Zs``) other than ASCII space (U+0020), plus the
    zero-width formatting chars. Deliberately EXCLUDES en-/em-dash and Latin-1 accented
    letters -- those are meaningful and inputenc utf8 handles them, so flagging them would be a
    false positive. (The real case: Crossref encodes author given names like ``Jon<U+2005>A.``.)
    """
    bad = set()
    for ch in s:
        cp = ord(ch)
        if cp == 0x20:
            continue
        if unicodedata.category(ch) == "Zs" or cp in (0x200B, 0x200C, 0x200D, 0xFEFF):
            bad.add(cp)
    return bad


def bib_latex_safety_problems(bib: str) -> List[str]:
    """Every ``.bib`` entry whose field values carry LaTeX-unsafe content (Phase 2). PURE.

    The cite/key gates validate that citations RESOLVE and are SHAPED right; this gate validates
    that the bib actually COMPILES -- the blind spot a manual or non-paperforge ``.bib`` leaves.
    paperforge's ``latex_safety.sanitize`` closes it on the acquisition path; this is the
    verify-side safety net for every OTHER path (hand-authored bib, a different tool, an old file).

    Flags, per entry: HTML entities (``&amp;`` …), HTML markup tags (``<i>``), a bare unescaped
    ``&`` (the LaTeX column separator), and non-standard Unicode spaces (U+2005 four-per-em etc.).
    Does NOT flag the LaTeX-safe ``\\&``, en-/em-dash, or Latin-1 accents -- no false positive.

    OD-4 style: names the offending entry; never rewrites the bib (the author re-runs paperforge
    or fixes it by hand). Returns sorted problem lines (empty = clean).
    """
    problems: List[str] = []
    for m in _BIB_ENTRY_BODY_RE.finditer(bib):
        key, body = m.group(1).strip(), m.group(2)
        if _HTML_ENTITY_RE.search(body):
            problems.append(
                f"bib LaTeX-safety: entry '{key}' contains an HTML entity (e.g. &amp;) -- "
                "invalid in LaTeX, use the LaTeX form (e.g. \\&)"
            )
        if _HTML_TAG_RE.search(body):
            problems.append(
                f"bib LaTeX-safety: entry '{key}' contains an HTML tag (e.g. <i>) -- "
                "use the LaTeX command (e.g. \\textit{...})"
            )
        if _BARE_AMP_RE.search(body):
            problems.append(
                f"bib LaTeX-safety: entry '{key}' contains a bare '&' -- escape it as \\&"
            )
        bad = _nonstandard_space_codepoints(body)
        if bad:
            cps = ", ".join("U+%04X" % c for c in sorted(bad))
            problems.append(
                f"bib LaTeX-safety: entry '{key}' contains non-standard Unicode space(s) "
                f"[{cps}] -- replace with an ASCII space"
            )
    return sorted(problems)


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


# -- body word range (P4, REQ-PG-404 / AC-3: gates, no longer advisory) -------


def body_word_count(tex: str) -> int:
    """The deterministic word count over the manuscript BODY (the abstract env removed). PURE.

    The 'body' is the prose OUTSIDE ``\\begin{abstract}...\\end{abstract}`` -- the abstract has
    its own ``abstract_max_words`` gate, so the body range counts the rest. Reuses the same
    conservative :func:`word_count` tokeniser (one definition of 'how many words').
    """
    return word_count(_ABSTRACT_BODY_RE.sub(" ", tex))


def body_word_range_problems(
    tex: str, body_word_range: Optional[tuple[int, int]]
) -> List[str]:
    """A single problem line iff the BODY word count is outside ``body_word_range`` (REQ-PG-404).

    PURE + deterministic. ``None`` skips the check. SPEC-PAPER-GATE-001 P4 / AC-3 makes the body
    range GATE (it was advisory): a body below ``min`` or above ``max`` FAILS and names the count
    + range. Returns ``[]`` when within range or no range declared.
    """
    if body_word_range is None:
        return []
    lo, hi = body_word_range
    count = body_word_count(tex)
    if lo <= count <= hi:
        return []
    return [
        f"body word count: {count} words is outside the declared range {lo}-{hi}"
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
    "bib_latex_safety_problems",
    "cite_resolution_problems",
    "citation_key_conforms",
    "citation_key_shape_problems",
    "citation_disambiguation_problems",
    "unpublished_citation_warnings",
    "abstract_body",
    "abstract_word_count",
    "abstract_max_words_problems",
    "body_word_count",
    "body_word_range_problems",
    "figure_presence_problems",
    "readme_submission_readiness_problems",
]
