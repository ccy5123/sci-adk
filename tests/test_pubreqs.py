"""
F1 publishing-requirements: the ``PubReqs`` frozen contract, its digest, the pure checkers,
and the ``pubreqs freeze`` CLI verb (design/paper-publishing-requirements.md §1 / §2).

These cover the engineering surface of F1-core that does NOT require a verify run (that lives
in test_verify.py): the model's freeze discipline (a gate-bearing field is immutable, mirror
Spec S1), the tamper-evidence digest (deterministic, changes on a gate field, ignores the
freeze timestamp), the pure font/DPI/section/reference/word-count checkers, and the
``pubreqs freeze`` verb writing ``runs/<id>/pubreqs.json`` at the RUN ROOT with the digest.
"""

from __future__ import annotations

import json
import struct
import zlib
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from sci_adk.core.pubreqs import (
    DEFAULT_IMAGE_MIN_DPI,
    DEFAULT_REQUIRED_SECTIONS,
    PubReqs,
)
from sci_adk.core.spec import (
    DecisionRule,
    DecisionRuleKind,
    Hypothesis,
    HypothesisMode,
    MethodPlan,
    RawProposal,
    Spec,
    TargetClaim,
)
from sci_adk.provenance import pubreqs_digest
from sci_adk.render.pubreqs_checks import (
    NOMINAL_TEXTWIDTH_IN,
    display_width_inches,
    figure_font_policy_problems,
    image_dpi_problems,
    is_figure_bearing,
    max_words_problems,
    raster_pixel_width,
    reference_style_problems,
    required_sections_problems,
    word_count,
)


# -- PNG fixture helper (stdlib only -- NO Pillow) ---------------------------

def _make_png(width: int, height: int = 10) -> bytes:
    """A minimal valid PNG with a chosen IHDR width (truecolor, no pixel data needed).

    The DPI checker reads only the IHDR width from the header, so a header-only PNG (signature
    + IHDR + IEND) is enough -- no pixel decode happens.
    """
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def _chunk(typ: bytes, data: bytes) -> bytes:
        body = typ + data
        crc = zlib.crc32(body) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + body + struct.pack(">I", crc)

    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IEND", b"")


def _make_jpeg(width: int, height: int = 10) -> bytes:
    """A minimal JPEG header carrying a SOF0 with a chosen width (header-only).

    SOI + a baseline SOF0 segment whose width field is read by the checker. No scan data is
    needed -- the checker reads only the frame header.
    """
    soi = b"\xff\xd8"
    # SOF0: marker FFC0, length(8) precision(1=8) height(2) width(2) comps(1=1) + comp spec(3)
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 8 + 3, 8, height, width, 1) + b"\x01\x11\x00"
    eoi = b"\xff\xd9"
    return soi + sof + eoi


# -- PubReqs model ------------------------------------------------------------

def test_pubreqs_defaults_match_design():
    pr = PubReqs(spec_id="s1")
    assert pr.figure_font_policy is True
    assert pr.image_min_dpi == DEFAULT_IMAGE_MIN_DPI == 300
    assert pr.reproduction_bundle is True
    assert pr.required_sections == []          # the model default is empty (CLI seeds IMRaD)
    assert pr.max_pages is None and pr.max_words is None
    assert DEFAULT_REQUIRED_SECTIONS[0] == "Abstract"


def test_pubreqs_is_frozen():
    # A gate-bearing field is immutable after construction (mirror Spec S1, anti-moving-goalposts).
    pr = PubReqs(spec_id="s1", image_min_dpi=300)
    with pytest.raises(ValidationError):
        pr.image_min_dpi = 100          # cannot relax after a figure fails
    with pytest.raises(ValidationError):
        pr.figure_font_policy = False
    with pytest.raises(ValidationError):
        pr.required_sections = ["X"]


def test_pubreqs_digest_is_deterministic():
    pr = PubReqs(spec_id="s1", required_sections=list(DEFAULT_REQUIRED_SECTIONS))
    assert pubreqs_digest(pr) == pubreqs_digest(pr)
    assert len(pubreqs_digest(pr)) == 64


