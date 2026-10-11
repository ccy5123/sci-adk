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
    section;
  - :func:`package_deposit_problems` -- each packaged run's protocol files under
    ``06_provenance/protocol/<id>/``, its declared files under ``02_data/<id>/`` and
    ``05_inputs/<id>/`` and ``06_provenance/deposit.csv`` are what ``runs/<id>/`` calls for,
    the package holds exactly the files the manifest lists, and the paths ``main.tex`` /
    ``si.tex`` name exist (design/deposit-files.md D5, D8).

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

import csv
import hashlib
import io
import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from sci_adk.render.deposit import (
    DATA_DIR,
    INPUTS_DIR,
    PACKAGE_DATA_DIR,
    PACKAGE_INPUTS_DIR,
    PACKAGE_MANIFEST,
    PACKAGE_MANIFEST_COLUMNS,
    PACKAGE_PROTOCOL_DIR,
    PACKAGE_RECORD,
    DataPlan,
    ProtocolPlan,
    deposit_data_problems,
    is_plain_name,
    package_data_root,
    package_manifest_differences,
    package_manifest_records,
    package_manifest_text,
    package_name_problems,
    package_protocol_root,
    package_rows,
    plan_run_deposit,
    protocol_digest,
    protocol_record_problems,
    withheld_advisory,
)
from sci_adk.render.bib_latex import (
    HTML_ENTITY_RE,
    T1_ONLY_CHARS,
    VERBATIM_FIELDS,
    accented_letters_in_math,
    bare_specials,
    bib_commands,
    caret_notation,
    dangerous_commands,
    field_value_spans,
    field_values,
    html_tags,
    math_commands_in_text,
    printed_field,
    raw_sort_letter,
    sort_letter_command,
    string_macros_used_as_urls,
    stray_math_dollar,
    undefined_month_tokens,
    unknown_commands,
    untypesettable_chars,
    url_arguments,
    url_problems,
)
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

# SPEC-SI-AUTHORING-001 M5 (REQ-SA-505): the package's deterministic record artifact relocates
# OUT of 01_manuscript/si.tex into the provenance floor as 06_provenance/record.tex -- symmetric
# to the per-run runs/<id>/record.tex. This is the SINGLE SOURCE both the assembler (make_si.py's
# OUT, wired via package.py) and the package deposit-completeness check (REQ-SA-508) reference,
# so the package record/belief boundary cannot drift. It also makes the record EXEMPT from the
# package tool-vocab gate BY CONSTRUCTION (the gate reads only 01_manuscript/, REQ-SA-507).
PACKAGE_RECORD_NAME: str = "record.tex"
_PACKAGE_RECORD_FOLDER: str = "06_provenance"


def package_record_path(package_dir: Path) -> Path:
    """The package's relocated deterministic record artifact (``06_provenance/record.tex``).

    The package analogue of :func:`sci_adk.loop.compiler.deposit_record_path` (REQ-SA-505/508):
    one source of truth for the relocation target that both the assembler writes and the package
    deposit-completeness check reads, so the package record/belief boundary cannot drift.
    """
    return package_dir / _PACKAGE_RECORD_FOLDER / PACKAGE_RECORD_NAME


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


