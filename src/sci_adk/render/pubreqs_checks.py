"""
PURE deterministic checkers for the F1 publishing-requirements gate (design §1.3 / §2).

These are the F2-deferred checker functions (design §6 build note: "the verify HARD gate
that CONSUMES those checkers is wired in F1") plus the small per-requirement helpers the
umbrella gate composes. Like ``render/consistency.py`` and ``render/reproduction.py`` this
module is PURE (data/paths in, verdict out): no LLM, no recompile, no network. The image-DPI
checker reads only raster file HEADERS (a few bytes via the stdlib ``struct`` module -- NO
Pillow, keeping the dependency surface minimal); it never decodes pixels.

It lives in ``render/`` (the kernel) and imports only stdlib + ``re`` -- nothing from
``adapter`` / ``loop`` (the F4 seam). ``loop/verify._check_paper_requirements`` orchestrates
these against the frozen ``pubreqs.json`` and reports the failures the contract declared.

The checkers (design §1.3 table):
  - :func:`required_sections_problems` -- each named section present as a ``\\section{...}``
    in draft.tex (Abstract also accepts ``\\begin{abstract}``);
  - :func:`figure_font_policy_problems` -- a figure-bearing document carries the F2 font
    preamble (the REAL tokens the F2 commit emits: ``newtxmath`` + ``[scaled]helvet``); a
    figure-LESS document is vacuously clean (the policy is N/A);
  - :func:`image_dpi_problems` -- every raster ``\\includegraphics`` is >= the threshold
    effective DPI; vector PDF/EPS are skipped (no fixed DPI);
  - :func:`reference_style_problems` -- the declared bib style is wired in draft.tex;
  - :func:`word_count` / the gate's max_words check -- a deterministic word count over the
    rendered prose.

The reproduction-bundle check lives in ``loop/verify`` (it needs the recorded Evidence's
``code_ref``s, a record read, not a pure-string op) -- but its OF-4 fail-open semantics are
documented there.

Honest limits (documented, mirroring consistency.py's comment rule):
  - the DPI display width is APPROXIMATE (it depends on the true ``\\textwidth``); the gate
    assumes the nominal article ``\\textwidth`` (~6.5in) and computes a CONSERVATIVE effective
    DPI -- when a width cannot be parsed it assumes the FULL text width (the largest display,
    hence the lowest DPI, hence the gate is least likely to false-PASS);
  - the font INSIDE a raster image cannot be checked deterministically (fonts baked into a
    bitmap are out of scope); the font rule is enforced for engine-rendered NATIVE figures.

Reference: design/paper-publishing-requirements.md §1.3 / §2.3, src/sci_adk/render/paper.py
(the F2 preamble tokens), src/sci_adk/render/consistency.py (the sibling pure checker).
"""

from __future__ import annotations

import re
import struct
from pathlib import Path
from typing import List, Optional

# -- required sections -------------------------------------------------------

# A \section{...} heading -- the argument up to the first closing brace. The renderer emits
# IMRaD bodies as \section{Introduction} / \section{Methods} / ... (paper.py); Abstract is
# the one IMRaD slot rendered as an ENVIRONMENT (\begin{abstract}), so it is matched both ways.
_SECTION_RE = re.compile(r"\\section\*?\{([^{}]+)\}")
_ABSTRACT_ENV_RE = re.compile(r"\\begin\{abstract\}")


def section_names(tex: str) -> List[str]:
    """The (stripped) ``\\section{...}`` heading names present in ``tex`` (lower-cased).

    PURE. Used to test required-section presence case-insensitively: the contract names
    "Introduction" and the renderer emits ``\\section{Introduction}``. Starred
    ``\\section*`` is tolerated.
    """
    return [m.strip().lower() for m in _SECTION_RE.findall(tex)]


