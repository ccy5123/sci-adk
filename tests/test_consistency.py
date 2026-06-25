"""
paper-figures Phase 3 (RED-first): a GENERAL LaTeX ``\\ref``<->``\\label`` consistency
checker (design/paper-figures-and-si.md D4) -- the pure kernel behind the verify-style
hard gate.

Unlike the Phase-1 ``check_figure_consistency`` (figure-only: ``\\ref{fig:...}`` vs a
known figure-id set), this checker is GENERAL: it parses every ``\\label{X}`` and every
``\\ref{X}`` / ``\\eqref{X}`` / ``\\autoref{X}`` in a single document (any prefix --
fig:/tab:/sec:/eq:/...) and reports WITHIN-document integrity:

  - ``unresolved_refs``: a ``\\ref{X}`` with NO matching ``\\label{X}`` (a broken
    reference -- shows "??" in the compiled PDF). A GATE failure.
  - ``duplicate_labels``: a label defined more than once (a LaTeX "multiply defined"
    error). A GATE failure.
  - ``ok``: True iff BOTH gate-lists are empty. An UNused label (never referenced) is
    benign in a draft and does NOT make ``ok`` False.

PURE (string in, report out; no fs/LLM/network), deterministic (sorted lists).

These pin the behavior before any implementation exists.
"""

from __future__ import annotations

from sci_adk.render.consistency import (
    CrossDocRefReport,
    LatexRefReport,
    check_cross_doc_s_refs,
    check_latex_ref_consistency,
)


# A small SI fixture: two captioned figures (-> Figure S1, S2) and one table (-> Table S1).
_SI_TWO_FIG_ONE_TAB = "\n".join([
    r"\begin{table}[htbp]\caption{nums}\label{tab:s1}\end{table}",
    r"\begin{figure}[htbp]\caption{a}\label{fig:a}\end{figure}",
    r"\begin{figure}[htbp]\caption{b}\label{fig:b}\end{figure}",
])


# -- a consistent document is ok ---------------------------------------------

def test_label_and_ref_resolve_is_ok():
    tex = r"""
\section{Intro}\label{sec:intro}
As shown in Figure~\ref{fig:a}, the result holds (see Section~\ref{sec:intro}).
\begin{figure}\caption{c}\label{fig:a}\end{figure}
"""
    report = check_latex_ref_consistency(tex)
    assert isinstance(report, LatexRefReport)
    assert report.unresolved_refs == []
    assert report.duplicate_labels == []
    assert report.ok is True


# -- a dangling \ref (no matching \label) is unresolved -> NOT ok ------------

def test_ref_without_label_is_unresolved():
    tex = r"See Figure~\ref{fig:missing}. \label{fig:other}"
    report = check_latex_ref_consistency(tex)
    assert report.unresolved_refs == ["fig:missing"]
    assert report.duplicate_labels == []
    assert report.ok is False


# -- a label defined twice is a duplicate -> NOT ok --------------------------

def test_label_defined_twice_is_duplicate():
    tex = r"\label{x}\ref{x} ... \label{x}"
    report = check_latex_ref_consistency(tex)
    assert report.duplicate_labels == ["x"]
    assert report.unresolved_refs == []
    assert report.ok is False


# -- an unused label (defined, never referenced) is benign -> still ok -------

def test_unused_label_does_not_fail_the_gate():
    # A label defined but never \ref'd is common and harmless in a draft. It MUST NOT
    # gate (this is the explicit Phase-3 decision: unused != broken).
    tex = r"\label{fig:never-cited}\section{s}"
    report = check_latex_ref_consistency(tex)
    assert report.unresolved_refs == []
    assert report.duplicate_labels == []
    assert report.ok is True


# -- \eqref and \autoref count as references too -----------------------------

def test_eqref_and_autoref_are_references():
    # \eqref / \autoref are reference forms; a dangling one is just as broken as \ref.
    tex = r"\eqref{eq:ghost} and \autoref{tab:ghost}; \label{eq:real}\eqref{eq:real}"
    report = check_latex_ref_consistency(tex)
    assert report.unresolved_refs == ["eq:ghost", "tab:ghost"]
    assert report.ok is False


# -- a \ref inside a commented-out line is ignored ---------------------------

def test_ref_in_comment_is_ignored():
    # A line whose first non-space char is % is a LaTeX comment: a \ref there never
    # compiles, so it must not count as a real reference (no false unresolved).
    tex = "\n".join([
        r"\label{fig:a}",
        r"  % \ref{fig:ghost} -- this is commented out, must be ignored",
        r"\ref{fig:a}",
    ])
    report = check_latex_ref_consistency(tex)
    assert report.unresolved_refs == []
    assert report.ok is True