def _entry_close_index(bib: str, open_brace: int) -> int:
    """The index just PAST the ``}`` that closes the entry opened at ``open_brace``.

    ``open_brace`` is the index of the ``{`` after the entry type (``@article{`` here). Scans
    forward tracking ``{`` / ``}`` nesting depth (depth 1 immediately after the entry-open
    brace) and returns the index one past the matching close brace -- the TRUE end of the
    entry, brace-depth aware. If the braces never balance (a malformed pool entry), returns
    ``len(bib)`` (the entry runs to EOF -- fail-loud content is preserved for the integrity
    gate to catch, never silently truncated). PURE.
    """
    depth = 1
    i = open_brace + 1
    n = len(bib)
    while i < n and depth > 0:
        ch = bib[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    return i


def bib_subset(bib: str, keep: Sequence[str]) -> str:
    """The ``bib`` entries whose key is in ``keep``, in source order (SI subset, M6).

    PURE + deterministic, no ``bibtexparser`` -- regex/line-based, house style (see
    ``citation_keys.py``). For each entry header (``@type{KEY,``, via ``_BIB_ENTRY_RE``) whose
    key is in ``keep``, the entry spans from its ``@`` to the TRUE matching close brace, found
    by BRACE-DEPTH-AWARE scanning (:func:`_entry_close_index`) -- NOT the naive "next header =
    entry end", which truncated an entry whose field value embeds a ``@word{...}``-shaped token
    (e.g. ``note = {... @inbook{X, y} ...}``). Kept entries are re-joined in their original
    order. Text before the first ``@entry`` (comments / preamble) is dropped -- the result is
    the concatenation of the kept entries only, so ``bib_keys(bib_subset(bib, keep)) ==
    sorted(set(keep) & set(bib_keys(bib)))``, and an empty result -> ``""``. Used to build the
    cited-only ``references_SI.bib`` from the run's ONE literature pool (REQ-SA-604/605): no
    LLM, no network, a pure set filter over the already-acquired pool.
    """
    wanted = set(keep)
    kept: List[str] = []
    for m in _BIB_ENTRY_RE.finditer(bib):
        key = m.group(1).strip()
        if key not in wanted:
            continue
        # m spans "@type{KEY," -- the entry-open brace is the "{" the header matched. Locate it
        # from the match start so the depth scan begins at the right brace.
        open_brace = bib.index("{", m.start())
        end = _entry_close_index(bib, open_brace)
        kept.append(bib[m.start() : end].rstrip())
    return ("\n".join(kept) + "\n") if kept else ""


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

# What is checked: the values of PRINTED fields only (``bib_latex.printed_field``: not abstract,
# keywords, file, annote, timestamp ...), since text no style prints never reaches the .bbl and
# cannot stop pdflatex. In those values: HTML entities (&amp; &lt; &#8722; ...) and markup tags
# (<i>, <span class="...">) from XML-rooted registrar metadata (Crossref/DataCite), bare
# specials, math a '$' breaks, non-standard spaces, characters pdflatex cannot typeset. The
# patterns and the character policy are the ones render's LaTeX-safe bib copy (bib_latex.py)
# applies, so the check and the copy agree. url/doi values print a special as itself: only
# their spaces and characters are checked here (an escape there would print; ?b&c;d is not an
# entity), and what hyperref would run in them by bib_command_problems. The .bib is read as
# BibTeX reads it (_bib_units): @string values and @preamble text are printed too.
# Spaces and zero-width characters have their own problem line (_nonstandard_space_codepoints).
_ZERO_WIDTH = (0x200B, 0x200C, 0x200D, 0xFEFF)
# The fix for a bare special: an escape, or (for ^) the command that prints a caret.
_SPECIAL_FIX = {"^": "write it as \\textasciicircum{}"}
# Where a per-run copy's problem is fixed: render rewrites paper/ from the run's literature store.
_PER_RUN_STORE = "the run's literature store entry (literature/references.bib), then render again"


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
        if unicodedata.category(ch) == "Zs" or cp in _ZERO_WIDTH:
            bad.add(cp)
    return bad


def _codepoint(ch: str) -> str:
    return "U+%04X (%s)" % (ord(ch), unicodedata.name(ch, "unnamed"))


def _character_problems(
    where: str, printed: List[tuple], package_source: Optional[str]
) -> List[str]:
    """The lines for characters pdflatex cannot typeset in one entry's printed values: one for
    those the copy has a LaTeX form for (naming the form), one for those with none."""
    with_form: dict = {}
    no_form: set = set()
    for name, value in printed:
        for ch, form in untypesettable_chars(value, verbatim=name in VERBATIM_FIELDS):
            if unicodedata.category(ch) == "Zs" or ord(ch) in _ZERO_WIDTH:
                continue  # reported as a space
            if form is None:
                no_form.add(ch)
            else:
                with_form.setdefault(ch, form)
    cannot = "which pdflatex cannot typeset with the preamble sci-adk emits (utf8 inputenc, T1)"
    lines: List[str] = []
    if with_form:
        chars = sorted(with_form)
        forms = ", ".join(
            "U+%04X as %s" % (ord(c), with_form[c] or "nothing (drop it)") for c in chars
        )
        advice = (
            f"; fix it in {package_source}"
            if package_source
            else "; re-rendering a run rewrites its paper/ copy with these forms"
        )
        lines.append(
            f"{where} contains {', '.join(_codepoint(c) for c in chars)}, {cannot} -- write it "
            f"in LaTeX: {forms}{advice}"
        )
    if no_form:
        lines.append(
            f"{where} contains {', '.join(_codepoint(c) for c in sorted(no_form))}, {cannot}, "
            f"and there is no automatic LaTeX form for it -- replace it in "
            f"{package_source or _PER_RUN_STORE} with an ASCII approximation or a LaTeX form"
        )
    return lines


# The label a unit read from a .bib carries in a problem line, for a @preamble.
_PREAMBLE = "@preamble"


def _bib_units(bib: str) -> List[Tuple[str, List[Tuple[str, str]]]]:
    """``(what, [(field name, value), ...])`` for each piece of ``bib`` BibTeX prints, read as
    BibTeX reads it (``bib_latex.bib_commands``: a parenthesised entry, white space after the
    ``@``, an ``@`` inside a value and ``%`` are taken as BibTeX takes them):

    - each ``@preamble`` (``"@preamble"``): its strings, which BibTeX writes into the reference
      list as they are;
    - each ``@string`` (``"@string 'name'"``): its value, printed wherever a field names the
      macro, whatever the macro is called (``title = abstract``); named ``url`` when a url or
      doi field names the macro, so it is read as a URL, else ``string``;
    - each entry (``"entry 'KEY'"``): the values of its printed fields
      (``bib_latex.printed_field``), braced or quoted, ``#``-joined parts each their own value.
    PURE."""
    commands = bib_commands(bib)
    url_macros = string_macros_used_as_urls(bib, commands)
    units: List[Tuple[str, List[Tuple[str, str]]]] = []
    for command in commands:
        if command.command == "preamble":
            values = [
                ("preamble", bib[start:end])
                for field in command.fields
                for start, end, delimited in field.parts
                if delimited
            ]
            units.append((_PREAMBLE, values))
        elif command.command == "string":
            for field in command.fields:
                kind = "url" if field.name in url_macros else "string"
                values = [(kind, bib[s:e]) for s, e, delimited in field.parts if delimited]
                units.append((f"@string '{field.name}'", values))
        else:
            values = [
                (field.name, bib[start:end])
                for field in command.fields
                if printed_field(field.name)
                for start, end, delimited in field.parts
                if delimited
            ]
            units.append((f"entry '{command.key}'", values))
    return units


def _unit_command_problems(
    where: str, printed: List[Tuple[str, str]], package_source: Optional[str], *, preamble: bool
) -> List[str]:
    """The FAIL lines for one unit of :func:`_bib_units`: a @preamble; a command on
    ``bib_latex.DANGEROUS_COMMANDS``; ``^^`` notation; and a URL (a url or doi value, a macro
    one names, or the URL argument of ``\\url``/``\\href`` in a value) holding a backslash,
    ``^^``, a brace or a scheme that launches a program or opens a file
    (``bib_latex.url_problems``). Shared by :func:`bib_latex_safety_problems` and
    :func:`bib_command_problems`, so both write the same line for the same unit."""
    fix = package_source or _PER_RUN_STORE
    values = [v for name, v in printed if name not in VERBATIM_FIELDS]
    urls = [v for name, v in printed if name in VERBATIM_FIELDS]
    urls += [arg for v in values for arg in url_arguments(v)]
    lines: List[str] = []
    if preamble:
        lines.append(
            f"{where} -- BibTeX writes a @preamble's text into the reference list as LaTeX, "
            "which pdflatex runs (a definition, a file read); a reference needs none: remove "
            f"it from {fix}"
        )
    commands = list(dict.fromkeys(c for v in values for c in dangerous_commands(v)))
    if commands:
        lines.append(
            f"{where} contains the command(s) {', '.join(commands)} -- a command that can "
            "read or write a file, define a macro, change how TeX reads its input or end the "
            f"document, which pdflatex would run from the reference list; remove it from {fix}"
        )
    if any(caret_notation(v) for v in values):
        lines.append(
            f"{where} has '^^' -- TeX reads '^^' and the characters after it as another "
            f"character ('^^5c' is a backslash), so it can spell a command; remove it from {fix}"
        )
    reasons = list(dict.fromkeys(r for url in urls for r in url_problems(url)))
    if reasons:
        lines.append(
            f"{where} has {', '.join(reasons)} in a URL or DOI -- hyperref reads a URL as TeX "
            "to make the link, so a backslash command in it runs ('^^5c' spells a backslash), "
            "and a run: or file: link launches a program or opens a file; no URL or DOI needs "
            f"one: remove it from {fix}"
        )
    return lines


# @MX:NOTE: [AUTO] verify runs this on every bibliography render writes (paper/, its SI and
#   deposit copies) whether or not a publishing contract is frozen; render prints the same lines.
def bib_command_problems(
    bib: str, source: str = "references.bib", package_source: Optional[str] = None
) -> List[str]:
    """Every ``.bib`` entry whose printed field values carry a command that can read or write a
    file, define a macro, change how TeX reads its input or end the document
    (``bib_latex.DANGEROUS_COMMANDS``: ``\\input``, ``\\def``, ``\\catcode``, ``\\end`` ...),
    or TeX's ``^^`` notation. PURE.

    Read as BibTeX reads the file (:func:`_bib_units`): every entry, every ``@string`` macro
    (whatever its name) and every ``@preamble``, which fails as such (BibTeX writes its text into
    the reference list as LaTeX). A url or doi value, a macro one names and the URL argument of
    ``\\url``/``\\href`` in a value fail on a backslash, ``^^``, a brace or a ``run:``/``file:``
    scheme (hyperref reads a URL as TeX).

    The same lines :func:`bib_latex_safety_problems` writes for them, so a caller running both
    can drop the repeats. ``source`` / ``package_source`` as there. Returns sorted lines (empty =
    clean)."""
    problems: List[str] = []
    for what, printed in _bib_units(bib):
        problems.extend(
            _unit_command_problems(
                f"bib LaTeX-safety: {source} {what}", printed, package_source,
                preamble=what == _PREAMBLE,
            )
        )
    return sorted(problems)


def bib_command_advisories(
    bib: str, source: str = "references.bib", package_source: Optional[str] = None
) -> List[str]:
    """One advisory per ``.bib`` entry or ``@string`` macro (:func:`_bib_units`) whose printed
    values carry a command verify does not know (``bib_latex.unknown_commands``: neither one a
    reference needs, ``bib_latex.SAFE_COMMANDS``, nor a dangerous one): publisher metadata holds
    harmless ones (``\\texttimes``, ``\\MakeUppercase``), but pdflatex stops on a command the
    preamble does not define, or on an argument it cannot use (``\\hspace{20000pt}``). And one
    per entry or macro that uses a math command in running text
    (``bib_latex.math_commands_in_text``: ``Decay of \\alpha particles``), where pdflatex stops
    with "Missing $ inserted". NON-BLOCKING. PURE."""
    fix = package_source or _PER_RUN_STORE
    notes: List[str] = []
    for what, printed in _bib_units(bib):
        if what == _PREAMBLE:
            continue  # it fails as a whole (bib_command_problems)
        values = [v for name, v in printed if name not in VERBATIM_FIELDS]
        commands = list(dict.fromkeys(c for v in values for c in unknown_commands(v)))
        if commands:
            notes.append(
                f"bib commands: {source} {what} contains {', '.join(commands)}, which verify "
                "does not know: not a command that can read or write a file, define a macro or "
                "end the document, but pdflatex stops on a command the preamble does not define "
                "or on an argument it cannot use (a length over 16383pt) -- check that the "
                f"reference list compiles, or replace it in {fix}"
            )
        in_text = list(dict.fromkeys(c for v in values for c in math_commands_in_text(v)))
        if in_text:
            notes.append(
                f"bib commands: {source} {what} uses the math command(s) {', '.join(in_text)} "
                "in running text, where pdflatex stops on it (\"Missing $ inserted\") -- put it "
                f"in math, $...$, in {fix}"
            )
    return sorted(notes)


def bib_latex_safety_problems(
    bib: str, source: str = "references.bib", package_source: Optional[str] = None
) -> List[str]:
    """Every ``.bib`` entry whose printed field values carry LaTeX-unsafe content (Phase 2). PURE.

    The cite/key gates validate that citations RESOLVE and are SHAPED right; this gate validates
    that the bib actually COMPILES. Render writes a LaTeX-safe copy of the run's literature pool
    into ``paper/`` (``bib_latex.latex_safe_bib``), and paperforge's ``latex_safety.sanitize``
    cleans what it acquires; this is the verify-side net for whatever is still unsafe -- a
    character the copy has no LaTeX form for, a hand-edited copy, an author-supplied package bib.

    Only fields a BibTeX style prints are checked (``bib_latex.UNPRINTED_FIELDS`` lists the
    ones that are not: abstract, keywords, file, annote, timestamp ...). Flags, per entry,
    naming what was found: HTML entities (``&amp;`` ...), markup tags (``<i>``,
    ``<span class="...">``; read in running text only, so ``$x<y$`` is not a tag), a bare ``&``
    (the LaTeX column separator), ``%`` or ``#``, a bare ``_`` or ``^`` outside math, a ``$``
    nested inside math or left open, a command that can read or write a file, define a macro,
    change how TeX reads its input or end the document (``\\input``, ``\\def``, ``\\end``:
    ``bib_latex.DANGEROUS_COMMANDS``; any other unknown command is advisory,
    :func:`bib_command_advisories`), ``^^`` notation, non-standard Unicode spaces (U+2005
    four-per-em etc.), and
    characters pdflatex cannot typeset with the preamble sci-adk emits (U+2212 MINUS SIGN ...;
    see ``bib_latex.typesettable``) -- with the LaTeX form the copy writes for each, or, where
    there is none, the instruction to replace the character at its source. Does NOT flag the
    LaTeX-safe ``\\&``, dashes, curly quotes, or Latin-1 / Latin Extended-A accents, nor an
    entity shape or a bare special in a ``url`` or ``doi`` value (typeset verbatim; the copy
    leaves them).

    ``source`` is the file name the problem lines carry. ``package_source`` is set for a
    package bib: the file the author has to fix (the package copies its bibliographies from
    ``package_src/`` unchanged, so re-rendering a run never repairs them); each line then names
    it instead of the per-run advice.

    OD-4 style: names the offending entry; never rewrites the bib. Returns sorted problem lines
    (empty = clean).
    """
    tail = f"; fix it in {package_source}" if package_source else ""
    problems: List[str] = []
    for what, printed in _bib_units(bib):
        if what == _PREAMBLE:
            continue  # it fails as a whole (bib_command_problems, below)
        where = f"bib LaTeX-safety: {source} {what}"
        values = [v for name, v in printed if name not in VERBATIM_FIELDS]
        entities = sorted({e for v in values for e in HTML_ENTITY_RE.findall(v)})
        if entities:
            problems.append(
                f"{where} contains HTML entity {', '.join(entities)} -- invalid in LaTeX, "
                f"use the LaTeX form (e.g. \\&){tail}"
            )
        tags = sorted({t for v in values for t in html_tags(v)})
        if tags:
            problems.append(
                f"{where} contains HTML tag {', '.join(tags)} -- use the LaTeX command "
                f"(e.g. \\textit{{...}}) or remove it{tail}"
            )
        for special in sorted(set().union(*(bare_specials(v) for v in values))):
            fix = _SPECIAL_FIX.get(special, f"escape it as \\{special}")
            problems.append(f"{where} contains a bare '{special}' -- {fix}{tail}")
        if any(stray_math_dollar(v) for v in values):
            problems.append(
                f"{where} has a '$' nested inside math or left open -- pdflatex stops on it; "
                f"close each $...$ at the brace level where it opens"
                + (
                    tail
                    or "; fix the entry in the run's literature store (literature/"
                    "references.bib) if it holds the '$', else render the run again"
                )
            )
        in_math = list(dict.fromkeys(c for v in values for c in accented_letters_in_math(v)))
        if in_math:
            problems.append(
                f"{where} has the accented letter(s) {', '.join(_codepoint(c) for c in in_math)} "
                "inside math -- inputenc writes it as a text accent, which pdflatex sets wrongly "
                "in math or stops on (\"Please use \\mathaccent\"); write it outside the math, "
                "or as accent commands in an \\mbox (the copy render writes does)"
                + (tail or "; render the run again")
            )
        bad = set().union(*(_nonstandard_space_codepoints(v) for _, v in printed))
        if bad:
            cps = ", ".join("U+%04X" % c for c in sorted(bad))
            problems.append(
                f"{where} contains non-standard Unicode space(s) [{cps}] -- replace with an "
                f"ASCII space{tail}"
            )
        problems.extend(_character_problems(where, printed, package_source))
    problems.extend(bib_command_problems(bib, source=source, package_source=package_source))
    return sorted(problems)


# -- font encoding of a package manuscript ---------------------------------------------------

# The preamble lines that decide the font encoding: \usepackage[...T1...]{fontenc}, or fontspec /
# unicode-math (the manuscript then needs XeLaTeX/LuaLaTeX, which typeset Unicode directly).
_FONTENC_RE = re.compile(r"\\(?:usepackage|RequirePackage)\s*\[([^\]]*)\]\s*\{fontenc\}")
_UNICODE_ENGINE_RE = re.compile(
    r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{[^}]*\b(?:fontspec|unicode-math)\b"
)
_TEX_COMMENT_RE = re.compile(r"(?<!\\)%.*")
_BIBLIOGRAPHY_RE = re.compile(r"\\bibliography\s*\{([^}]*)\}")
# The ogonek accent command: OT1 has no ogonek, so \k stops pdflatex there (measured).
_OGONEK_RE = re.compile(r"\\k(?![A-Za-z])")


def bibliography_stems(tex: str) -> List[str]:
    """The ``.bib`` stems ``tex`` loads through ``\\bibliography{a,b}`` (comments ignored). PURE."""
    body = _TEX_COMMENT_RE.sub("", tex)
    return [
        stem.strip()
        for m in _BIBLIOGRAPHY_RE.finditer(body)
        for stem in m.group(1).split(",")
        if stem.strip()
    ]


def _loads_t1_or_unicode_engine(tex: str) -> bool:
    preamble = _TEX_COMMENT_RE.sub("", tex.split("\\begin{document}", 1)[0])
    if _UNICODE_ENGINE_RE.search(preamble):
        return True
    return any(
        "T1" in (option.strip() for option in m.group(1).split(","))
        for m in _FONTENC_RE.finditer(preamble)
    )


def font_encoding_problems(
    tex: str, bib: str, *, tex_name: str, bib_name: str, fix_in: str
) -> List[str]:
    """One line when ``tex`` loads no T1 font encoding and ``bib`` (the bibliography it loads)
    holds a character pdflatex typesets only in T1, else none. PURE.

    sci-adk's character policy (``bib_latex.typesettable``) assumes the preamble render emits,
    which loads ``\\usepackage[T1]{fontenc}``; an author-supplied package manuscript may not,
    and then pdflatex runs in OT1, where ``bib_latex.T1_ONLY_CHARS`` (Ð þ Ę Ų « ...) and the
    ogonek command ``\\k`` stop the compile. Only printed fields count. A manuscript that loads
    T1 (``[T1]`` or a list holding it), or fontspec / unicode-math, is not checked; neither is a
    bib without such characters. ``fix_in`` names the file to add the line to.
    """
    if _loads_t1_or_unicode_engine(tex):
        return []
    found: dict = {}
    for m in _BIB_ENTRY_BODY_RE.finditer(bib):
        key, body = m.group(1).strip(), m.group(2)
        for name, start, end in field_value_spans(body):
            if not printed_field(name):
                continue
            value = body[start:end]
            for ch in set(value) & T1_ONLY_CHARS:
                found.setdefault(ch, set()).add(key)
            if _OGONEK_RE.search(value):
                found.setdefault("\\k", set()).add(key)
    if not found:
        return []
    chars = sorted(found, key=lambda c: (len(c) > 1, c))
    keys = sorted(set().union(*found.values()))
    return [
        f"font encoding: {bib_name} holds {' '.join(chars)} (entries {', '.join(keys)}), which "
        f"pdflatex typesets only in the T1 font encoding, and {tex_name} does not load it -- "
        f"add \\usepackage[T1]{{fontenc}} to the preamble of {fix_in}"
    ]


def bib_month_advisories(
    bib: str, source: str = "references.bib", package_source: Optional[str] = None
) -> List[str]:
    """Advisory lines (never a failure) for each bare ``month`` name BibTeX does not define
    (``month = June``, ``month = sept``): BibTeX warns and the reference list leaves the month
    out. Render's copy writes the macro (``jun``, ``sep``) itself; a package bib is copied
    unchanged, so the advice names ``package_source`` when given. PURE."""
    tail = f" in {package_source}" if package_source else ""
    lines: List[str] = []
    for m in _BIB_ENTRY_BODY_RE.finditer(bib):
        key, body = m.group(1).strip(), m.group(2)
        for token, macro in undefined_month_tokens(body):
            lines.append(
                f"bib month: {source} entry '{key}' has month = {token}, a name BibTeX does "
                f"not define (the reference list leaves the month out) -- write "
                f"month = {macro}{tail}"
            )
    return sorted(lines)


def bib_sort_advisories(
    tex: str, bib: str, source: str = "references.bib", package_source: Optional[str] = None
) -> List[str]:
    """Advisory lines (never a failure) for each entry ``tex`` cites whose first author (the
    first editor when it has no author) BibTeX sorts by a raw non-ASCII letter
    (:func:`bib_latex.raw_sort_letter`): plainnat lists it after the names that start with Z.
    Render's reference-list copy writes every letter that has a command BibTeX sorts by its base
    letter that way, so in a rendered paper only Ð Þ Đ Ŋ remain; a package bib is copied
    unchanged, so the advice names the command and ``package_source`` when there is one. PURE."""
    cited = set(cited_keys(tex))
    lines: List[str] = []
    for m in _BIB_ENTRY_BODY_RE.finditer(bib):
        key, body = m.group(1).strip(), m.group(2)
        if key not in cited:
            continue
        values: dict[str, str] = {}
        for name, start, end in field_value_spans(body):
            values.setdefault(name, body[start:end])
        names = values.get("author") or values.get("editor") or ""
        letter = raw_sort_letter(names)
        if letter is None:
            continue
        command = sort_letter_command(letter)
        fix = ""
        if command is not None:
            where = f" in {package_source}" if package_source else ""
            fix = f" -- write it as {command}{where}, which sorts with its base letter"
        lines.append(
            f"bib sort: {source} entry '{key}': the first name starts with {letter}, which "
            f"BibTeX sorts after every ASCII letter, so the reference list prints the entry "
            f"after the names that start with Z{fix}"
        )
    return sorted(lines)


# An entry header ``@type{KEY,`` -- the type is kept (only articles are checked below).
_BIB_TYPED_HEAD_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s{}]+)\s*,")
# The fields plainnat prints after an article's volume and issue: the page range, or the article
# number as ``eid``. ACM's ``articleno`` is not printed (measured with bibtex), so it does not count.
_ARTICLE_LOCATION_FIELDS = ("pages", "eid")