def required_sections_problems(tex: str, required: List[str]) -> List[str]:
    """Every required section NOT present in ``tex`` (design §1.3 required_sections).

    PURE + deterministic. A section is present iff its name appears (case-insensitively) as a
    ``\\section{...}`` heading. "Abstract" is special-cased: the renderer emits the abstract
    as a ``\\begin{abstract}`` environment, not a ``\\section``, so an abstract environment
    OR a ``\\section{Abstract}`` satisfies it. Returns the missing names in the contract's
    order (empty = all present). An empty ``required`` list -> no problems.
    """
    have = set(section_names(tex))
    has_abstract_env = bool(_ABSTRACT_ENV_RE.search(tex))
    missing: List[str] = []
    for name in required:
        key = name.strip().lower()
        if not key:
            continue
        if key == "abstract" and (has_abstract_env or key in have):
            continue
        if key in have:
            continue
        missing.append(name)
    return missing


# -- F2 figure font policy ---------------------------------------------------

# A document is "figure-bearing" iff it carries a native pgfplots figure (the renderer emits
# \begin{tikzpicture} inside the figure env) OR an image figure (\includegraphics). Either
# triggers the F2 preamble (paper.py: `if has_native or has_image`). We detect the document's
# rendered tokens rather than re-deriving from the figure specs (verify is read-only over the
# .tex, exactly as the other paper gates are).
_TIKZ_RE = re.compile(r"\\begin\{tikzpicture\}")
_INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics")
# The REAL F2 font tokens (git show 3dcb1dc): the math serif (Times-compatible) and the
# scaled sans (Arial/Helvetica-compatible). A figure-bearing document missing EITHER fails
# the font policy. We match the package names tolerantly to brace/option whitespace.
_NEWTXMATH_RE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{newtxmath\}")
_HELVET_RE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{helvet\}")


def is_figure_bearing(tex: str) -> bool:
    """True iff ``tex`` renders at least one figure (a native pgfplots plot or an image).

    PURE. The F2 font preamble is emitted ONLY for a figure-bearing document, so this is the
    precondition the font-policy gate keys off: a figure-less paper is byte-identical to
    pre-F2 and the policy does not apply.
    """
    return bool(_TIKZ_RE.search(tex)) or bool(_INCLUDEGRAPHICS_RE.search(tex))


def figure_font_policy_problems(tex: str) -> List[str]:
    """Confirm the F2 font preamble is present for a figure-bearing document (design §2).

    PURE + deterministic. For a figure-bearing document the render-time policy emits the
    Times-compatible math serif (``newtxmath``) and the Arial-compatible sans
    (``[scaled]{helvet}``); a hand-edited ``.tex`` that strips either bypasses the policy and
    fails this gate (the render-time + verify-gate pairing the reframe uses). A figure-LESS
    document is vacuously clean -- the policy is N/A (no figures to set the font of). Returns
    the missing-package problem lines (empty = clean).

    The font INSIDE a raster image is out of scope (a baked-in bitmap font is not
    deterministically checkable) -- the policy covers the engine-rendered NATIVE figures'
    text; the preamble packages are the deterministic signal that policy is in force.
    """
    if not is_figure_bearing(tex):
        return []
    problems: List[str] = []
    if not _NEWTXMATH_RE.search(tex):
        problems.append(
            "figure font policy: a figure-bearing document is missing "
            r"\usepackage{newtxmath} (the Times-compatible math serif, F2)"
        )
    if not _HELVET_RE.search(tex):
        problems.append(
            "figure font policy: a figure-bearing document is missing "
            r"\usepackage[scaled]{helvet} (the Arial-compatible sans, F2)"
        )
    return problems


# -- F2 raster (image) DPI gate ----------------------------------------------

# The nominal text width of the article documentclass, in inches. The true \textwidth depends
# on margins/geometry; absent a compile we assume the article default (~6.5in) and compute a
# CONSERVATIVE effective DPI (design §2.3 honest limit). Vector figures have no fixed DPI.
NOMINAL_TEXTWIDTH_IN = 6.5

# Raster extensions the DPI gate inspects (it can read a pixel width from the header). Vector
# formats (.pdf/.eps/.ps/.svg) are resolution-independent -> SKIPPED (no DPI to fail).
_RASTER_EXTS = {".png", ".jpg", ".jpeg"}
_VECTOR_EXTS = {".pdf", ".eps", ".ps", ".svg"}