def test_pubreqs_digest_changes_on_a_gate_field():
    base = PubReqs(spec_id="s1", image_min_dpi=300)
    relaxed = PubReqs(spec_id="s1", image_min_dpi=100)
    assert pubreqs_digest(base) != pubreqs_digest(relaxed)

    sections_a = PubReqs(spec_id="s1", required_sections=["Abstract", "Methods"])
    sections_b = PubReqs(spec_id="s1", required_sections=["Abstract"])
    assert pubreqs_digest(sections_a) != pubreqs_digest(sections_b)

    font_on = PubReqs(spec_id="s1", figure_font_policy=True)
    font_off = PubReqs(spec_id="s1", figure_font_policy=False)
    assert pubreqs_digest(font_on) != pubreqs_digest(font_off)


def test_pubreqs_digest_ignores_timestamp_and_digest_field():
    # The digest covers only the GATE-BEARING contract: two freezes of identical requirements
    # at different times share a digest, and the stored `digest` slot does not feed itself.
    a = PubReqs(spec_id="s1", frozen_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    b = PubReqs(spec_id="s1", frozen_at=datetime(2026, 6, 25, tzinfo=timezone.utc))
    assert pubreqs_digest(a) == pubreqs_digest(b)
    # Storing the digest back in does not change the digest (not circular).
    d = pubreqs_digest(a)
    stamped = a.model_copy(update={"digest": d})
    assert pubreqs_digest(stamped) == d


# -- required_sections checker -----------------------------------------------

def test_required_sections_present_is_clean():
    tex = (
        r"\begin{abstract}x\end{abstract}"
        r"\section{Introduction}a\section{Methods}b"
        r"\section{Results}c\section{Discussion}d\section{Conclusion}e"
    )
    assert required_sections_problems(tex, list(DEFAULT_REQUIRED_SECTIONS)) == []


def test_required_sections_missing_one_fails():
    tex = (
        r"\begin{abstract}x\end{abstract}"
        r"\section{Introduction}a\section{Results}c\section{Discussion}d"
        r"\section{Conclusion}e"
    )  # no Methods
    missing = required_sections_problems(tex, list(DEFAULT_REQUIRED_SECTIONS))
    assert missing == ["Methods"]


def test_required_sections_abstract_accepts_environment_or_section():
    assert required_sections_problems(r"\begin{abstract}x\end{abstract}", ["Abstract"]) == []
    assert required_sections_problems(r"\section{Abstract}x", ["Abstract"]) == []
    assert required_sections_problems(r"no abstract here", ["Abstract"]) == ["Abstract"]


# -- F2 figure font policy checker -------------------------------------------

_FONT_PREAMBLE = (
    r"\usepackage{amsmath}" "\n" r"\usepackage{newtxmath}" "\n"
    r"\usepackage[scaled]{helvet}"
)


def test_font_policy_figure_bearing_with_preamble_is_clean():
    tex = (
        _FONT_PREAMBLE + "\n"
        r"\begin{figure}\begin{tikzpicture}\begin{axis}[font=\sffamily]\end{axis}"
        r"\end{tikzpicture}\end{figure}"
    )
    assert is_figure_bearing(tex) is True
    assert figure_font_policy_problems(tex) == []


def test_font_policy_figure_bearing_stripped_preamble_fails():
    # A figure-bearing doc with the F2 packages removed (hand-edited) fails the gate.
    tex = r"\begin{figure}\begin{tikzpicture}\end{tikzpicture}\end{figure}"
    problems = figure_font_policy_problems(tex)
    assert len(problems) == 2  # missing both newtxmath and helvet
    assert any("newtxmath" in p for p in problems)
    assert any("helvet" in p for p in problems)


def test_font_policy_figureless_doc_is_clean():
    # No figure -> the policy is N/A -> vacuously clean (the F2 regression invariant).
    tex = r"\section{Introduction}prose only, no figures."
    assert is_figure_bearing(tex) is False
    assert figure_font_policy_problems(tex) == []


def test_font_policy_image_figure_needs_preamble():
    tex = r"\includegraphics[width=\linewidth]{figures/fig1.png}"
    assert is_figure_bearing(tex) is True
    assert len(figure_font_policy_problems(tex)) == 2  # no font packages -> fail


# -- F2 raster DPI checker ----------------------------------------------------

def test_image_dpi_high_resolution_is_clean(tmp_path):
    figs = tmp_path / "figures"
    figs.mkdir()
    (figs / "fig1.png").write_bytes(_make_png(2000))  # 2000px / 6.5in ~= 307 DPI
    tex = r"\includegraphics{figures/fig1.png}"
    assert image_dpi_problems(tex, figs, 300) == []


def test_image_dpi_low_resolution_fails(tmp_path):
    figs = tmp_path / "figures"
    figs.mkdir()
    (figs / "fig1.png").write_bytes(_make_png(500))  # 500px / 6.5in ~= 77 DPI < 300
    tex = r"\includegraphics{figures/fig1.png}"
    problems = image_dpi_problems(tex, figs, 300)
    assert len(problems) == 1
    assert "fig1.png" in problems[0]


def test_image_dpi_jpeg_header_is_read(tmp_path):
    figs = tmp_path / "figures"
    figs.mkdir()
    (figs / "fig1.jpg").write_bytes(_make_jpeg(300))  # tiny width -> low DPI -> fail
    assert raster_pixel_width(figs / "fig1.jpg") == 300
    tex = r"\includegraphics{figures/fig1.jpg}"
    assert len(image_dpi_problems(tex, figs, 300)) == 1


def test_image_dpi_vector_is_skipped(tmp_path):
    figs = tmp_path / "figures"
    figs.mkdir()
    # A vector .pdf has no fixed DPI -> skipped (no file even needs to exist as a raster).
    tex = r"\includegraphics[width=\textwidth]{figures/fig1.pdf}"
    assert image_dpi_problems(tex, figs, 300) == []


def test_image_dpi_width_fraction_lowers_display_and_raises_dpi(tmp_path):
    figs = tmp_path / "figures"
    figs.mkdir()
    (figs / "fig1.png").write_bytes(_make_png(1000))
    # Full width: 1000 / 6.5 ~= 154 DPI < 300 -> fails.
    assert len(image_dpi_problems(r"\includegraphics{figures/fig1.png}", figs, 300)) == 1
    # Half width: 1000 / 3.25 ~= 308 DPI >= 300 -> clean (a smaller display raises DPI).
    half = r"\includegraphics[width=0.5\textwidth]{figures/fig1.png}"
    assert image_dpi_problems(half, figs, 300) == []


def test_image_dpi_missing_file_is_not_a_failure(tmp_path):
    figs = tmp_path / "figures"
    figs.mkdir()
    tex = r"\includegraphics{figures/absent.png}"  # no co-located file -> unmeasurable
    assert image_dpi_problems(tex, figs, 300) == []


def test_display_width_inches_forms():
    assert display_width_inches(r"0.8\textwidth") == pytest.approx(0.8 * NOMINAL_TEXTWIDTH_IN)
    assert display_width_inches(r"\linewidth") == pytest.approx(NOMINAL_TEXTWIDTH_IN)
    assert display_width_inches("5in") == pytest.approx(5.0)
    assert display_width_inches("") == pytest.approx(NOMINAL_TEXTWIDTH_IN)
    # Unparseable -> conservative full text width (largest display, lowest DPI).
    assert display_width_inches(r"\somemacro") == pytest.approx(NOMINAL_TEXTWIDTH_IN)


# -- reference style + word count --------------------------------------------

def test_reference_style_wired_is_clean():
    tex = r"\usepackage{natbib}\bibliographystyle{plainnat}\bibliography{refs}"
    assert reference_style_problems(tex, "plainnat") == []
    assert reference_style_problems(tex, "natbib") == []        # package name also matches
    assert reference_style_problems(tex, None) == []            # not declared -> skipped


def test_reference_style_unwired_fails():
    tex = r"\section{Introduction}no bibliography here"
    problems = reference_style_problems(tex, "plainnat")
    assert len(problems) == 1 and "plainnat" in problems[0]


def test_word_count_strips_control_words():
    # The tokeniser strips \commands (control words) but leaves brace-argument text -- a
    # conservative, deterministic count. \ref/\section/$...$ control words are removed; the
    # remaining word tokens are counted (the safe direction for a ceiling -- never inflated
    # by LaTeX macro names). A command-free body counts plainly.
    plain = "The quick brown fox jumps over the lazy dog"
    assert word_count(plain) == 9
    # The control word \section is stripped (does not add a word); its argument text remains.
    assert word_count(r"\section{Intro}" + plain) == 10   # 'Intro' + 9
    assert max_words_problems(plain, 100) == []
    over = max_words_problems(plain, 3)
    assert len(over) == 1 and "word count" in over[0]
    assert max_words_problems(plain, None) == []      # no limit -> skipped


# -- pubreqs freeze CLI verb -------------------------------------------------

def _seed_spec_run(tmp_path: Path, spec_id: str = "pr-run") -> Path:
    """Write a minimal runs/<id>/spec.json so `pubreqs freeze` can read the spec_id."""
    spec = Spec(
        id=spec_id,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id="h1", statement="s", mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= threshold => support",
                    params={"statistic": "point", "op": ">=", "value": 0.5},
                ),
                referent="formal",
                non_circularity="the verifier checks a property not baked into the generator",
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="h1")],
    )
    run_dir = tmp_path / "runs" / spec_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "spec.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    return run_dir