def bib_article_number_advisories(
    tex: str,
    bib: str,
    source: str = "references.bib",
    fix_in: str = "the literature store",
) -> List[str]:
    """Advisory lines (never a failure) for each ``@article`` entry ``tex`` cites that has a
    ``journal`` and a ``volume`` but neither ``pages`` nor ``eid``: the reference list then gives
    the journal and volume without where in the volume the article is. The usual cause is a
    journal that numbers articles instead of pages (J Cheminform (2018) 10:10): the registrar
    BibTeX the store is acquired from has no field for that number, and sci-adk's acquisition
    never sees the metadata that holds it, so it is added by hand as ``pages = {<n>}`` in
    ``fix_in``. Entries are split brace-depth aware (a one-line entry and a field name inside
    another value are both read correctly); an empty field counts as absent. PURE."""
    cited = set(cited_keys(tex))
    lines: List[str] = []
    pos = 0
    while (m := _BIB_TYPED_HEAD_RE.search(bib, pos)) is not None:
        end = _entry_close_index(bib, bib.index("{", m.start()))
        pos = end
        kind, key = m.group(1).lower(), m.group(2)
        if kind != "article" or key not in cited:
            continue
        values = {name: v.strip() for name, v in field_values(bib[m.end() : end - 1]).items()}
        journal, volume = values.get("journal", ""), values.get("volume", "")
        if not (journal and volume) or any(values.get(f) for f in _ARTICLE_LOCATION_FIELDS):
            continue
        lines.append(
            f"bib article number: {source} entry '{key}' ({journal}, volume {volume}) has "
            f"neither pages nor eid, so the reference list does not say where in the volume "
            f"the article is -- add its article number as pages = {{<n>}} to the entry in "
            f"{fix_in}"
        )
    return sorted(lines)


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