# \includegraphics[<opts>]{<path>} -- capture the optional bracket block (carrying width=...)
# and the path. The renderer emits \includegraphics[width=...]{figures/fig<N><ext>}.
_INCLUDEGRAPHICS_FULL_RE = re.compile(
    r"\\includegraphics(?:\[([^\]]*)\])?\{([^{}]+)\}"
)
# A width=<spec> option inside the bracket block. The <spec> is captured up to the next comma
# or the end of the block.
_WIDTH_OPT_RE = re.compile(r"width\s*=\s*([^,\]]+)")
# A LaTeX length expressed as a fraction of a relative unit: "0.8\textwidth", "\linewidth",
# "0.5 \columnwidth". The leading number is optional (a bare \linewidth -> factor 1.0).
_REL_WIDTH_RE = re.compile(
    r"^\s*([0-9]*\.?[0-9]+)?\s*\\(?:textwidth|linewidth|columnwidth|hsize)\s*$"
)
# An absolute LaTeX length: "5in", "100pt", "3.2cm", "40mm". Converted to inches.
_ABS_WIDTH_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(in|pt|cm|mm|bp|px)\s*$")
_ABS_UNIT_TO_IN = {
    "in": 1.0,
    "pt": 1.0 / 72.27,   # TeX point
    "bp": 1.0 / 72.0,    # big point (PostScript)
    "px": 1.0 / 72.0,    # treat a pixel as a big point (best-effort)
    "cm": 1.0 / 2.54,
    "mm": 1.0 / 25.4,
}


def display_width_inches(
    width_spec: str, textwidth_in: float = NOMINAL_TEXTWIDTH_IN
) -> float:
    """Resolve a LaTeX ``\\includegraphics`` width spec to a display width in INCHES.

    PURE + deterministic + CONSERVATIVE (design §2.3): the effective DPI is
    ``pixel_width / display_width_in``, so a LARGER display width yields a LOWER DPI (the gate
    is least likely to false-PASS). Therefore an UNPARSEABLE width is treated as the FULL
    nominal text width -- the most generous display, the most conservative DPI.

    Resolved forms:
      - a relative unit ("0.8\\textwidth", bare "\\linewidth") -> factor * ``textwidth_in``
        (a missing factor is 1.0);
      - an absolute length ("5in", "100pt", "3cm") -> converted to inches;
      - empty / unparseable -> ``textwidth_in`` (conservative full width).
    """
    spec = (width_spec or "").strip()
    if not spec:
        return textwidth_in
    rel = _REL_WIDTH_RE.match(spec)
    if rel:
        factor = float(rel.group(1)) if rel.group(1) else 1.0
        return factor * textwidth_in
    absm = _ABS_WIDTH_RE.match(spec)
    if absm:
        return float(absm.group(1)) * _ABS_UNIT_TO_IN[absm.group(2)]
    # Unparseable (e.g. a macro we do not model): conservative full text width.
    return textwidth_in


def _png_pixel_width(data: bytes) -> Optional[int]:
    """The pixel width from a PNG header (the IHDR width), or None if not a PNG.

    The PNG signature is 8 bytes; the IHDR chunk's data starts at offset 16 and its first
    4 bytes are the big-endian width. Pure stdlib (``struct``) -- NO Pillow.
    """
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if data[12:16] != b"IHDR":
        return None
    return struct.unpack(">I", data[16:20])[0]