def test_label_inside_comment_is_ignored():
    # A \label on a fully-commented line is also inert: it must not register as a
    # definition (so a real \ref to it stays unresolved, and it cannot duplicate).
    tex = "\n".join([
        r"% \label{x}",
        r"\ref{x}",
    ])
    report = check_latex_ref_consistency(tex)
    assert report.unresolved_refs == ["x"]
    assert report.ok is False


# -- determinism: sorted, de-duplicated output -------------------------------

def test_unresolved_refs_are_sorted_and_deduped():
    tex = r"\ref{z}\ref{a}\ref{a}\ref{m}"
    report = check_latex_ref_consistency(tex)
    assert report.unresolved_refs == ["a", "m", "z"]


def test_empty_document_is_ok():
    report = check_latex_ref_consistency("")
    assert report.unresolved_refs == []
    assert report.duplicate_labels == []
    assert report.ok is True


# -- the report is frozen ----------------------------------------------------

def test_report_is_frozen():
    report = check_latex_ref_consistency(r"\label{a}")
    import pytest

    with pytest.raises(Exception):
        report.ok = False  # frozen pydantic -> mutation refused


# == cross-document "Figure/Table S<n>" gate (main paper -> SI) ===============

def test_cross_doc_all_s_refs_resolve_is_ok():
    # SI has 2 figures + 1 table; the main paper cites only floats that exist -> clean.
    draft = r"As shown in Figure S1 and Figure S2, and the data in Table S1, ..."
    report = check_cross_doc_s_refs(draft, _SI_TWO_FIG_ONE_TAB)
    assert isinstance(report, CrossDocRefReport)
    assert report.unresolved_refs == []
    assert report.ok is True


def test_cross_doc_dangling_figure_is_unresolved():
    # The SI has 2 figures; "Figure S3" points past them -> a silent dangling cross-ref.
    draft = r"See Figure S3 for the extended sweep."
    report = check_cross_doc_s_refs(draft, _SI_TWO_FIG_ONE_TAB)
    assert report.unresolved_refs == ["Figure S3"]
    assert report.ok is False


def test_cross_doc_dangling_table_is_unresolved():
    # The SI has exactly 1 table; "Table S2" does not exist.
    draft = r"The full numbers are in Table S2."
    report = check_cross_doc_s_refs(draft, _SI_TWO_FIG_ONE_TAB)
    assert report.unresolved_refs == ["Table S2"]
    assert report.ok is False


def test_cross_doc_no_s_refs_is_ok():
    # A main paper that cites no SI float cannot dangle.
    report = check_cross_doc_s_refs(r"A paper body with Figure 1 and Table 1 only.",
                                    _SI_TWO_FIG_ONE_TAB)
    assert report.unresolved_refs == []
    assert report.ok is True


def test_cross_doc_abbreviations_and_tilde_are_recognized():
    # "Fig.~S1" and "Tab. S1" are the same cross-reference forms; both resolve here.
    draft = r"see Fig.~S1 and Tab. S1"
    assert check_cross_doc_s_refs(draft, _SI_TWO_FIG_ONE_TAB).ok is True
    # ... but "Fig. S5" past the 2 SI figures dangles.
    assert check_cross_doc_s_refs(r"see Fig.~S5", _SI_TWO_FIG_ONE_TAB).unresolved_refs == [
        "Figure S5"
    ]


def test_cross_doc_citation_in_comment_is_ignored():
    # A "Figure S9" on a fully-commented line never compiles -> must not gate.
    draft = "\n".join([
        r"% Figure S9 -- a note to self, commented out",
        r"Figure S1 is the headline.",
    ])
    report = check_cross_doc_s_refs(draft, _SI_TWO_FIG_ONE_TAB)
    assert report.unresolved_refs == []
    assert report.ok is True


def test_cross_doc_empty_si_dangles_every_s_ref():
    # No SI floats at all: any "Figure S1" the paper cites is dangling.
    report = check_cross_doc_s_refs(r"Figure S1 and Table S1.", "")
    assert report.unresolved_refs == ["Figure S1", "Table S1"]
    assert report.ok is False


def test_cross_doc_unresolved_sorted_by_kind_then_number_and_deduped():
    # Determinism: ("Figure", n) before ("Table", n); numeric (not lexical) order; deduped.
    draft = r"Figure S10, Figure S2, Table S3, Figure S2 again, Table S3 again."
    report = check_cross_doc_s_refs(draft, "")  # empty SI -> all dangle
    assert report.unresolved_refs == ["Figure S2", "Figure S10", "Table S3"]


def test_cross_doc_report_is_frozen():
    import pytest

    report = check_cross_doc_s_refs(r"Figure S1", "")
    with pytest.raises(Exception):
        report.ok = True  # frozen pydantic -> mutation refused