# -- Deposit-completeness (SPEC-SI-AUTHORING-001 M2, Pillar C) ----------------

# The "Data & code availability" statement marker (design §5 / spec REQ-SA-301). Matched
# tolerantly (case-insensitive, "and"-or-"&", any whitespace) so a hand-authored variant in
# the deposit's record text still counts -- the SAME presence-only spirit as
# ``_SUBMISSION_READINESS_RE`` above. Presence-only: it confirms the statement EXISTS, never
# that it is correct (record vs belief -- this gate does not judge belief content).
#
# KEEP IN SYNC with the authoritative producers of the statement (REQ-SA-506a): the package
# record renderer emits `\section{Data \& code availability}` (make_si.py), and the per-run
# record renderer's availability prose likewise carries this header. This pattern MUST keep
# matching those header strings -- changing a producer's wording without widening this regex
# would silently break the deposit-completeness gate.
_DATA_AVAILABILITY_RE = re.compile(
    r"data\s*(?:&|\\&|and)\s*code\s*availability", re.IGNORECASE
)


def deposit_completeness_problems(record_path: Path) -> List[str]:
    """Problem lines iff the deposit lacks the record artifact and/or its availability stmt.

    PURE + deterministic + presence-only, modeled on
    :func:`readme_submission_readiness_problems` (REQ-SA-301/304). Returns ``[]`` when the
    deposit carries BOTH (a) the retained record artifact at ``record_path`` AND (b) a
    "Data & code availability" statement (detected by presence in the record artifact's
    text), else one problem line per missing element (REQ-SA-302/303, named separately --
    EC-5).

    ``record_path`` is supplied already-resolved by the caller (``verify`` resolves it via
    ``loop.compiler.deposit_record_path`` -- the M1 single source of truth, F4). This keeps
    the checker on the render/kernel seam: ``render/`` imports ``sci_adk.core`` + sibling
    render helpers ONLY, never ``loop/`` (which would cycle, since ``loop.compiler`` imports
    ``render``). The checker reads the record file's TEXT, never an LLM, never the network --
    same inputs -> same result.
    """
    if not record_path.is_file():
        # AC-C2 / EC-5: the deposit's retained record artifact is absent -> name THAT element
        # (one line). The availability statement lives IN the record artifact, so with no
        # record there is nothing to carry it; naming the absent record is the single, honest
        # missing element (EC-5's "vice versa" -- availability without record -- cannot arise).
        return [
            f"deposit: missing the retained record artifact ({record_path.name})"
        ]
    if not _DATA_AVAILABILITY_RE.search(record_path.read_text(encoding="utf-8")):
        # AC-C3: the record artifact exists but states no availability statement -> name it.
        return [
            "deposit: missing a \"Data & code availability\" statement in the record artifact"
        ]
    return []


