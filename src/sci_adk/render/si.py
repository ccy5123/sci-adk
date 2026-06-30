"""
Supporting Information renderer: the RECORD dumped as a standalone ``si.tex``
(design/paper-figures-and-si.md, Phase 2 / D3).

record / belief <-> SI / paper. sci-adk's deepest split maps onto paper structure:
the main paper (``draft.tex``, ``render/paper.py``) is the BELIEF narrative -- the
Claims plus the key figures carrying the headline. The Supporting Information is the
RECORD -- the complete append-only Evidence, the numeric data tables, ALL figures, the
verdicts plus the frozen decision rules, and a record-integrity line. A rigorous SI
*is* "the complete record behind the belief", and sci-adk already stores exactly that,
so the SI is the most natural DETERMINISTIC render of what sci-adk holds -- no authoring
judgment, no LLM at render time. Only the main paper needs prose.

This module is PURE: it imports ``sci_adk.core`` + the sibling render helpers ONLY (the
F4 kernel seam -- no adapter, no loop, no LLM, no fs/network). ``render_si_latex`` takes
the record (Spec + Claims + Evidence, plus optional figures + a record digest) and
returns a STANDALONE LaTeX document string (``\\documentclass{article}`` ...
``\\end{document}``) so ``si.tex`` compiles on its own as a folder-upload sibling of
``draft.tex`` -- with NO ``\\input`` (native figures are inline text; image figures
reference the same co-located ``figures/<id><ext>`` the compiler lands next to it).
Deterministic: same inputs -> byte-identical string.

Reuse: every interpolated string is routed through :func:`paper._latex_sanitize` (the
same escaper + unicode safety net the main paper uses), and figures through
:func:`figures.render_figure` -- so the SI is sanitized and plotted identically to the
paper (native pgfplots or an image ``\\includegraphics``, routed by figure kind).

Reference: design/paper-figures-and-si.md (D3, Phase 2), design/abstractions.md,
design/directory-structure.md (render/), design/rigor-shell-architecture.md (F4 seam).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

from sci_adk.core.claim import Claim
from sci_adk.core.evidence import EvidenceItem, EvidenceKind
from sci_adk.core.spec import Spec
from sci_adk.render.factref import substitute_factrefs
from sci_adk.render.figures import (
    AnyFigure,
    order_figures_by_reference,
    render_figure,
)
from sci_adk.render.novelty import NOVELTY_NEWCOMMAND, has_novelty_markup
from sci_adk.render.paper import (
    _confidence_display,
    _latex_evidence_validity_label,
    _latex_sanitize,
    _novelty_prose,
    _result_summary,
    _status_str,
)
from sci_adk.render.prose import SIProse
from sci_adk.render.reproduction import (
    ReproListing,
    render_reproduction_section,
    reproduction_uses_listings,
)

# The numeric Result scalar fields, in a fixed order, for the quantitative data table.
# A column is emitted ONLY when at least one item carries a value for it (empty columns
# are skipped deterministically). Kept in sync with the numeric fields of
# ``sci_adk.core.evidence.Result``.
_NUMERIC_FIELDS: tuple[str, ...] = (
    "point",
    "effect_size",
    "ci",
    "p_value",
    "posterior",
    "residual",
    "predictive_error",
)


def _fmt_cell(value: object) -> str:
    """Deterministic, LaTeX-safe rendering of one numeric Result value for a table cell.

    A ``ci`` is a 2-list ``[lo, hi]`` -> ``[lo, hi]`` text; a float -> ``%g`` (drops
    trailing zeros, byte-stable); ``None`` -> an empty cell. The result is sanitized so
    any stray character cannot break compilation.

    Deliberate asymmetry vs ``render_native_figure``: a NaN/inf Result value renders here
    as the literal compile-safe text ``nan``/``inf`` (the value IS in the record, and a
    ``tabular`` cell is plain text), whereas the figure renderer REJECTS NaN/inf because
    pgfplots coordinates cannot be non-finite.
    """
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        inner = ", ".join(f"{float(v):g}" for v in value)
        return _latex_sanitize(f"[{inner}]")
    if isinstance(value, bool):
        # A bool is not a numeric measurement; render its text, sanitized.
        return _latex_sanitize(str(value))
    if isinstance(value, (int, float)):
        return _latex_sanitize(f"{float(value):g}")
    return _latex_sanitize(str(value))


def _provenance_str(ev: EvidenceItem) -> str:
    """A short, honest provenance/capability line for one Evidence item.

    Surfaces the recorded ``data_source`` (the evidence-validity capability marker) and
    ``code_ref`` when present, so the SI record shows where each item came from. Returns
    ``"(none)"`` when nothing is recorded (honest about unmarked provenance).
    """
    prov = ev.provenance
    parts: List[str] = []
    if prov.data_source:
        parts.append(f"data_source={prov.data_source}")
    if prov.code_ref:
        parts.append(f"code_ref={prov.code_ref}")
    if prov.data_ref:
        parts.append(f"data_ref={prov.data_ref}")
    return "; ".join(parts) if parts else "(none)"


def _kind_str(ev: EvidenceItem) -> str:
    return ev.kind.value if hasattr(ev.kind, "value") else str(ev.kind)


def _dedupe_evidence_for_render(
    evidence: Sequence[EvidenceItem],
) -> List[tuple[EvidenceItem, int]]:
    """Collapse repeated Evidence items into ``(item, count)`` for the SI render (3.3).

    A repeated acquisition (e.g. the SAME DOI literature item recorded six times, or a
    re-run novelty decision) clutters the record dump with byte-identical entries. This
    is a RENDER-TIME view only -- it never touches the stored append-only log (E1); it
    just shows one entry with a ``(recorded Nx)`` count instead of N identical lines.

    Two items collapse iff they share ``(kind, finding, point)`` -- the record content a
    reader sees. Distinct experiment runs (different findings) never collapse; the 6
    identical literature items do. First-seen order is preserved (deterministic).
    """
    out: List[tuple[EvidenceItem, int]] = []
    index: dict[tuple[str, str, object], int] = {}
    for ev in evidence:
        key = (_kind_str(ev), ev.result.finding or "", ev.result.point)
        if key in index:
            item, count = out[index[key]]
            out[index[key]] = (item, count + 1)
        else:
            index[key] = len(out)
            out.append((ev, 1))
    return out


def render_si_latex(
    spec: Spec,
    claims: Sequence[Claim],
    evidence: Sequence[EvidenceItem],
    *,
    figures: Optional[Sequence[AnyFigure]] = None,
    digest: Optional[str] = None,
    prose: Optional[SIProse] = None,
    paper_body: Optional[str] = None,
    bib_path: Optional[str] = None,
    repro_listings: Optional[Sequence[ReproListing]] = None,
) -> str:
    """Render the full record as a STANDALONE Supporting Information ``si.tex``.

    A deterministic, no-authoring dump of everything sci-adk stores -- the RECORD behind
    the main paper's belief narrative. PURE (data in, string out): no LLM, no network, no
    filesystem. Same inputs -> byte-identical output.

    An OPTIONAL :class:`~sci_adk.render.prose.SIProse` may wrap the spine with narrative
    (design/paper-figures-and-si.md D3, Phase 4): ``overview`` near the top (after the
    italic record-note, before the Evidence record) and ``notes`` at the bottom (after
    Record integrity, before ``\\end{document}``). It is INPUT, never sci-adk-generated;
    the strict no-authoring record dump remains the spine and is never replaced. With
    ``prose=None`` (or both slots ``None``) the output is BYTE-IDENTICAL to the no-prose
    dump (a regression invariant, like the ``figures``/``digest`` defaults).

    Sections (a faithful record dump; every interpolated string sanitized):
      1. Title -- ``Supporting Information: <spec goal>``.
      2. Evidence record -- every ``EvidenceItem`` (stable order = as given): id, kind, a
         result summary (point or finding), and its provenance/capability. The complete
         append-only record.
      3. Quantitative data -- a ``tabular`` of the numeric ``Result`` fields for each item
         that has them; all-empty columns are skipped deterministically.
      4. Claims and verdicts -- per Claim: the hypothesis it answers, statement, status,
         the confidence (type + value/level + the load-bearing **basis**, always present,
         C3), its supporting/refuting evidence links, and the hypothesis's frozen
         ``decision_rule`` (what it was judged against).
      5. Figures -- ALL ``figures`` via :func:`render_figure` (the SI shows every figure,
         native or image), in the SAME global body-reference order + the SAME ``fig<N>``
         identity as the main paper (so ``si.tex`` references the same
         ``paper/figures/fig<N>`` files the compiler co-locates -- one shared file set for
         both documents); ``pgfplots`` is added to the preamble when a NATIVE figure is
         present and ``graphicx`` when an IMAGE figure is present.
      5b. Reproduction code (F3, OPTIONAL) -- when ``repro_listings`` is supplied: each
         resolvable co-located script inlined as an ``lstlisting`` + each bare commit/ref
         as a POINTER line. Emitted after Figures, before Record integrity; adds a guarded
         ``\\usepackage{listings}`` when a script is present. Absent/empty -> no section
         (byte-identical to today).
      6. Record integrity -- ``digest`` embedded as ``Record digest (sha256): <digest>``
         when provided; ELSE a note that the record is independently auditable via
         ``sci-adk verify <run>`` (which computes the digest over the persisted run).

    Args:
        spec: the compiled Spec (the frozen hypotheses + their decision rules).
        claims: the Claims (belief states) whose verdicts the SI records.
        evidence: the append-only Evidence record (rendered in the given order).
        figures: optional agent-authored figure list (native or image) -- the SI renders
            ALL of them, in the SAME global ``fig<N>`` body-reference order as the main
            paper (see ``paper_body``) so an image figure references the SAME
            ``figures/fig<N><ext>`` file the compiler co-located (one shared file set for
            ``draft.tex`` + ``si.tex``). ``pgfplots`` + ``\\pgfplotsset{compat=1.18}`` are
            added when a native figure is present, ``graphicx`` when an image figure is
            present. ``None``/empty -> no figures, no figure packages.
        digest: optional record digest (hex sha256). When provided it is embedded in the
            integrity section; ``None`` (Phase 2 default) emits the ``sci-adk verify``
            note instead -- NEVER a fabricated digest.

            Phase 2 wiring note (compiler): at compile time the evidence is NOT yet
            persisted to disk (the loop persists AFTER compile), so computing
            ``record_digest(run_dir)`` then would digest an INCOMPLETE run dir. So the
            compiler passes ``digest=None`` and the SI's integrity section points to
            ``sci-adk verify`` (which computes the digest over the persisted run).
            Embedding the real digest at render time is a later refinement.
        prose: optional agent-authored narrative wrapping the record dump -- a present
            ``overview`` becomes an ``\\section{Overview}`` before the Evidence record and
            a present ``notes`` becomes an ``\\section{Notes}`` after Record integrity,
            each sanitized exactly like the paper's prose slots. ``None`` (or a ``None``
            slot) -> nothing emitted: the output stays byte-identical to the no-prose
            record dump (a regression invariant). NEVER LLM-generated -- input, the same
            spirit as ``PaperProse``.
        paper_body: optional MAIN-PAPER body text used ONLY to compute the global
            body-reference figure numbering (:func:`order_figures_by_reference`), so the
            SI's figures share the SAME ``fig<N>`` numbers + filenames as ``draft.tex``
            (the compiler passes the rendered main draft here). ``None`` -> the figures
            are numbered in supply order (no body to reference against), which is correct
            for a standalone SI render with no companion paper. Affects ONLY figure
            numbering (the ``\\label{fig:<id>}`` anchors are unchanged), so a figure-less
            SI is byte-identical regardless of ``paper_body``.
        repro_listings: optional reproduction-code entries (F3,
            design/paper-publishing-requirements.md §3) -- one per Evidence item carrying
            a ``provenance.code_ref``, ALREADY RESOLVED by the compiler (this renderer
            stays PURE -- it reads no files). A resolvable co-located script becomes an
            inlined ``lstlisting`` in a new "Reproduction code" section (after Figures,
            before Record integrity) and adds a GUARDED ``\\usepackage{listings}`` to the
            preamble; a bare commit/ref becomes an honest POINTER line. ``None``/empty ->
            no section, no ``listings`` package: byte-identical to today (the F3
            regression invariant, exactly like the ``figures``/``prose``/``digest``
            defaults). The code listing lives in the SI (the exempt record dump), NEVER
            in the tool-agnostic main paper.

    Returns:
        A STANDALONE LaTeX document string.
    """
    claims = list(claims)
    evidence = list(evidence)
    figures = list(figures or [])
    # Novelty decisions (bears_on=[]) back the \novelty{} markup re-derivation (N2 gate).
    # The SI prose also gets the gate -- no gap where an author sneaks \novelty into the SI.
    novelty_decisions = [
        ev for ev in evidence if ev.kind == EvidenceKind.NOVELTY_DECISION
    ]

    def _si_slot(text: str) -> str:
        # SI prose -> substitute record-fidelity facts (\evval/\status, fail-loud), THEN
        # render \novelty{} markup (scope baked / HARD fail) + the prose sanitizer
        # (\ref/\cite preserved). Same contract as the paper's prose.
        return _novelty_prose(
            substitute_factrefs(text.strip(), evidence, claims),
            spec,
            novelty_decisions,
        )

    # The Spec's frozen hypotheses, keyed by id, so each Claim's verdict can show the
    # decision rule it was judged against.
    hyp_by_id = {h.id: h for h in spec.hypotheses}

    lines: List[str] = []
    # The record title is the spec id, not the goal/hypothesis wall (the same short title
    # the paper falls back to; the agent's narrative title lives in the main paper). The
    # identity wording reads as the RECORD (SPEC-SI-AUTHORING-001 REQ-SA-203), not an SI.
    title = spec.id

    # -- Preamble (standalone document; same inputenc/hyperref/url as the paper, so
    #    si.tex compiles on its own). Figure packages are added PER KIND (mirrors the
    #    paper): pgfplots ONLY when a native figure is present, graphicx ONLY when an
    #    image figure is present -- a figure-less SI stays minimal.
    has_native = any(f.kind == "native" for f in figures)
    has_image = any(f.kind == "image" for f in figures)
    lines.append(r"\documentclass{article}")
    lines.append(r"\usepackage[utf8]{inputenc}")
    lines.append(r"\usepackage{hyperref}")
    lines.append(r"\usepackage{url}")
    lines.append(r"\usepackage{natbib}")
    # Figure font policy (design/paper-publishing-requirements.md F2), mirroring the paper:
    # newtxmath (Times-compatible MATH only, body text unchanged) + helvet (Arial-compatible
    # sans for figure text). Only for a figure-bearing SI -- a figure-less SI is unchanged.
    if has_native or has_image:
        lines.append(r"\usepackage{amsmath}")
        lines.append(r"\usepackage{newtxmath}")
        lines.append(r"\usepackage[scaled]{helvet}")
    if has_native:
        lines.append(r"\usepackage{pgfplots}")
        lines.append(r"\pgfplotsset{compat=1.18}")
    if has_image:
        lines.append(r"\usepackage{graphicx}")
    # F3 reproduction code (design/paper-publishing-requirements.md §3): the listings
    # package is added ONLY when a resolvable script will be inlined as an lstlisting --
    # a code-less (or pointer-only) SI carries NO listings package, so its preamble stays
    # byte-identical to today (the same per-kind guarding as pgfplots/graphicx above).
    has_repro_listing = reproduction_uses_listings(repro_listings)
    if has_repro_listing:
        lines.append(r"\usepackage{listings}")
    # \novelty{kind}{hyp}{text} survives into si.tex; this \newcommand makes LaTeX render
    # only the text. Emitted ONLY when SI prose carries novelty markup, so a no-novelty SI
    # is byte-identical to the no-prose dump (regression invariant).
    has_nov = prose is not None and any(
        has_novelty_markup(s) for s in (prose.overview, prose.notes) if s
    )
    if has_nov:
        lines.append(NOVELTY_NEWCOMMAND)
    # SI numbering convention: tables/figures are S-prefixed (Table S1, Figure S1, ...),
    # so a main-paper cross-reference written as the plain text "Table S1" / "Figure S1"
    # matches this document's printed numbers (cross-document \ref is deferred -- the xr
    # package + compile-order dependency; design/paper-figures-and-si.md).
    lines.append(r"\renewcommand{\thetable}{S\arabic{table}}")
    lines.append(r"\renewcommand{\thefigure}{S\arabic{figure}}")
    # SPEC-SI-AUTHORING-001 REQ-SA-203: the identity wording reads as the RECORD (the
    # deposit's retained deterministic record), NOT as a "Supporting Information" sibling
    # of the paper. Presentation-only -- the record-dump LOGIC below is unchanged.
    lines.append(
        f"\\title{{Record: {_latex_sanitize(title)}}}"
    )
    lines.append(r"\author{sci-adk (deterministic record)}")
    lines.append(r"\date{\today}")
    lines.append("")
    lines.append(r"\begin{document}")
    lines.append(r"\maketitle")
    lines.append("")
    lines.append(
        f"\\noindent\\textit{{The complete append-only RECORD behind Spec "
        f"\\texttt{{{_latex_sanitize(spec.id)}}} (v{spec.version}). This is the "
        f"deterministic dump of every Evidence item, the data tables, all figures, and "
        f"the verdicts; the main paper is the belief narrative.}}"
    )
    lines.append("")

    # Agent-authored overview (before the record dump), when supplied. Sanitized
    # exactly like the paper's prose slots; absent -> nothing, preserving the
    # byte-identical no-prose dump.
    if prose is not None and prose.overview:
        lines.append(r"\section{Overview}")
        # Prose slot: \evval/\status substituted, then sanitized (\ref/\cite preserved);
        # the record dump below stays fully escaped (no factref, no passthrough).
        lines.append(_si_slot(prose.overview))
        lines.append("")

    # -- Section: Evidence record (the append-only record, de-duplicated for render) --
    # A repeated acquisition (the same DOI six times) collapses to one entry with a
    # (recorded Nx) count -- a render-time VIEW only; the stored log is untouched (E1).
    deduped = _dedupe_evidence_for_render(evidence)
    lines.append(r"\section{Evidence record}")
    if not evidence:
        lines.append(r"\emph{No evidence recorded.}")
    else:
        lines.append(r"\begin{description}")
        for ev, count in deduped:
            summary = _result_summary(ev)
            times = f" (recorded {count}x)" if count > 1 else ""
            lines.append(
                f"  \\item[\\texttt{{{_latex_sanitize(ev.id)}}} "
                f"({_latex_sanitize(_kind_str(ev))})] "
                f"{_latex_sanitize(summary)}{times}"
            )
            lines.append(
                f"    \\\\ \\textit{{provenance:}} "
                f"{_latex_sanitize(_provenance_str(ev))}"
            )
        lines.append(r"\end{description}")
    lines.append("")

    # -- Section: Quantitative data (a captioned, labelled TABLE of numeric Result
    #    fields) -- the de-duplicated items, so a repeated item is not double-listed. A
    #    column is emitted ONLY when at least one item carries a value for it (empty
    #    columns skipped deterministically). The table is wrapped in a ``table`` float
    #    with ``\caption`` + ``\label{tab:s1}`` and referenced within the SI (Table~\ref),
    #    so the "Table S1" a main-paper author cites resolves to a real, S-numbered table.
    quant_items = [
        ev for ev, _count in deduped
        if any(getattr(ev.result, f, None) is not None for f in _NUMERIC_FIELDS)
    ]
    active_fields = [
        f for f in _NUMERIC_FIELDS
        if any(getattr(ev.result, f, None) is not None for ev in quant_items)
    ]
    lines.append(r"\section{Quantitative data}")
    if not quant_items or not active_fields:
        lines.append(r"\emph{No quantitative results recorded.}")
    else:
        lines.append(
            r"The recorded numeric results are listed in Table~\ref{tab:s1}."
        )
        lines.append(r"\begin{table}[htbp]")
        lines.append(r"\centering")
        lines.append(
            r"\caption{Recorded numeric results, one row per Evidence item (the "
            r"append-only quantitative record).}"
        )
        lines.append(r"\label{tab:s1}")
        # Column spec: one for the id + one per active numeric field.
        col_spec = "l" + "r" * len(active_fields)
        lines.append(f"\\begin{{tabular}}{{{col_spec}}}")
        lines.append(r"\hline")
        header = " & ".join(
            ["evidence"] + [_latex_sanitize(f) for f in active_fields]
        )
        lines.append(f"{header} \\\\")
        lines.append(r"\hline")
        for ev in quant_items:
            cells = [f"\\texttt{{{_latex_sanitize(ev.id)}}}"]
            for f in active_fields:
                cells.append(_fmt_cell(getattr(ev.result, f, None)))
            lines.append(" & ".join(cells) + r" \\")
        lines.append(r"\hline")
        lines.append(r"\end{tabular}")
        lines.append(r"\end{table}")
    lines.append("")

    # -- Section: Claims and verdicts ---------------------------------------------
    lines.append(r"\section{Claims and verdicts}")
    if not claims:
        lines.append(r"\emph{No claims recorded.}")
    for claim in claims:
        lines.append(
            f"\\subsection{{{_latex_sanitize(claim.statement)}}}"
        )
        lines.append(r"\begin{itemize}")
        lines.append(
            f"  \\item Answers hypothesis: "
            f"\\texttt{{{_latex_sanitize(str(claim.answers))}}}"
        )
        # Status + confidence. The uninformative credence/posterior=0 default a
        # deterministic threshold produces is SUPPRESSED (it would read as "confidence 0"
        # next to SUPPORTED); the basis below carries the real judgment (C3).
        confidence = _confidence_display(claim)
        status_line = (
            f"  \\item \\textbf{{Status: {_latex_sanitize(_status_str(claim))}}}"
        )
        if confidence is not None:
            status_line += f" --- confidence {_latex_sanitize(confidence)}"
        lines.append(status_line)
        # C3: the basis is always present and load-bearing.
        lines.append(f"  \\item Basis: {_latex_sanitize(claim.confidence.basis)}")

        supporting = [link.evidence_id for link in claim.get_supporting_evidence()]
        refuting = [link.evidence_id for link in claim.get_refuting_evidence()]
        sup_str = ", ".join(_latex_sanitize(s) for s in supporting) or "(none)"
        ref_str = ", ".join(_latex_sanitize(s) for s in refuting) or "(none)"
        lines.append(f"  \\item Supporting evidence: {sup_str}")
        lines.append(f"  \\item Refuting evidence: {ref_str}")

        # The frozen decision rule this hypothesis was judged against (the spine of
        # anti-HARKing) + the honest evidence-validity label (referent + data_source(s),
        # moved here from the paper -- the structured honesty now lives in the record).
        # Absent only if the claim answers an unknown hypothesis.
        hyp = hyp_by_id.get(claim.answers)
        if hyp is not None:
            rule = hyp.decision_rule
            rule_kind = (
                rule.kind.value if hasattr(rule.kind, "value") else str(rule.kind)
            )
            lines.append(
                f"  \\item Decision rule ({_latex_sanitize(rule_kind)}): "
                f"{_latex_sanitize(rule.expression)}"
            )
            lines.append(
                f"  \\item {_latex_evidence_validity_label(hyp, claim, evidence)}"
            )
        lines.append(r"\end{itemize}")
        lines.append("")

    # -- Section: Figures (ALL of them; the SI shows every figure) -----------------
    # render_figure routes by kind (native pgfplots from the record / image include),
    # emitted in the SAME global body-reference order + the SAME fig<N> numbering as the
    # main paper: order_figures_by_reference against `paper_body` (the rendered main
    # draft) -> Figure N here == Figure N there, and an image figure references the SAME
    # figures/fig<N><ext> file the compiler co-located (one shared file set for both
    # docs). paper_body=None -> supply order (a standalone SI with no companion paper).
    if figures:
        ordered = order_figures_by_reference(figures, paper_body or "")
        lines.append(r"\section{Figures}")
        lines.append("")
        for number, fig in ordered:
            lines.append(render_figure(fig, evidence, number))
            lines.append("")

    # -- Section: Reproduction code (F3; OPTIONAL) --------------------------------
    # design/paper-publishing-requirements.md §3: the generating code retained with the
    # paper -- resolvable co-located scripts inlined as lstlistings, bare commit/refs as
    # honest POINTER lines. The compiler resolves code_ref -> (script | pointer) and
    # co-locates paper/code/ + writes paper/reproduce.py; this renderer only lists. After
    # Figures, before Record integrity. Empty/None -> "" (no section): byte-identical to
    # today, the F3 regression invariant. The code listing lives in the SI (the exempt
    # record dump), NEVER in the tool-agnostic main paper.
    repro_section = render_reproduction_section(repro_listings)
    if repro_section:
        lines.append(repro_section)
        lines.append("")

    # -- Section: Record integrity ------------------------------------------------
    lines.append(r"\section{Record integrity}")
    if digest is not None:
        lines.append(
            f"Record digest (sha256): \\texttt{{{_latex_sanitize(digest)}}}"
        )
    else:
        # Phase 2: at compile time the evidence is NOT yet persisted, so a real digest
        # would be computed over an incomplete run dir. Instead point to the
        # third-party headless re-check, which computes the digest over the persisted
        # run. (Embedding the real digest at render time is a later refinement.)
        lines.append(
            "This record is independently auditable: run "
            "\\texttt{sci-adk verify <run>} to recompute the record digest (sha256) "
            "over the persisted run and re-check the verdict trail."
        )
    lines.append("")

    # Agent-authored closing notes (after Record integrity), when supplied. Sanitized
    # exactly like the paper's prose slots; absent -> nothing, preserving the
    # byte-identical no-prose dump.
    if prose is not None and prose.notes:
        lines.append(r"\section{Notes}")
        # Prose slot: \evval/\status substituted, then sanitized (\ref/\cite preserved).
        lines.append(_si_slot(prose.notes))
        lines.append("")

    # Bibliography -- the SI cites the SAME references.bib as the paper, so its \citep in
    # the prose resolves (and the references print) instead of showing [?]. natbib is in
    # the preamble; an existing .bib is wired with plainnat + \bibliography (the compiler
    # passes the co-located path; the renderer does no fs access). None -> no bibliography.
    if bib_path is not None:
        stem = Path(bib_path).stem
        lines.append(r"\bibliographystyle{plainnat}")
        lines.append(f"\\bibliography{{{stem}}}")
        lines.append("")

    lines.append(r"\end{document}")
    return "\n".join(lines)


__all__ = ["render_si_latex"]