def test_pubreqs_freeze_writes_artifact_at_run_root_with_digest(tmp_path, capsys):
    from sci_adk.cli import main

    run_dir = _seed_spec_run(tmp_path)
    rc = main(["pubreqs", "freeze", str(run_dir), "--defaults"])
    assert rc == 0

    pubreqs_path = run_dir / "pubreqs.json"
    assert pubreqs_path.is_file()                          # at RUN ROOT, not inside paper/
    assert not (run_dir / "paper" / "pubreqs.json").exists()

    data = json.loads(pubreqs_path.read_text(encoding="utf-8"))
    pr = PubReqs.model_validate(data)
    assert pr.spec_id == "pr-run"
    assert pr.required_sections == DEFAULT_REQUIRED_SECTIONS  # --defaults seeded IMRaD
    assert pr.image_min_dpi == 300
    assert pr.figure_font_policy is True
    assert pr.reproduction_bundle is True
    # The digest is STORED in the artifact (design §1.1) and matches the recomputed value.
    assert pr.digest == pubreqs_digest(pr)
    assert len(pr.digest) == 64

    out = capsys.readouterr().out
    assert "digest (sha256):" in out


def test_pubreqs_freeze_explicit_options_override_defaults(tmp_path):
    from sci_adk.cli import main

    run_dir = _seed_spec_run(tmp_path, "pr-opts")
    rc = main([
        "pubreqs", "freeze", str(run_dir),
        "--no-font-policy", "--image-min-dpi", "600",
        "--reference-style", "natbib", "--max-words", "8000",
        "--required-section", "Conclusion", "--advisory", "double-blind",
        "--max-pages", "12",
    ])
    assert rc == 0
    pr = PubReqs.model_validate(
        json.loads((run_dir / "pubreqs.json").read_text(encoding="utf-8"))
    )
    assert pr.figure_font_policy is False
    assert pr.image_min_dpi == 600
    assert pr.reference_style == "natbib"
    assert pr.max_words == 8000
    assert pr.required_sections == ["Conclusion"]   # no --defaults -> replace, not append
    assert pr.advisory == ["double-blind"]
    assert pr.max_pages == 12


def test_pubreqs_freeze_no_spec_errors(tmp_path):
    from sci_adk.cli import main

    empty = tmp_path / "runs" / "empty"
    empty.mkdir(parents=True)
    rc = main(["pubreqs", "freeze", str(empty), "--defaults"])
    assert rc == 2     # no spec.json