# -- deposit files (design/deposit-files.md D5, D8) -------------------------------

_DEPOSIT_TAG = "deposit files"
_REASSEMBLE = "re-assemble the package (sci-adk package)"
_NO_PACKAGE_DEPOSIT_ADVICE = (
    f"{_DEPOSIT_TAG}: {PACKAGE_MANIFEST} is missing: the package was assembled before each "
    f"run's protocol history shipped with it -- {_REASSEMBLE} to ship the protocol files and "
    "their manifest"
)


_PACKAGE_OWNED_ROOTS: Tuple[str, ...] = (
    PACKAGE_PROTOCOL_DIR, PACKAGE_DATA_DIR, PACKAGE_INPUTS_DIR,
)


def _package_cell_problem(package_dir: Path, cell: str, packaged: Set[str]) -> Optional[str]:
    """Why a ``deposit.csv`` ``file`` cell is not one the package could have written, or
    ``None``: ``06_provenance/protocol/``, ``02_data/`` or ``05_inputs/``, then a packaged
    run and a plain file name, with no symbolic link on the way."""
    parts = cell.split("/")
    ok = False
    for root in _PACKAGE_OWNED_ROOTS:
        prefix = root.split("/")
        if (len(parts) == len(prefix) + 2 and parts[:len(prefix)] == prefix
                and parts[-2] in packaged and is_plain_name(parts[-1])):
            ok = True
    if not ok:
        return (f"not {', '.join(r + '/' for r in _PACKAGE_OWNED_ROOTS)} followed by a "
                "packaged run and a plain file name")
    for depth in range(1, len(parts) + 1):
        if package_dir.joinpath(*parts[:depth]).is_symlink():
            return f"{'/'.join(parts[:depth])} is a symbolic link"
    return None