def _jpeg_pixel_width(data: bytes) -> Optional[int]:
    """The pixel width from a JPEG's first SOF marker, or None if not parseable.

    Walks the JPEG marker segments from the SOI (``\\xff\\xd8``) to the first Start-Of-Frame
    (SOF0..SOF15, excluding the non-frame markers), reading the 16-bit big-endian width.
    Pure stdlib (``struct``) -- NO Pillow; reads only the segment headers, never pixel data.
    """
    if len(data) < 4 or data[0:2] != b"\xff\xd8":
        return None
    i = 2
    n = len(data)
    while i + 1 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        # Skip any fill bytes (a run of 0xFF).
        marker = data[i + 1]
        i += 2
        # Standalone markers (no length): RSTn, SOI, EOI, TEM.
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            continue
        if i + 1 >= n:
            return None
        seg_len = struct.unpack(">H", data[i:i + 2])[0]
        # SOF markers carry the frame dimensions. Exclude DHT(C4)/DAC(CC)/SOS(DA) which share
        # the 0xC* range but are not frame headers.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            # segment: [len:2][precision:1][height:2][width:2]...
            if i + 7 > n:
                return None
            return struct.unpack(">H", data[i + 5:i + 7])[0]
        i += seg_len
    return None


def raster_pixel_width(path: Path) -> Optional[int]:
    """The pixel width of a PNG/JPEG raster from its HEADER (stdlib), or None.

    PURE-ish (reads a small header prefix of the file -- the only filesystem touch, like the
    other verify file reads). Returns None for a non-raster / unreadable / unrecognised file
    (the caller treats None as "cannot measure" -> skipped, not a failure). Reads at most the
    first 64 KiB (enough for any SOF marker) -- never decodes pixels, never needs Pillow.
    """
    try:
        with path.open("rb") as fh:
            data = fh.read(65536)
    except OSError:
        return None
    return _png_pixel_width(data) or _jpeg_pixel_width(data)


def image_dpi_problems(
    tex: str,
    figures_dir: Path,
    min_dpi: int,
    textwidth_in: float = NOMINAL_TEXTWIDTH_IN,
) -> List[str]:
    """Every raster ``\\includegraphics`` whose effective DPI is below ``min_dpi`` (design §2.3).

    PURE-ish + deterministic + CONSERVATIVE. For each ``\\includegraphics[...]{path}`` in
    ``tex``:
      - a VECTOR include (.pdf/.eps/.ps/.svg) is SKIPPED -- vector is resolution-independent,
        so there is no DPI to fail (documented honest limit);
      - a RASTER include (.png/.jpg/.jpeg) is measured: read its pixel width from the
        co-located ``figures_dir/<basename>`` header, resolve the display width from the
        figure's ``width`` option against the nominal text width, and compute
        ``effective_dpi = pixel_width / display_width_in``. Fail (a problem line) iff
        ``effective_dpi < min_dpi``;
      - an include whose co-located file is MISSING / UNMEASURABLE is skipped (None pixel
        width) -- the gate measures what it can read, and a missing figure file is the
        consistency/compile concern, not the DPI gate's (it does not fabricate a failure).

    The path in the ``.tex`` is the rendered ``figures/fig<N><ext>``; the co-located raster is
    at ``figures_dir/fig<N><ext>`` (the compiler's ``_colocate_figures``). Returns the
    below-threshold problem lines (empty = clean / no raster figures / DPI gate off upstream).
    """
    problems: List[str] = []
    for match in _INCLUDEGRAPHICS_FULL_RE.finditer(tex):
        opts = match.group(1) or ""
        path_in_tex = match.group(2).strip()
        ext = Path(path_in_tex).suffix.lower()
        if ext in _VECTOR_EXTS:
            continue  # vector: no fixed DPI (skipped, documented)
        if ext not in _RASTER_EXTS:
            continue  # unknown/none: nothing to measure
        raster = figures_dir / Path(path_in_tex).name
        pixel_width = raster_pixel_width(raster)
        if pixel_width is None or pixel_width <= 0:
            continue  # unmeasurable: not a DPI failure (a missing file is another gate)
        width_match = _WIDTH_OPT_RE.search(opts)
        width_spec = width_match.group(1) if width_match else ""
        display_in = display_width_inches(width_spec, textwidth_in)
        if display_in <= 0:
            continue
        effective_dpi = pixel_width / display_in
        if effective_dpi < min_dpi:
            problems.append(
                f"image DPI: {Path(path_in_tex).name} is ~{effective_dpi:.0f} DPI "
                f"(< {min_dpi}): {pixel_width}px over ~{display_in:.2f}in display "
                "(conservative: nominal textwidth, full width if unparseable)"
            )
    return problems


