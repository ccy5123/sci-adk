"""
Reproduction bundle renderers (F3, design/paper-publishing-requirements.md §3).

F3 retains the GENERATING CODE with the paper in two complementary forms, BOTH
derived from the record's ``provenance.code_ref`` (evidence.py:161):

  - a "Reproduction code" section in the deposit record -- each distinct script the record
    names, once, INLINED as a LaTeX ``lstlisting`` (a ``code_ref`` that names no shipped
    script is recorded as a POINTER line, honestly, because no body is held);
  - ``paper/reproduce.py`` -- a MANIFEST AND HASH CHECK. The record holds each script and
    its sha256, but no command-line arguments or input mapping, so the bundle cannot
    re-run the scripts as they were run; ``reproduce.py`` therefore runs none of them. It
    lists each script shipped under ``paper/code/``, the recorded results it backs (in the
    researcher's words, never by record id) and the data those results name -- including
    the data files a ``code_ref`` names with a hash, which are listed with that hash and
    never shipped -- and checks every shipped script against its recorded hash. Record ids
    and the verbatim ``code_ref``s live only in its clearly marked machine section (the F3
    gate reads them).

This module is PURE (data in, string out): it imports nothing from ``loop``/``runner``
and never touches the filesystem -- the COMPILER (``loop/compiler.py``, the sole
filesystem toucher) resolves each ``code_ref`` to the scripts it names, builds the
:class:`ReproListing` list, lands ``paper/code/`` + ``paper/reproduce.py``, and feeds the
resolved listings to these renderers and to :func:`sci_adk.render.si.render_si_latex`.
The code listing lives in the record dump, NEVER in the tool-agnostic ``draft.tex``
(design/paper-publishing-requirements.md §0).

Determinism: same inputs -> byte-identical strings. An empty listing list -> ``""`` (the
record emits no "Reproduction code" section and no ``listings`` package, and no
``paper/code/`` or ``reproduce.py`` is written) -- the F3 backward-compatibility /
regression invariant.

Reference: design/paper-publishing-requirements.md (F3 §3), design/abstractions.md
(Provenance / code_ref), design/directory-structure.md (render/, runner/).
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sci_adk.render.paper import _latex_sanitize

# The LaTeX listings environment cannot verbatim-hold a body that itself contains the
# closing delimiter. Such a script is still SHIPPED under paper/code/ (byte for byte); the
# record names it without typesetting its body, so the record is never a broken document.
_LSTLISTING_END = r"\end{lstlisting}"

# The reproduce.py layout version, written into its machine section. A re-render reads the
# previous reproduce.py to learn which paper/code/ files the previous render wrote: in this
# format each SCRIPTS entry starts with the file name; the original driver (no
# BUNDLE_FORMAT) listed ``(evidence_id, code_ref, filename)``.
BUNDLE_FORMAT = 2

# The marker that opens the machine section of reproduce.py.
MACHINE_SECTION_MARKER = (
    "# ---- Machine section: generated from the run record by sci-adk; do not edit. ----"
)

# First-sentence boundary candidates for a reader summary: sentence punctuation, whitespace,
# then a capital letter or an opening bracket ("al. 1979" and "LogP_QR.sdf)" do not split).
# A candidate whose last word is an abbreviation (_ABBREVIATIONS, an initial "J.", or a
# dotted form "e.g.") is not a boundary.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")
_SUMMARY_LIMIT = 160

# @MX:NOTE: [AUTO] abbreviations a finding uses before a capitalised word, so a period after
#   them does not end the first sentence ("Environ. Rev.", "et al. Table", "Fig. S3"). A
#   heuristic list (lower-case, no trailing period): a missing entry only makes a summary
#   end early; a wrong entry only makes it run on to the 160-character cap.
_ABBREVIATIONS = frozenset(
    {
        "al", "cf", "vs", "approx", "ca", "resp", "fig", "figs", "eq", "eqs", "eqn",
        "tab", "ref", "refs", "sec", "sect", "ch", "ed", "eds", "suppl", "ser", "rep",
        "dr", "mr", "mrs", "ms", "prof", "st", "inc", "ltd", "co", "corp", "jr", "sr",
        "dept", "univ", "sp", "spp", "var",
        # journal-title words
        "acad", "am", "anal", "ann", "appl", "aquat", "assess", "biochem", "biol", "bull",
        "chem", "comput", "contam", "ecol", "ecotoxicol", "eng", "env", "environ", "evol",
        "geophys", "int", "lett", "manag", "mar", "math", "med", "mol", "nat", "natl",
        "org", "pharmacol", "phys", "pollut", "proc", "res", "rev", "saf", "sci", "soc",
        "stat", "technol", "toxicol", "trans",
    }
)

# An internal approach number: the MethodPlan's list index as a researcher writes it
# ("approach [13]", "approaches [9]-[10]", "approach-[5]"). The reader of the bundle has no
# such list, and the record does not fix whether the numbering starts at 0 or 1, so the
# number is never turned into a title (it could name the wrong approach): it is dropped.
# Written bracketed ("approach [13]"), or bare after "method" ("Spec method approach 4": a
# bare "approaches 1" elsewhere is the English verb, never touched).
_METHOD_PREFIX = r"\b(?:[Ss]pec\s+)?[Mm]ethod\s+"
_APPROACH_REF = (
    r"(?:" + _METHOD_PREFIX + r"[Aa]pproach(?:es)?[ -]?\[?\d+\]?"
    r"(?:\s*(?:-|\u2013)\s*\[?\d+\]?)*"
    r"|\b[Aa]pproach(?:es)?[ -]?\[\d+\](?:\s*(?:-|\u2013|to|and|,)\s*\[\d+\])*)"
)
# ONE approach (not a range): it can only label one step.
_APPROACH_ONE = (
    r"(?:" + _METHOD_PREFIX + r"[Aa]pproach[ -]?\[?\d+\]?(?![\d\]])"
    r"|\b[Aa]pproach[ -]?\[\d+\])"
)
# The number used as a LABEL, where only the number goes:
#   - in front of a colon at the start of a clause ("Approach [6]: chemical identifier",
#     "(Spec method approach 4: exclude ...)") -- the colon goes with it;
#   - at the start of a clause in front of the researcher's own name for the step
#     ("Approach [2] chemical structure", "... and approach [6] aggregation");
#   - one approach, anywhere, in front of a word ("kept after approach [1] filtering", "the
#     approach [5] sources"). A RANGE used mid-clause ("passing approaches [1]-[6]
#     restricted to") is a noun: stripping it would leave a fragment, so it is a reference.
_APPROACH_COLON_LABEL = re.compile(
    r"(^|\(|[,;:]\s+|\b(?:and|or)\s+)" + _APPROACH_REF + r"\s*:\s*"
)
_APPROACH_LABEL = re.compile(
    r"(^|[,;:]\s+|\(|\b(?:and|or)\s+)" + _APPROACH_REF + r"\s+(?=[A-Za-z])"
)
_APPROACH_ONE_LABEL = re.compile(_APPROACH_ONE + r"\s+(?=[A-Za-z])")
# The words that introduce a reference at the end of the text before it ("for <id>",
# "recorded in <id>", "see <id>"): a clause is cut there and keeps what comes before.
_PREPOSITION_BEFORE_REFERENCE = re.compile(
    r"(?:^|\s+)(?:as\s+)?"
    r"(?:(?:recorded|reported|described|listed|given|built|read|shown|derived|computed|"
    r"stated|defined|taken|kept|written|noted|documented|cited|named|used)\s+)?"
    r"(?:in|of|for|from|by|see|to|on|at|with|per|under|cf\.)\s*$",
    re.IGNORECASE,
)
# @MX:NOTE: [AUTO] words that NEED the preposition after them ("relative to <id>", "differs
#   from <id>", "and not from <id>"): cutting the clause at that preposition prints a
#   fragment ("The slope was lower relative."), so the sentence goes instead. A heuristic
#   list: a missing word lets a fragment through; an extra one only drops a sentence (a
#   summary then falls back to the output name).
_GOVERNING_WORDS = frozenset(
    {
        "relative", "compared", "comparison", "according", "due", "owing", "similar",
        "dissimilar", "different", "differs", "differ", "differed", "differing", "distinct",
        "identical", "equal", "equivalent", "close", "closer", "next", "prior", "contrary",
        "opposed", "consistent", "inconsistent", "agree", "agrees", "agreed", "agreement",
        "contrast", "instead", "rather", "apart", "aside", "based", "depends", "depend",
        "depending", "dependent", "independent", "relation", "respect", "regard",
        "addition", "place", "favour", "favor", "line", "more", "less", "than", "same",
        "like", "unlike", "versus", "vs", "and", "or", "not", "nor", "but", "both",
        "either", "neither",
    }
)
# The first word may be capitalised after the clause before it was removed only when it is
# a plain lower-case word (never a file name such as "s3_counts.json").
_PLAIN_FIRST_WORD = re.compile(r"[a-z][a-z-]*[,;:]?")


@dataclass(frozen=True)
class ReproScript:
    """One distinct script shipped under ``paper/code/``.

    Attributes:
        filename: its ``paper/code/`` name -- the script's own file name, or that name with
            a ``_<sha256 prefix>`` suffix when different contents share the name.
        sha256: the sha256 of ``data`` (equal to the recorded hash when one was recorded).
        hash_recorded: whether a ``code_ref`` records this hash (else it was computed when
            the bundle was rendered).
        text: the body as text for the record listing, or ``None`` (not UTF-8 text).
        data: the exact bytes shipped (so the shipped copy keeps the recorded hash).
    """

    filename: str
    sha256: str
    hash_recorded: bool
    text: Optional[str] = None
    data: bytes = b""


@dataclass(frozen=True)
class ReproListing:
    """One Evidence item's reproduction entry, as resolved by the compiler.

    ``kind="script"`` when the item's ``code_ref`` names at least one shipped script
    (``scripts``, in the order the ``code_ref`` names them); ``kind="pointer"`` when it
    names none (a bare commit/ref, a missing file, a file whose hash no longer matches) --
    NOTHING is fabricated for a pointer. ``text``/``filename`` mirror the first shipped
    script (and, when ``scripts`` is empty, describe the single script on their own -- the
    original one-script shape). ``unshipped`` holds the SOURCE paths the ``code_ref`` names
    WITH a hash that are not shipped; ``data_files`` the ``(path, sha256)`` data references
    it names (listed, never shipped). ``summary`` describes the result in the researcher's
    words (no record ids); ``output_ref`` / ``data_ref`` are the item's recorded artifact and
    data.
    """

    evidence_id: str
    code_ref: str
    kind: str  # "script" | "pointer"
    text: Optional[str] = None       # first shipped script's body, else None
    filename: Optional[str] = None   # first shipped script's paper/code/ name, else None
    scripts: Tuple[ReproScript, ...] = ()
    unshipped: Tuple[str, ...] = ()
    summary: str = ""
    output_ref: Optional[str] = None
    data_ref: Optional[str] = None
    data_files: Tuple[Tuple[str, str], ...] = ()

    @property
    def all_scripts(self) -> Tuple[ReproScript, ...]:
        """Every shipped script this item names (one, from ``text``/``filename``, when
        ``scripts`` was not given)."""
        if self.scripts:
            return self.scripts
        if self.kind == "script" and self.text is not None:
            data = self.text.encode("utf-8")
            return (
                ReproScript(
                    filename=self.filename or f"{self.evidence_id}.py",
                    sha256=hashlib.sha256(data).hexdigest(),
                    hash_recorded=False,
                    text=self.text,
                    data=data,
                ),
            )
        return ()

    @property
    def is_script(self) -> bool:
        return self.kind == "script" and bool(self.all_scripts)


def listing_inlinable(text: str) -> bool:
    """Whether a script body can be SAFELY inlined as an ``lstlisting``.

    ``listings`` typesets its body verbatim, but cannot hold a body that itself contains
    the closing ``\\end{lstlisting}`` delimiter. Pure + deterministic.
    """
    return _LSTLISTING_END not in text


def _typeset(script: ReproScript) -> bool:
    return script.text is not None and listing_inlinable(script.text)


def reproduction_uses_listings(listings: Optional[Sequence[ReproListing]]) -> bool:
    """Whether the record preamble must add ``\\usepackage{listings}`` for these entries.

    True iff at least one shipped script is typeset (only then is an ``lstlisting``
    emitted). A pointer-only (or empty/``None``) set needs no ``listings`` package, so the
    preamble stays byte-identical to today -- the same per-kind guarding the record already
    uses for ``pgfplots``/``graphicx`` (design/paper-publishing-requirements.md F2/F3).
    """
    return any(
        _typeset(script)
        for item in (listings or [])
        if item.is_script
        for script in item.all_scripts
    )


def bundle_scripts(listings: Optional[Sequence[ReproListing]]) -> List[ReproScript]:
    """The distinct shipped scripts, one per ``paper/code/`` file, in first-named order."""
    seen: Dict[str, ReproScript] = {}
    for item in listings or []:
        if not item.is_script:
            continue
        for script in item.all_scripts:
            seen.setdefault(script.filename, script)
    return list(seen.values())


# @MX:NOTE: [AUTO] the ONE naming rule for paper/code/: the compiler names the shipped copies
#   with it and verify re-derives the names to check reproduce.py's script list. Changing it
#   fails every existing render's gate until it is re-rendered.
def bundle_file_names(contents: Sequence[Tuple[str, str]]) -> Dict[str, str]:
    """``paper/code/`` names for distinct script contents: ``(sha256, file name)`` pairs. PURE.

    A file name used by exactly one content is kept as-is. A name shared by different
    contents gets ``<stem>_<first 8 hex of its sha256><suffix>`` on EVERY one of them, so
    the choice does not depend on which was named first (a longer prefix in the unlikely
    case the suffixed name is taken). The compiler names the shipped copies with it and
    ``verify`` re-derives the same names to check ``reproduce.py``'s script list.
    """
    by_name: Dict[str, List[str]] = {}
    for sha, name in contents:
        by_name.setdefault(name, []).append(sha)
    chosen: Dict[str, str] = {}
    used = {name for name, shas in by_name.items() if len(shas) == 1}
    for name, shas in by_name.items():
        if len(shas) == 1:
            chosen[shas[0]] = name
            continue
        dot = name.rfind(".")
        stem, suffix = (name[:dot], name[dot:]) if dot > 0 else (name, "")
        for sha in shas:
            width = 8
            candidate = f"{stem}_{sha[:width]}{suffix}"
            while candidate in used:
                width += 4
                candidate = f"{stem}_{sha[:width]}{suffix}"
            used.add(candidate)
            chosen[sha] = candidate
    return chosen


# @MX:NOTE: [AUTO] reader-facing text never gets a placeholder for a reference it cannot
#   show (an earlier version printed "another recorded result" 17 times on a real run):
#   the reference leaves with the smallest clause around it.
def reader_text(text: Optional[str], known_ids: Iterable[str] = ()) -> str:
    """``text`` with every reference its reader cannot resolve removed. PURE.

    The references are the record ids in ``known_ids`` and the MethodPlan's internal
    approach numbers ("approach [13]", "Spec method approach 4"). Nothing is put in their
    place, and no fragment is left where one stood:

      - an approach number used as a label loses the number: before a colon at the start
        of a clause ("Approach [6]: identifier" -> "identifier"), before the researcher's
        own name for the step ("Approach [2] chemical structure" -> "chemical structure"),
        and -- one approach, not a range -- before any word ("kept after approach [1]
        filtering" -> "kept after filtering");
      - inside brackets, the comma/semicolon-separated part holding a reference goes, and
        brackets left empty go with the space before them ("(H1: b >= 0.7, <id>)" ->
        "(H1: b >= 0.7)", "(approach [13])" -> "");
      - elsewhere the clause holding it (text between ``, `` ``; `` ``: ``) is cut where a
        preposition introduces the reference ("Named values for <id>" -> "Named values",
        "chemicals recorded in <id>" -> "chemicals"), or removed when it holds nothing but
        the reference ("see <id>").
      - a reference that cannot leave that way -- the clause goes on after it ("Value
        differs from <id> by 0.02"), the word before the preposition needs it ("lower
        relative to <id>", "and not from <id>"), or no preposition introduces it in a
        clause that says more ("The fit used <id>") -- takes its whole clause with it when
        another clause comes before ("The slope was 0.77, lower relative to <id>." ->
        "The slope was 0.77."), and its whole SENTENCE when it sits in the first clause.

    Then spacing and punctuation are tidied: the end punctuation is kept, and a first word
    left lower-case by a removed clause is capitalised when the sentence began with a
    capital. A sentence with no reference only has its whitespace collapsed.
    """
    original = " ".join((text or "").split())
    if not original:
        return ""
    reference = _reference_pattern(known_ids)
    kept: List[str] = []
    for sentence in _sentences(original):
        out = _APPROACH_COLON_LABEL.sub(r"\1", sentence)
        out = _APPROACH_LABEL.sub(r"\1", out)
        out = _APPROACH_ONE_LABEL.sub("", out)
        if reference.search(out):
            out = _drop_references(out, reference, (", ", "; ", ": "))
            if out is None:
                continue  # the reference cannot leave without leaving a fragment
        out = sentence if out == sentence else _tidy(out, sentence)
        if out:
            kept.append(out)
    return " ".join(kept)


def reader_summary(
    finding: Optional[str],
    known_ids: Iterable[str] = (),
    *,
    fallback: str = "",
) -> str:
    """A short description of a recorded result for a reader. PURE.

    The first sentence of the finding (of its ``"summary"`` when the finding is a JSON
    object carrying one; a period after an abbreviation such as "Environ." or "et al." does
    not end it), with whitespace collapsed and every reference a reader cannot resolve
    removed by :func:`reader_text`, capped at 160 characters at a word boundary. An empty
    finding, or a first sentence that was nothing but such references -> ``fallback``.
    """
    text = (finding or "").strip()
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict) and isinstance(parsed.get("summary"), str):
            text = parsed["summary"].strip()
    text = " ".join(text.split())
    if not text:
        return fallback
    sentence = reader_text(_first_sentence(text), known_ids)
    if not re.search(r"\w", sentence):
        return fallback
    if len(sentence) > _SUMMARY_LIMIT:
        cut = sentence[: _SUMMARY_LIMIT - 3].rsplit(" ", 1)[0].rstrip(" ,;:")
        sentence = cut + "..."
    return sentence


def _first_sentence(text: str) -> str:
    """Text up to the first sentence boundary that does not follow an abbreviation."""
    return _sentences(text)[0]


def _sentences(text: str) -> List[str]:
    """``text`` split at every sentence boundary that does not follow an abbreviation (the
    whitespace at each boundary dropped)."""
    out: List[str] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        last_word = text[start: match.start()].rsplit(" ", 1)[-1]
        if not _is_abbreviation(last_word):
            out.append(text[start: match.start()])
            start = match.end()
    out.append(text[start:])
    return out


def _is_abbreviation(word: str) -> bool:
    """Whether ``word`` (ending in the punctuation just before a candidate boundary) is an
    abbreviation: an initial ("J."), a dotted form ("e.g.", "U.S."), or a listed word."""
    if not word.endswith("."):
        return False
    bare = word[:-1].lstrip("([{\"'")
    return (
        re.fullmatch(r"[A-Z]", bare) is not None
        or re.fullmatch(r"(?:[A-Za-z]\.)+[A-Za-z]", bare) is not None
        or bare.lower() in _ABBREVIATIONS
    )


def _reference_pattern(known_ids: Iterable[str]) -> re.Pattern[str]:
    ids = sorted({i for i in known_ids if i}, key=len, reverse=True)
    alternatives = [_APPROACH_REF]
    if ids:
        alternatives.insert(
            0, r"(?<![\w-])(?:" + "|".join(map(re.escape, ids)) + r")(?![\w-])"
        )
    return re.compile("|".join(alternatives))


def _drop_references(
    text: str,
    reference: re.Pattern[str],
    separators: Tuple[str, ...],
    *,
    in_brackets: bool = False,
) -> Optional[str]:
    """Remove every reference from ``text`` with the smallest unit around it (see
    :func:`reader_text`): bracketed parts first, then the clauses split at ``separators``.

    A clause that cannot lose its reference without leaving a fragment goes whole when
    another clause comes before it ("..., reported in <id> but not yet named" -- the main
    clause stands without it). ``None`` when it is the FIRST clause -- the sentence's main
    clause is broken, and the caller drops the sentence. Inside brackets such a part simply
    goes (``in_brackets``): the bracket then reads as if the part had never been written."""
    text = _drop_in_brackets(text, reference)
    if not reference.search(text):
        return text
    kept: List[str] = []
    for index, (unit, separator) in enumerate(_split_top_level(text, separators)):
        if reference.search(unit):
            cut = _clause_without_reference(unit, reference)
            if cut is None and index == 0 and not in_brackets:
                return None
            unit = cut or ""
        if re.search(r"\w", unit):
            kept.append(unit + separator)
    return "".join(kept)


def _drop_in_brackets(text: str, reference: re.Pattern[str]) -> str:
    out: List[str] = []
    i = 0
    while i < len(text):
        if text[i] not in "([":
            out.append(text[i])
            i += 1
            continue
        end = _closing_bracket(text, i)
        if end is None:  # unbalanced: leave the rest as written
            out.append(text[i:])
            break
        inner = text[i + 1:end]
        if reference.search(inner):
            inner = (_drop_references(inner, reference, (", ", "; "), in_brackets=True)
                     or "").strip().rstrip(",;:")
            if not re.search(r"\w", inner):
                out = ["".join(out).rstrip(" ")]  # the group goes, with the space before it
                i = end + 1
                continue
        out.append(text[i] + inner + text[end])
        i = end + 1
    return "".join(out)


def _closing_bracket(text: str, start: int) -> Optional[int]:
    depth = 0
    for j in range(start, len(text)):
        if text[j] in "([":
            depth += 1
        elif text[j] in ")]":
            depth -= 1
            if depth == 0:
                return j
    return None


def _split_top_level(text: str, separators: Tuple[str, ...]) -> List[Tuple[str, str]]:
    """``text`` split at ``separators`` outside brackets: ``(unit, separator after it)``."""
    units: List[Tuple[str, str]] = []
    depth, start, i = 0, 0, 0
    while i < len(text):
        char = text[i]
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        elif depth == 0:
            separator = next((s for s in separators if text.startswith(s, i)), None)
            if separator is not None:
                units.append((text[start:i], separator))
                i += len(separator)
                start = i
                continue
        i += 1
    units.append((text[start:], ""))
    return units


def _clause_without_reference(unit: str, reference: re.Pattern[str]) -> Optional[str]:
    """``unit`` without its references, or ``None`` when that would leave a fragment.

    The part before the preposition that introduces the first reference ("Named values"
    from "Named values for <id>"); ``""`` when the unit holds nothing else ("see <id>").
    ``None`` when the unit goes on after its last reference, when no preposition
    introduces it but the unit says more, or when the word before the preposition needs
    it (:data:`_GOVERNING_WORDS`: "relative to", "and not from")."""
    matches = list(reference.finditer(unit))
    if not matches:
        return unit
    if re.search(r"\w", unit[matches[-1].end():]):
        return None
    head = unit[: matches[0].start()]
    introduced = _PREPOSITION_BEFORE_REFERENCE.search(head)
    if introduced is None:
        return None if re.search(r"\w", head) else ""
    kept = head[: introduced.start()]
    words = kept.split()
    if words and words[-1].lower().strip(",;:") in _GOVERNING_WORDS:
        return None
    return kept


def _tidy(text: str, original: str) -> str:
    text = " ".join(text.split())
    text = re.sub(r"\s+([,;:.!?)\]])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    text = text.strip().lstrip(",;:").strip()
    text = re.sub(r"^(?:and|or|but)\s+", "", text, flags=re.IGNORECASE)
    text = text.rstrip(" ,;:")
    if not text:
        return ""
    end = original[-1]
    if end in ".!?" and text[-1] not in ".!?":
        text += end
    first = text.split(" ", 1)[0]
    if original[0].isupper() and _PLAIN_FIRST_WORD.fullmatch(first):
        text = text[0].upper() + text[1:]
    return text


def render_reproduction_section(
    listings: Optional[Sequence[ReproListing]],
) -> str:
    """Render the record's "Reproduction code" section body (or ``""`` when there is nothing).

    Walking the entries in the GIVEN order (deterministic):
      - each shipped script is emitted ONCE, at its first appearance: its body verbatim in
        an ``lstlisting`` (NOT LaTeX-escaped -- ``listings`` handles raw code) under a
        sanitized caption naming ``paper/code/<file>``, its sha256 and the record ids of
        every entry that names it; a script whose body cannot be typeset (not text, or it
        contains ``\\end{lstlisting}``) is named in one line instead;
      - a ``pointer`` entry emits one honest POINTER line recording the ``code_ref``.

    An empty or ``None`` list returns ``""`` so the record emits NO section (the F3
    regression invariant: a run with no ``code_ref`` is byte-identical to today). PURE
    + deterministic.
    """
    items = list(listings or [])
    if not items:
        return ""

    named_by: Dict[str, List[str]] = {}
    for item in items:
        if not item.is_script:
            continue
        for script in item.all_scripts:
            ids = named_by.setdefault(script.filename, [])
            if item.evidence_id not in ids:
                ids.append(item.evidence_id)

    lines: List[str] = [r"\section{Reproduction code}"]
    lines.append(
        "The generating code the recorded results name, each distinct script once. Each is "
        r"shipped byte for byte under \texttt{paper/code/}; \texttt{python "
        r"paper/reproduce.py} checks the shipped copies against the SHA-256 hashes the "
        "record holds. It does not re-run them: the record holds no command-line "
        "arguments or input files for them. A code reference that names no shipped script "
        "is recorded as a pointer (the body is not held)."
    )
    lines.append("")
    emitted: set[str] = set()
    for item in items:
        if item.is_script:
            for script in item.all_scripts:
                if script.filename in emitted:
                    continue
                emitted.add(script.filename)
                caption = _latex_sanitize(
                    f"paper/code/{script.filename} -- sha256 {script.sha256} -- named by "
                    + ", ".join(named_by[script.filename])
                )
                if _typeset(script):
                    lines.append(r"\begin{lstlisting}[basicstyle=\ttfamily\small,"
                                 f"caption={{{caption}}},breaklines=true]")
                    # Body is verbatim -- listings handles raw code; NEVER _latex_sanitize
                    # here (that would corrupt the source). _typeset guarantees the body
                    # has no \\end{lstlisting}, so this cannot break.
                    lines.append(script.text or "")
                    lines.append(r"\end{lstlisting}")
                else:
                    lines.append(
                        r"\noindent\textbf{Script:} " + caption
                        + r" (shipped; its body is not typeset here). \\"
                    )
                lines.append("")
        else:
            lines.append(
                r"\noindent\textbf{Pointer:} \texttt{"
                f"{_latex_sanitize(item.evidence_id)}"
                r"} -- code\_ref \texttt{"
                f"{_latex_sanitize(item.code_ref)}"
                r"} (a recorded reference; no co-located script body is held). "
                r"\\"
            )
            lines.append("")
    return "\n".join(lines).rstrip("\n")


_DOC_RUNS_NOTHING = """\
This script runs none of the scripts it lists. The run record holds each script
that produced a recorded result and the script's SHA-256 hash, but not the
command-line arguments or the input files each script was run with, so the
scripts cannot be re-run from this bundle as they were run."""

_DOC_WHAT_IT_DOES = """\
What it does: for each script under code/ it prints the recorded results the
script produced and the data those results name, and checks that the script is
present with the SHA-256 hash listed for it. It exits 0 when every listed script
is present with that hash, and 1 otherwise."""

_DOC_UNRECORDED_HASH = """\
For a script the record holds no hash for, the hash listed is the one computed
when this bundle was rendered."""

_DOC_DATA_FILES = """\
Data files a code reference names with a SHA-256 hash are listed with that hash.
They are not shipped with this bundle; compare the hash with your own copy."""

_DOC_NO_SCRIPT = """\
No script is shipped with this paper: no code reference in the record names a
file this bundle holds. The references are printed for the reader; there is
nothing to check, and it exits 0."""

_DRIVER_MAIN = '''

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _replace_unprintable_characters() -> None:
    """Print a character the console encoding cannot show as '?' instead of stopping."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main() -> int:
    _replace_unprintable_characters()
    code_dir = Path(__file__).resolve().parent / "code"
    backs = {}
    data_files = {}
    for _record_id, _ref, files, summary, output, data, _unshipped, named_data in RESULTS:
        for name in files:
            backs.setdefault(name, []).append((summary, output, data))
            listed = data_files.setdefault(name, [])
            listed.extend(pair for pair in named_data if pair not in listed)

    if SCRIPTS:
        print(f"{_plural(len(SCRIPTS), 'script')} under code/ produced the recorded "
              "results. None is run here; each is checked against its SHA-256 hash.")
    else:
        print("No script is shipped with this paper: no code reference in the record "
              "names a file this bundle holds.")

    matched = 0
    for name, digest, recorded in SCRIPTS:
        path = code_dir / name
        if not path.is_file():
            status = "MISSING"
        elif _sha256(path) != digest:
            status = "HASH DIFFERS"
        else:
            status = "ok"
            matched += 1
        source = ("recorded" if recorded
                  else "computed when this bundle was rendered; the record holds none")
        print()
        print(f"code/{name}  sha256 {digest} ({source}): {status}")
        results = backs.get(name, [])
        print(f"  produced {_plural(len(results), 'recorded result')}:")
        data_seen = []
        for summary, output, data in results:
            print(f"    - {summary}")
            if output:
                print(f"      output: {output}")
            if data and data not in data_seen:
                data_seen.append(data)
        if data_seen:
            print("  data named by these results:")
            for data in data_seen:
                print(f"    - {data}")
        if data_files.get(name):
            print("  data files the code references name (not shipped; recorded SHA-256):")
            for data_path, data_digest in data_files[name]:
                print(f"    - {data_path}  sha256 {data_digest}")

    unshipped = []
    for _record_id, _ref, files, _summary, _output, _data, paths, _named in RESULTS:
        if files:
            unshipped.extend(p for p in paths if p not in unshipped)
    if unshipped:
        print()
        print("Scripts the record names with a hash but this bundle does not hold "
              "(missing, or changed since they were recorded):")
        for path in unshipped:
            print(f"  - {path}")

    pointers = [(entry[1], entry[3]) for entry in RESULTS if not entry[2]]
    if pointers:
        print()
        print("Code references that name no script under code/ (listed, not checked):")
        for ref, summary in pointers:
            print(f"  - {ref}  ({summary})")

    if SCRIPTS:
        print()
        print(f"{matched} of {len(SCRIPTS)} scripts match the hash listed for them.")
    return 0 if matched == len(SCRIPTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def render_reproduce_driver(
    listings: Optional[Sequence[ReproListing]],
    spec_id: str,
) -> str:
    """Render ``paper/reproduce.py``: a manifest of the shipped code and a hash check.

    It runs NOTHING: the record holds the scripts and their hashes but no argv or input
    mapping, so the bundle cannot re-run them, and the docstring says exactly that. When
    run (stdlib only -- no sci-adk, no docker), it prints each shipped script with the
    recorded results it backs (``summary``, no record ids), their outputs, the data they
    name and the data files their ``code_ref``s name with a hash (listed, never shipped),
    checks every shipped file's sha256, lists the hashed scripts named but not shipped and
    the pointer-only references, and exits 0 iff every listed script is present with its
    hash. A character the console cannot encode is printed as ``?`` rather than stopping
    the report.

    Record ids, ``spec_id`` and every verbatim recorded ``code_ref`` are written ONLY in the
    machine section (the F3 gate confirms each recorded ``code_ref`` appears there and
    compares its ``SCRIPTS`` with the record; a re-render reads ``SCRIPTS`` to learn which
    ``paper/code/`` files it owns). PURE + deterministic.
    """
    items = list(listings or [])
    scripts = bundle_scripts(items)

    doc = ["reproduce.py -- the generating code shipped with this paper, and a check of it.",
           "", _DOC_RUNS_NOTHING, ""]
    if scripts:
        doc += [_DOC_WHAT_IT_DOES, ""]
        if any(not s.hash_recorded for s in scripts):
            doc += [_DOC_UNRECORDED_HASH, ""]
    else:
        doc += [_DOC_NO_SCRIPT, ""]
    if any(item.data_files for item in items):
        doc += [_DOC_DATA_FILES, ""]
    doc += ["Usage: python reproduce.py"]

    lines: List[str] = ['"""', *doc, '"""', "from __future__ import annotations", "",
                        "import hashlib", "import sys", "from pathlib import Path", "", ""]
    lines.append(MACHINE_SECTION_MARKER)
    lines.append("# The identifiers below link each entry to the run's evidence log; the")
    lines.append("# report printed by main() does not show them.")
    lines.append(f"BUNDLE_FORMAT = {BUNDLE_FORMAT}")
    lines.append(f"RUN = {_py_str(spec_id)}")
    lines.append("")
    lines.append("# (file under code/, SHA-256, True if the record holds this hash / False if")
    lines.append("#  it was computed when this bundle was rendered)")
    lines.append("SCRIPTS = [")
    for script in scripts:
        lines.append(
            f"    ({_py_str(script.filename)}, {_py_str(script.sha256)}, "
            f"{script.hash_recorded!r}),"
        )
    lines.append("]")
    lines.append("")
    lines.append("# One entry per recorded result that names generating code: (record id,")
    lines.append("#  code reference as recorded, files under code/ it names, summary, output")
    lines.append("#  as recorded, data as recorded, hashed source paths it names that are not")
    lines.append("#  shipped, (data file, SHA-256) pairs it names -- listed, never shipped)")
    lines.append("RESULTS = [")
    for item in items:
        files = tuple(s.filename for s in item.all_scripts) if item.is_script else ()
        lines.append("    (")
        for value in (
            _py_str(item.evidence_id),
            _py_str(item.code_ref),
            _py_tuple(files),
            _py_str(item.summary),
            _py_str(item.output_ref or ""),
            _py_str(item.data_ref or ""),
            _py_tuple(item.unshipped),
            repr(tuple(tuple(pair) for pair in item.data_files)),
        ):
            lines.append(f"        {value},")
        lines.append("    ),")
    lines.append("]")
    lines.append("# ---- End of machine section. ----")
    return "\n".join(lines) + "\n" + _DRIVER_MAIN


def written_by_sci_adk(driver_text: str) -> bool:
    """Whether a ``paper/reproduce.py`` was written by a sci-adk render (this format's
    machine-section marker, or the original driver's "Auto-emitted by sci-adk" line), so a
    re-render may replace or remove it. PURE."""
    return MACHINE_SECTION_MARKER in driver_text or "Auto-emitted by sci-adk" in driver_text


def listed_code_files(driver_text: str) -> Optional[List[str]]:
    """The ``paper/code/`` file names a previously rendered ``reproduce.py`` lists. PURE.

    Reads (never executes) its top-level ``SCRIPTS`` literal: in this format
    (``BUNDLE_FORMAT = 2``) each entry starts with the file name; the original driver listed
    ``(evidence_id, code_ref, filename)``. Text that does not parse, or has no ``SCRIPTS``
    list literal -> ``None`` (the caller then removes nothing). Names are returned as
    written; the caller decides which are plain file names it may touch.
    """
    values = _driver_literals(driver_text)
    listed = None if values is None else values.get("SCRIPTS")
    if not isinstance(listed, (list, tuple)):
        return None
    index = 0 if values.get("BUNDLE_FORMAT") == BUNDLE_FORMAT else 2
    return [
        entry[index]
        for entry in listed
        if isinstance(entry, (list, tuple))
        and len(entry) > index
        and isinstance(entry[index], str)
    ]


def listed_scripts(driver_text: str) -> Optional[List[Tuple[str, str, bool]]]:
    """The script list of a ``reproduce.py`` in this format: ``(file under code/, sha256,
    hash recorded?)`` per entry. PURE.

    Read (never executed) from the top-level ``BUNDLE_FORMAT`` and ``SCRIPTS`` literals.
    ``None`` when the text does not parse, is not this format, or its ``SCRIPTS`` is not a
    list literal of such entries -- the F3 gate then reports that ``reproduce.py`` has no
    script list it can check.
    """
    values = _driver_literals(driver_text)
    if values is None or values.get("BUNDLE_FORMAT") != BUNDLE_FORMAT:
        return None
    listed = values.get("SCRIPTS")
    if not isinstance(listed, (list, tuple)):
        return None
    entries: List[Tuple[str, str, bool]] = []
    for entry in listed:
        if not (
            isinstance(entry, (list, tuple))
            and len(entry) == 3
            and isinstance(entry[0], str)
            and isinstance(entry[1], str)
            and isinstance(entry[2], bool)
        ):
            return None
        entries.append((entry[0], entry[1], entry[2]))
    return entries


def _driver_literals(driver_text: str) -> Optional[Dict[str, object]]:
    """The literal values of a driver's top-level ``SCRIPTS`` and ``BUNDLE_FORMAT``
    assignments (read with ``ast.literal_eval``; nothing is executed). A name assigned
    something that is not a literal is left out; text that does not parse -> ``None``."""
    try:
        tree = ast.parse(driver_text)
    except (SyntaxError, ValueError):
        return None
    values: Dict[str, object] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in ("SCRIPTS", "BUNDLE_FORMAT")
        ):
            try:
                values[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                values.pop(node.targets[0].id, None)
    return values


def _py_str(s: str) -> str:
    """A safe Python string literal for the generated driver (deterministic)."""
    return repr(s)


def _py_tuple(values: Sequence[str]) -> str:
    return repr(tuple(values))


__all__ = [
    "BUNDLE_FORMAT",
    "MACHINE_SECTION_MARKER",
    "ReproListing",
    "ReproScript",
    "bundle_file_names",
    "bundle_scripts",
    "listed_code_files",
    "listed_scripts",
    "listing_inlinable",
    "reader_summary",
    "reader_text",
    "reproduction_uses_listings",
    "render_reproduction_section",
    "render_reproduce_driver",
    "written_by_sci_adk",
]