def _run_evidence(run_dir: Path) -> list:
    """The run's Evidence log, read-only (the same files ``verify`` reads)."""
    from sci_adk.core.evidence import EvidenceItem

    evidence_dir = run_dir / "evidence"
    if not evidence_dir.is_dir():
        return []
    return [EvidenceItem.model_validate(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(evidence_dir.glob("*.json"))]


def _workspace_runs(workspace_dir: Path) -> Set[str]:
    runs_root = workspace_dir / "runs"
    if not runs_root.is_dir():
        return set()
    return {d.name for d in runs_root.iterdir() if d.is_dir() and (d / "spec.json").is_file()}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# How the package gate names the bibliography a declared file's ``cite`` keys resolve in: the
# package's own, which the assembler copies from the author's drop point (a placeholder with no
# entry when there is none).
_PACKAGE_BIB_NAME = "01_manuscript/references.bib, supplied via package_src/references.bib"
_RUN_INDEX = "06_provenance/run_index.csv"
_DIGEST_COLUMN = "protocol_digest_sha256"
_PROTOCOL_HISTORY = "\\section{Protocol history}"
# The digest line make_si.py prints in a run's Protocol history block ("Protocol digest:" and,
# after the line break and font commands, the 64-hex digest).
_RECORD_DIGEST_RE = re.compile(
    r"Protocol digest.{0,120}?(?<![0-9A-Fa-f])([0-9A-Fa-f]{64})(?![0-9A-Fa-f])", re.DOTALL)


def _read_text(path: Path) -> Optional[str]:
    """``path``'s UTF-8 text, or ``None`` when it is missing, a link or unreadable."""
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _run_index_digests(text: Optional[str]) -> Optional[Dict[str, str]]:
    """``{run id: protocol_digest_sha256 cell}`` of a ``run_index.csv`` text, or ``None`` when
    there is no such column."""
    if text is None:
        return None
    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or _DIGEST_COLUMN not in reader.fieldnames \
                or "run_id" not in reader.fieldnames:
            return None
        return {row["run_id"]: row[_DIGEST_COLUMN] or "" for row in reader}
    except csv.Error:
        return None


def _has_deposit_trace(package_dir: Path) -> bool:
    """Whether the package was assembled with deposit files: its ``record.tex`` has a Protocol
    history section, or its ``run_index.csv`` a ``protocol_digest_sha256`` column."""
    record = _read_text(package_dir / PACKAGE_RECORD)
    if record is not None and _PROTOCOL_HISTORY in record:
        return True
    index = _read_text(package_dir / _RUN_INDEX)
    if index is None:
        return False
    header = next(csv.reader(io.StringIO(index)), [])
    return _DIGEST_COLUMN in header


def _record_tex_escape(text: str) -> str:
    """The escaping the shipped ``make_si.py`` applies to a run id (its ``tex``: a copy of the
    renderer's one-line sanitizer, compared with it by the test suite)."""
    from sci_adk.render.paper import _latex_sanitize, _one_line

    return _latex_sanitize(_one_line(text))


def _record_digest(record: str, rid: str) -> Optional[str]:
    """The protocol digest ``record.tex`` prints in run ``rid``'s Protocol history block, or
    ``None`` when there is no such block or no digest line in it."""
    if _PROTOCOL_HISTORY not in record:
        return None
    history = record.split(_PROTOCOL_HISTORY, 1)[1].split("\\section{", 1)[0]
    head = f"\\subsection*{{Run \\texttt{{{_record_tex_escape(rid)}}}}}"
    if head not in history:
        return None
    block = history.split(head, 1)[1].split("\\subsection*{", 1)[0]
    match = _RECORD_DIGEST_RE.search(block)
    return match.group(1).lower() if match else None


def _protocol_digest_problems(
    package_dir: Path, plans: Sequence[Tuple[str, ProtocolPlan]]
) -> List[str]:
    """D11 in the package: ``run_index.csv`` (``protocol_digest_sha256``) and each run's
    Protocol history block of ``record.tex`` print the protocol digest the record computes now
    (:func:`~sci_adk.render.deposit.protocol_digest`, from ``runs/<id>/``)."""
    if not plans:
        return []
    out: List[str] = []
    cells = _run_index_digests(_read_text(package_dir / _RUN_INDEX))
    if cells is None:
        out.append(f"{_DEPOSIT_TAG}: {_RUN_INDEX} has no {_DIGEST_COLUMN} column, so it "
                   f"states no run's protocol digest -- {_REASSEMBLE}")
    record = _read_text(package_dir / PACKAGE_RECORD) or ""
    for rid, plan in plans:
        digest = protocol_digest(plan)
        tag = f"{_DEPOSIT_TAG}: run '{rid}'"
        if cells is not None and cells.get(rid) != digest:
            given = cells.get(rid)
            stated = ("has no row for the run" if given is None
                      else f"gives protocol digest {given or '(empty)'}")
            out.append(f"{tag}: {_RUN_INDEX} {stated}, but runs/{rid}/ gives protocol digest "
                       f"{digest} -- {_REASSEMBLE}")
        printed = _record_digest(record, rid)
        if printed != digest:
            stated = ("prints no protocol digest in the run's Protocol history block"
                      if printed is None else f"prints protocol digest {printed}")
            out.append(f"{tag}: {PACKAGE_RECORD} {stated}, but runs/{rid}/ gives protocol "
                       f"digest {digest} -- {_REASSEMBLE}")
    return out


# @MX:ANCHOR: [AUTO] the package's deposit-file gate -- verify_package folds it into the HARD
#   package gate; the assembler (render/package.py _write_deposit) writes what it checks.
# @MX:REASON: [AUTO] D8: the package's rows must be current at verify time (an amendment or a
#   changed declaration after packaging fails), and 06_provenance/protocol/ and the packaged
#   runs' 02_data/<id>/ and 05_inputs/<id>/ must hold exactly the files deposit.csv lists.
#   Every hash is recomputed from bytes and the expected rows are rebuilt from runs/<id>/ and
#   the declared sources; trusting deposit.csv or the copies would let a stale package pass.
def package_deposit_problems(
    workspace_dir: Path, package_dir: Path, run_ids: Sequence[str]
) -> Tuple[List[str], List[str]]:
    """The deposit-file checks of an assembled package (design/deposit-files.md D5, D8).

    READ-ONLY; every hash is recomputed from bytes and the expected ``deposit.csv`` is rebuilt
    from ``runs/<id>/``, each run's persisted ``deposit.json`` and the declared sources --
    never read from the package. For each packaged run (``run_ids``):

      - the record-side protocol comparisons (receipts vs history files, ``prior_version_id``
        links, rationales), whether the protocol ships or is withheld;
      - copies: each protocol file the run ships is at ``06_provenance/protocol/<id>/`` with
        exactly the record's bytes; each declared file it ships is at ``02_data/<id>/`` or
        ``05_inputs/<id>/`` with exactly its source's bytes;
      - the D5 data checks (recorded, derived, external against the run's Evidence; citations
        against ``01_manuscript/references.bib``; cited not shipped, terms);
      - the withheld advisory for a run that withholds its protocol;
      - an advisory for a declared file whose bytes also sit under ``04_scripts/runs/<id>/``.

    Then for the package:

      - inventory: every ``deposit.csv`` row's file exists with that SHA-256 and size; every
        file under ``06_provenance/protocol/`` and the packaged runs' ``02_data/<id>/`` and
        ``05_inputs/<id>/`` is a row; a subfolder of the protocol folder that is not a packaged
        run fails, as does a ``02_data/`` or ``05_inputs/`` subfolder named after a workspace
        run that is not packaged; one named after no workspace run gets an advisory;
      - plan: ``deposit.csv`` is the text the package writes for the record as it is now (an
        amendment, a new declaration or a re-selection since the assembly fails here);
      - names: the paths ``main.tex`` / ``si.tex`` name exist in the package
        (:func:`~sci_adk.render.deposit.package_name_problems`);
      - protocol digests: each packaged run's digest, recomputed from ``runs/<id>/``, is the
        one ``run_index.csv`` (``protocol_digest_sha256``) and the run's Protocol history block
        of ``record.tex`` print.

    A package with no trace of this feature -- no ``deposit.csv``, no
    ``06_provenance/protocol/``, no Protocol history section in ``record.tex`` and no
    ``protocol_digest_sha256`` column in ``run_index.csv`` (assembled before it) -- gets one
    advisory and no failure; any trace of it makes a missing ``deposit.csv`` or protocol
    folder fail.

    Returns ``(problems, advisories)``.
    """
    workspace_dir = Path(workspace_dir)
    package_dir = Path(package_dir)
    manifest = package_dir / PACKAGE_MANIFEST
    root = package_dir / PACKAGE_PROTOCOL_DIR
    if not (manifest.exists() or manifest.is_symlink() or root.exists() or root.is_symlink()
            or _has_deposit_trace(package_dir)):
        return [], [_NO_PACKAGE_DEPOSIT_ADVICE]

    bib_path = package_dir / "01_manuscript" / "references.bib"
    bib_text = (bib_path.read_text(encoding="utf-8", errors="replace")
                if bib_path.is_file() else None)
    problems: List[str] = []
    notes: List[str] = []
    deposits: List[Tuple[str, ProtocolPlan, DataPlan]] = []
    planned_all = True
    for rid in run_ids:
        tag = f"{_DEPOSIT_TAG}: run '{rid}'"
        run_dir = workspace_dir / "runs" / rid
        try:
            plan, data = plan_run_deposit(run_dir)
        except (OSError, ValueError) as e:
            problems.append(f"{tag}: {e}")
            planned_all = False
            continue
        fails, advice = protocol_record_problems(plan)
        problems.extend(f"{tag}: {m}" for m in fails)
        notes.extend(f"{tag}: {m}" for m in advice)
        if plan.withheld_reason is not None:
            notes.append(f"{tag}: {withheld_advisory(plan.withheld_reason)}")
        deposits.append((rid, plan, data))
        for f in plan.shipped:
            rel = f"{package_protocol_root(rid)}/{f.name}"
            copy = package_dir / rel
            if copy.is_symlink() or not copy.is_file():
                problems.append(
                    f"{_DEPOSIT_TAG}: {rel} is missing ({f.description}; the record keeps it "
                    f"as runs/{rid}/{f.record_name}) -- {_REASSEMBLE}"
                )
            elif copy.read_bytes() != f.data:
                problems.append(
                    f"{_DEPOSIT_TAG}: {rel} differs from runs/{rid}/{f.record_name} -- "
                    f"{_REASSEMBLE}"
                )
        for df in data.shipped:
            rel = f"{package_data_root(df.entry.folder, rid)}/{df.entry.name}"
            copy = package_dir / rel
            if copy.is_symlink() or not copy.is_file():
                problems.append(
                    f"{_DEPOSIT_TAG}: {rel} is missing ({df.entry.label}) -- {_REASSEMBLE}")
            elif copy.read_bytes() != df.data:
                problems.append(
                    f"{_DEPOSIT_TAG}: {rel} differs from its source {df.entry.source} -- "
                    f"{_REASSEMBLE}"
                )
        if data.files:
            data_fails, data_notes = deposit_data_problems(
                plan, data, _run_evidence(run_dir), bib_text,
                folder_of={folder: package_data_root(folder, rid)
                           for folder in (DATA_DIR, INPUTS_DIR)},
                bib_name=_PACKAGE_BIB_NAME,
            )
            problems.extend(f"{tag}: {m}" for m in data_fails)
            notes.extend(f"{tag}: {m}" for m in data_notes)
            notes.extend(f"{tag}: {m}" for m in _artifact_copies(package_dir, rid, data))

    # inventory: deposit.csv against the files, and the files against deposit.csv
    text: Optional[str] = None
    records: List[dict] = []
    if manifest.is_symlink() or not manifest.is_file():
        problems.append(f"{_DEPOSIT_TAG}: {PACKAGE_MANIFEST} is missing -- {_REASSEMBLE}")
    else:
        try:
            text = manifest.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.append(f"{_DEPOSIT_TAG}: {PACKAGE_MANIFEST} is not UTF-8 text")
        if text is not None:
            parsed = package_manifest_records(text)
            if parsed is None:
                problems.append(
                    f"{_DEPOSIT_TAG}: {PACKAGE_MANIFEST} does not have the columns "
                    f"{','.join(PACKAGE_MANIFEST_COLUMNS)}"
                )
            else:
                records = parsed
    packaged = set(run_ids)
    listed = {r["file"]: r for r in records if r["file"]}
    for rel, row in sorted(listed.items()):
        reason = _package_cell_problem(package_dir, rel, packaged)
        if reason:
            problems.append(f"{_DEPOSIT_TAG}: {PACKAGE_MANIFEST} row file {rel!r}: {reason}")
            continue
        path = package_dir / rel
        if not path.is_file():
            problems.append(
                f"{_DEPOSIT_TAG}: {rel} is listed in {PACKAGE_MANIFEST} but missing -- "
                f"{_REASSEMBLE}")
            continue
        held = path.read_bytes()
        actual = hashlib.sha256(held).hexdigest()
        if actual != row["sha256"]:
            problems.append(
                f"{_DEPOSIT_TAG}: {rel}: its SHA-256 {actual} differs from the one "
                f"{PACKAGE_MANIFEST} gives, {row['sha256'] or '(empty)'}"
            )
        if str(len(held)) != row["bytes"]:
            problems.append(
                f"{_DEPOSIT_TAG}: {rel}: {len(held)} bytes, {PACKAGE_MANIFEST} says "
                f"{row['bytes'] or '(empty)'}"
            )
    if root.is_symlink():
        problems.append(f"{_DEPOSIT_TAG}: {PACKAGE_PROTOCOL_DIR} is a symbolic link -- "
                        f"{_REASSEMBLE}")
    elif root.is_dir():
        for child in sorted(root.iterdir()):
            if child.name not in packaged or child.is_symlink() or not child.is_dir():
                problems.append(
                    f"{_DEPOSIT_TAG}: {PACKAGE_PROTOCOL_DIR}/{child.name} is not the folder "
                    f"of a packaged run; the package rebuilds {PACKAGE_PROTOCOL_DIR}/ whole "
                    f"-- {_REASSEMBLE}"
                )
                continue
            problems.extend(_unlisted(package_dir, child, listed))
    workspace_runs = _workspace_runs(workspace_dir)
    for folder in (PACKAGE_DATA_DIR, PACKAGE_INPUTS_DIR):
        base = package_dir / folder
        if not base.is_dir() or base.is_symlink():
            continue
        for child in sorted(base.iterdir()):
            if not (child.is_dir() or child.is_symlink()):
                continue                       # claims_all.csv, README.md: not a namespace
            where = f"{folder}/{child.name}"
            if child.name in packaged:
                if child.is_symlink():
                    problems.append(f"{_DEPOSIT_TAG}: {where} is a symbolic link -- "
                                    f"{_REASSEMBLE}")
                    continue
                problems.extend(_unlisted(package_dir, child, listed))
            elif child.name in workspace_runs:
                problems.append(
                    f"{_DEPOSIT_TAG}: {where} belongs to run '{child.name}', which is not "
                    f"packaged; the package rebuilds it -- {_REASSEMBLE}"
                )
            else:
                notes.append(
                    f"{_DEPOSIT_TAG}: {where} is named after no run of the workspace; it is "
                    "not the package's and ships unchecked"
                )

    # plan: deposit.csv is what the record calls for now
    if text is not None and planned_all:
        record = package_dir / PACKAGE_RECORD
        record_text = record.read_text(encoding="utf-8") if record.is_file() else None
        expected = package_manifest_text(package_rows(
            [(rid, plan) for rid, plan, _ in deposits], record_text,
            {rid: data for rid, _, data in deposits},
        ))
        if text != expected:
            problems.extend(
                f"{_DEPOSIT_TAG}: {line} -- {_REASSEMBLE}"
                for line in package_manifest_differences(text, expected)
            )

    # names: the package paths main.tex / si.tex name (D8)
    docs: Dict[str, str] = {}
    for name in ("main.tex", "si.tex"):
        doc = package_dir / "01_manuscript" / name
        if doc.is_file():
            docs[name] = doc.read_text(encoding="utf-8", errors="replace")
    problems.extend(
        f"{_DEPOSIT_TAG}: {m}" for m in package_name_problems(package_dir, docs, deposits))

    # protocol digests: run_index.csv and record.tex print what runs/<id>/ computes now (D11)
    problems.extend(_protocol_digest_problems(
        package_dir, [(rid, plan) for rid, plan, _ in deposits]))
    return problems, notes


def _unlisted(package_dir: Path, folder: Path, listed: dict) -> List[str]:
    out: List[str] = []
    for path in sorted(folder.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        rel = path.relative_to(package_dir).as_posix()
        if rel not in listed:
            out.append(
                f"{_DEPOSIT_TAG}: {rel} is not in {PACKAGE_MANIFEST}: the package did not "
                f"write it -- {_REASSEMBLE}"
            )
    return out


def _artifact_copies(package_dir: Path, rid: str, data: DataPlan) -> List[str]:
    """D8: a declared file whose bytes also sit under ``04_scripts/runs/<id>/`` (the
    wholesale copy of ``runs/<id>/artifacts/``) -- shipped twice, or shipped there although
    the declaration does not ship it."""
    scripts = package_dir / "04_scripts" / "runs" / rid
    if not scripts.is_dir():
        return []
    by_sha: Dict[str, List[str]] = {}
    for path in sorted(scripts.rglob("*")):
        if path.is_file() and not path.is_symlink():
            by_sha.setdefault(_sha256_file(path), []).append(
                path.relative_to(package_dir).as_posix())
    out: List[str] = []
    for df in data.files:
        for copy in by_sha.get(df.sha256, []):
            if df.entry.ships:
                checked = f"{package_data_root(df.entry.folder, rid)}/{df.entry.name}"
                out.append(
                    f"{df.entry.label} ships twice: {checked} and {copy}; the {checked} copy "
                    "is the checked one"
                )
            else:
                out.append(
                    f"{copy} ships {df.entry.label} although the declaration does not ship it "
                    f"({df.entry.not_shipped_reason()})"
                )
    return out


__all__ = [
    "PACKAGE_FOLDERS",
    "PACKAGE_RECORD_NAME",
    "package_record_path",
    "layout_problems",
    "cited_keys",
    "bib_keys",
    "bib_article_number_advisories",
    "bib_command_advisories",
    "bib_command_problems",
    "bib_latex_safety_problems",
    "bib_month_advisories",
    "bib_sort_advisories",
    "bibliography_stems",
    "font_encoding_problems",
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
    "deposit_completeness_problems",
    "package_deposit_problems",
]