# -- reference style ---------------------------------------------------------

_BIBSTYLE_RE = re.compile(r"\\bibliographystyle\{([^{}]+)\}")


def reference_style_problems(tex: str, reference_style: Optional[str]) -> List[str]:
    """Confirm the declared bib style is wired in ``tex`` (design §1.3 reference_style).

    PURE + deterministic. The contract may declare a style by its LaTeX
    ``\\bibliographystyle`` value (e.g. "plainnat") OR by the bib package family it implies
    ("natbib" -> the renderer wires ``\\bibliographystyle{plainnat}`` with the ``natbib``
    package). To stay tolerant of either spelling, the gate passes iff a ``\\bibliographystyle``
    is present AND the declared token appears anywhere in the document (the explicit style
    name, or the package name the author named) -- both are deterministic textual signals
    that the declared referencing is in force. A ``None`` style skips the check.

    Returns a single problem line when the style is declared but unwired (empty = clean / no
    style declared).
    """
    if not reference_style or not reference_style.strip():
        return []
    token = reference_style.strip().lower()
    styles = [s.strip().lower() for s in _BIBSTYLE_RE.findall(tex)]
    body_lower = tex.lower()
    # Pass when a \bibliographystyle is wired AND the declared token is present somewhere
    # (as the style value or the package name the author declared).
    if styles and (token in styles or token in body_lower):
        return []
    return [
        f"reference style: declared style '{reference_style}' is not wired in draft.tex "
        r"(expected a \bibliographystyle naming it, or the package present)"
    ]


# -- word count --------------------------------------------------------------

# Strip LaTeX commands (\foo and \foo[..]{..}), braces, math delimiters, and comment lines so
# the count approximates the PROSE the reader sees. This is a CONSERVATIVE, deterministic
# tokeniser (not a TeX engine): it under-counts markup-heavy text rather than inflating.
_COMMENT_LINE_RE = re.compile(r"(?m)^\s*%.*$")
_INLINE_COMMENT_RE = re.compile(r"(?<!\\)%.*")
_COMMAND_RE = re.compile(r"\\[A-Za-z@]+\*?")
_BRACE_RE = re.compile(r"[{}]")
_MATH_RE = re.compile(r"\$+")
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*")


def word_count(tex: str) -> int:
    """A deterministic, conservative word count over a LaTeX document's PROSE (design §1.3).

    PURE. Drops comment lines + inline comments, strips ``\\commands`` (and their bracket /
    brace arguments' delimiters), braces, and ``$`` math delimiters, then counts word tokens.
    It is a TOKENISER, not a TeX renderer -- it under-counts markup (a stripped ``\\section``
    name still leaves its text, a ``\\ref{x}`` leaves nothing), which is the safe direction
    for a ceiling gate (it will not falsely exceed a limit by counting LaTeX control words).
    """
    text = _COMMENT_LINE_RE.sub("", tex)
    text = _INLINE_COMMENT_RE.sub("", text)
    text = _COMMAND_RE.sub(" ", text)
    text = _MATH_RE.sub(" ", text)
    text = _BRACE_RE.sub(" ", text)
    return len(_WORD_RE.findall(text))


def max_words_problems(tex: str, max_words: Optional[int]) -> List[str]:
    """A single problem line iff the prose word count exceeds ``max_words`` (design §1.3).

    PURE + deterministic. ``None`` skips the check. Returns ``[]`` when within the limit.
    """
    if max_words is None:
        return []
    count = word_count(tex)
    if count <= max_words:
        return []
    return [f"word count: draft.tex has {count} words (> limit {max_words})"]


__all__ = [
    "NOMINAL_TEXTWIDTH_IN",
    "section_names",
    "required_sections_problems",
    "is_figure_bearing",
    "figure_font_policy_problems",
    "display_width_inches",
    "raster_pixel_width",
    "image_dpi_problems",
    "reference_style_problems",
    "word_count",
    "max_words_problems",
]
