"""
Workspace package-requirements: the ``PackageReqs`` frozen contract, its digest, the pure
package checkers, and the ``pkgreqs freeze`` CLI verb (design/near-submission-package.md §2).

These cover the engineering surface of the package layer that does NOT require an assembled
package (that lives in test_package_gate.py / test_package_smoke.py): the model's freeze
discipline (a gate-bearing field is immutable, mirror PubReqs/Spec), the tamper-evidence digest
(deterministic, changes on a gate field, ignores the freeze timestamp + digest slot), the pure
layout/cite/abstract/figure/readme checkers, and the ``pkgreqs freeze`` verb writing
``<ws>/pkgreqs.json`` at the WORKSPACE ROOT with the digest.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from sci_adk.core.pkgreqs import (
    ALL_RUNS,
    DEFAULT_IMAGE_MIN_DPI,
    DEFAULT_REQUIRED_SECTIONS,
    PackageReqs,
)
from sci_adk.provenance import pkgreqs_digest
from sci_adk.render.pkgreqs_checks import (
    PACKAGE_FOLDERS,
    abstract_max_words_problems,
    abstract_word_count,
    bib_keys,
    cite_resolution_problems,
    cited_keys,
    figure_presence_problems,
    layout_problems,
    readme_submission_readiness_problems,
)


# -- PackageReqs model -------------------------------------------------------

def test_pkgreqs_defaults_match_design():
    pr = PackageReqs()
    assert pr.venue is None
    assert pr.required_sections == []          # the model default is empty (CLI seeds IMRaD)
    assert pr.figure_font_policy is True       # F2 font policy on by default (mirrors PubReqs)
    assert pr.image_min_dpi == DEFAULT_IMAGE_MIN_DPI == 300
    assert pr.reference_style is None
    assert pr.abstract_max_words is None
    assert pr.body_word_range is None
    assert pr.runs == ALL_RUNS == "all"        # synthesize ALL runs by default
    assert pr.advisory == []
    assert DEFAULT_REQUIRED_SECTIONS[0] == "Abstract"
    assert "Conclusion" in DEFAULT_REQUIRED_SECTIONS   # REQ-PG-105: IMRaD incl Conclusion


def test_pkgreqs_is_frozen():
    # A gate-bearing field is immutable after construction (mirror PubReqs/Spec S1).
    pr = PackageReqs(abstract_max_words=300, required_sections=["Abstract"])
    with pytest.raises(ValidationError):
        pr.abstract_max_words = 250            # cannot relax after the abstract fails
    with pytest.raises(ValidationError):
        pr.required_sections = ["X"]
    with pytest.raises(ValidationError):
        pr.reference_style = "natbib"
    with pytest.raises(ValidationError):
        pr.figure_font_policy = False          # cannot relax the font policy after a failure
    with pytest.raises(ValidationError):
        pr.image_min_dpi = 72                  # cannot relax the DPI floor after a failure


def test_pkgreqs_runs_accepts_all_or_explicit_list():
    assert PackageReqs().runs == "all"
    assert PackageReqs(runs=["r1", "r2"]).runs == ["r1", "r2"]


def test_pkgreqs_digest_is_deterministic_and_64_hex():
    pr = PackageReqs(required_sections=list(DEFAULT_REQUIRED_SECTIONS), abstract_max_words=300)
    assert pkgreqs_digest(pr) == pkgreqs_digest(pr)
    assert len(pkgreqs_digest(pr)) == 64


def test_pkgreqs_digest_changes_on_a_gate_field():
    base = PackageReqs(abstract_max_words=300)
    relaxed = PackageReqs(abstract_max_words=250)
    assert pkgreqs_digest(base) != pkgreqs_digest(relaxed)

    sections_a = PackageReqs(required_sections=["Abstract", "Methods"])
    sections_b = PackageReqs(required_sections=["Abstract"])
    assert pkgreqs_digest(sections_a) != pkgreqs_digest(sections_b)

    runs_all = PackageReqs(runs="all")
    runs_one = PackageReqs(runs=["r1"])
    assert pkgreqs_digest(runs_all) != pkgreqs_digest(runs_one)


def test_pkgreqs_digest_ignores_timestamp_and_digest_field():
    # The digest covers only the GATE-BEARING contract: two freezes of identical requirements
    # at different times share a digest, and the stored `digest` slot does not feed itself.
    a = PackageReqs(abstract_max_words=300, frozen_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    b = PackageReqs(abstract_max_words=300, frozen_at=datetime(2026, 6, 25, tzinfo=timezone.utc))
    assert pkgreqs_digest(a) == pkgreqs_digest(b)
    d = pkgreqs_digest(a)
    stamped = a.model_copy(update={"digest": d})
    assert pkgreqs_digest(stamped) == d


# -- layout checker ----------------------------------------------------------

def _make_package(tmp_path: Path, *, folders=PACKAGE_FOLDERS, root_files=("MANIFEST.md", "README.md")) -> Path:
    pkg = tmp_path / "package"
    for folder in folders:
        (pkg / folder).mkdir(parents=True, exist_ok=True)
    for name in root_files:
        (pkg / name).write_text("x", encoding="utf-8")
    return pkg


def test_layout_present_is_clean(tmp_path):
    pkg = _make_package(tmp_path)
    assert layout_problems(pkg) == []


def test_layout_missing_folder_fails(tmp_path):
    pkg = _make_package(tmp_path, folders=[f for f in PACKAGE_FOLDERS if f != "02_data"])
    problems = layout_problems(pkg)
    assert any("02_data" in p for p in problems)


def test_layout_missing_root_file_fails(tmp_path):
    pkg = _make_package(tmp_path, root_files=("MANIFEST.md",))   # no README.md
    problems = layout_problems(pkg)
    assert any("README.md" in p for p in problems)


# -- citation resolution -----------------------------------------------------

def test_cited_and_bib_keys_parse():
    tex = r"prose \citep{a,b} more \citet{c} end \cite{a}"
    assert cited_keys(tex) == ["a", "b", "c"]
    bib = "@article{a, title={A}}\n@book{ b , title={B}}"
    assert bib_keys(bib) == ["a", "b"]


def test_cite_resolution_clean_when_all_resolve():
    tex = r"\citep{a,b}"
    bib = "@article{a,}\n@book{b,}"
    assert cite_resolution_problems(tex, bib) == []


def test_cite_resolution_flags_unresolved_key():
    tex = r"\citep{a,ghost}"
    bib = "@article{a,}"
    problems = cite_resolution_problems(tex, bib)
    assert len(problems) == 1 and "ghost" in problems[0]


def test_cite_resolution_uncited_bib_entry_is_benign():
    tex = r"\citep{a}"
    bib = "@article{a,}\n@book{unused,}"   # 'unused' never cited -> NOT a problem
    assert cite_resolution_problems(tex, bib) == []


# -- abstract word count -----------------------------------------------------

def test_abstract_word_count_over_an_environment():
    tex = r"\begin{abstract}one two three four five\end{abstract}\section{Intro}body"
    assert abstract_word_count(tex) == 5


def test_abstract_word_count_none_without_environment():
    assert abstract_word_count(r"\section{Intro}no abstract here") is None


def test_abstract_max_words_within_limit_is_clean():
    tex = r"\begin{abstract}one two three\end{abstract}"
    assert abstract_max_words_problems(tex, 10) == []
    assert abstract_max_words_problems(tex, None) == []      # no limit -> skipped


def test_abstract_max_words_over_limit_fails():
    tex = r"\begin{abstract}one two three four five\end{abstract}"
    problems = abstract_max_words_problems(tex, 3)
    assert len(problems) == 1 and "abstract word count" in problems[0]


def test_abstract_max_words_no_abstract_is_not_this_gates_failure():
    # A limit set but no abstract env -> NOT this gate's failure (required_sections enforces
    # the Abstract's presence); this gate measures an abstract that exists.
    assert abstract_max_words_problems(r"no abstract", 100) == []


# -- figure presence ---------------------------------------------------------

def test_figure_presence_clean_when_colocated(tmp_path):
    man = tmp_path / "01_manuscript"
    (man / "figures").mkdir(parents=True)
    (man / "figures" / "fig1.png").write_bytes(b"x")
    tex = r"\includegraphics[width=\linewidth]{figures/fig1.png}"
    assert figure_presence_problems(tex, man) == []


def test_figure_presence_flags_missing_file(tmp_path):
    man = tmp_path / "01_manuscript"
    man.mkdir(parents=True)
    tex = r"\includegraphics{figures/absent.png}"
    problems = figure_presence_problems(tex, man)
    assert len(problems) == 1 and "absent.png" in problems[0]


def test_figure_presence_resolves_extensionless_include(tmp_path):
    man = tmp_path / "01_manuscript"
    (man / "figures").mkdir(parents=True)
    (man / "figures" / "fig1.pdf").write_bytes(b"x")
    tex = r"\includegraphics{figures/fig1}"   # LaTeX picks the extension
    assert figure_presence_problems(tex, man) == []


# -- README submission-readiness ---------------------------------------------

def test_readme_submission_readiness_present_is_clean():
    readme = "# Pkg\n\n## Submission-readiness self-assessment\n\nGaps: ...\n"
    assert readme_submission_readiness_problems(readme) == []


def test_readme_submission_readiness_missing_fails():
    problems = readme_submission_readiness_problems("# Pkg\n\nno such section here\n")
    assert len(problems) == 1 and "submission-readiness" in problems[0].lower()


# -- pkgreqs freeze CLI verb -------------------------------------------------

def _seed_workspace(tmp_path: Path) -> Path:
    """A minimal workspace with a runs/ dir so `pkgreqs freeze` accepts it."""
    (tmp_path / "runs" / "r1").mkdir(parents=True)
    return tmp_path


def test_pkgreqs_freeze_writes_artifact_at_workspace_root_with_digest(tmp_path, capsys):
    from sci_adk.cli import main

    ws = _seed_workspace(tmp_path)
    rc = main(["pkgreqs", "freeze", str(ws), "--defaults", "--venue", "IEAM",
               "--abstract-max-words", "300"])
    assert rc == 0

    pkgreqs_path = ws / "pkgreqs.json"
    assert pkgreqs_path.is_file()                          # at WORKSPACE ROOT, not in package/
    assert not (ws / "package" / "pkgreqs.json").exists()

    pr = PackageReqs.model_validate(json.loads(pkgreqs_path.read_text(encoding="utf-8")))
    assert pr.venue == "IEAM"
    assert pr.required_sections == DEFAULT_REQUIRED_SECTIONS  # --defaults seeded IMRaD
    assert pr.abstract_max_words == 300
    assert pr.runs == "all"
    # The digest is STORED in the artifact (design §2) and matches the recomputed value.
    assert pr.digest == pkgreqs_digest(pr)
    assert len(pr.digest) == 64

    out = capsys.readouterr().out
    assert "digest (sha256):" in out


def test_pkgreqs_freeze_explicit_options_override_defaults(tmp_path):
    from sci_adk.cli import main

    ws = _seed_workspace(tmp_path)
    rc = main([
        "pkgreqs", "freeze", str(ws),
        "--required-section", "Conclusion", "--reference-style", "natbib",
        "--abstract-max-words", "250", "--body-word-min", "4000", "--body-word-max", "7000",
        "--run", "r1", "--run", "r2", "--advisory", "double-blind",
    ])
    assert rc == 0
    pr = PackageReqs.model_validate(
        json.loads((ws / "pkgreqs.json").read_text(encoding="utf-8"))
    )
    assert pr.required_sections == ["Conclusion"]    # no --defaults -> replace, not append
    assert pr.reference_style == "natbib"
    assert pr.abstract_max_words == 250
    assert pr.body_word_range == (4000, 7000)
    assert pr.runs == ["r1", "r2"]
    assert pr.advisory == ["double-blind"]
    # no DPI flags + no --defaults -> the DPI gate is OFF (mirrors pubreqs freeze)
    assert pr.image_min_dpi is None
    assert pr.figure_font_policy is True             # on by default


def test_pkgreqs_freeze_defaults_seed_font_and_dpi(tmp_path):
    """--defaults turns on the F2 font policy + a 300 DPI floor (mirrors pubreqs freeze)."""
    from sci_adk.cli import main

    ws = _seed_workspace(tmp_path)
    assert main(["pkgreqs", "freeze", str(ws), "--defaults"]) == 0
    pr = PackageReqs.model_validate(
        json.loads((ws / "pkgreqs.json").read_text(encoding="utf-8"))
    )
    assert pr.figure_font_policy is True
    assert pr.image_min_dpi == 300


def test_pkgreqs_freeze_font_and_dpi_flags_can_disable(tmp_path):
    """--no-font-policy turns it off; --no-image-dpi wins even under --defaults; --image-min-dpi sets it."""
    from sci_adk.cli import main

    ws = _seed_workspace(tmp_path)
    assert main([
        "pkgreqs", "freeze", str(ws), "--defaults", "--no-font-policy", "--no-image-dpi",
    ]) == 0
    pr = PackageReqs.model_validate(
        json.loads((ws / "pkgreqs.json").read_text(encoding="utf-8"))
    )
    assert pr.figure_font_policy is False
    assert pr.image_min_dpi is None                  # --no-image-dpi overrides the --defaults 300

    ws2 = _seed_workspace(tmp_path / "w2")
    assert main(["pkgreqs", "freeze", str(ws2), "--image-min-dpi", "600"]) == 0
    pr2 = PackageReqs.model_validate(
        json.loads((ws2 / "pkgreqs.json").read_text(encoding="utf-8"))
    )
    assert pr2.image_min_dpi == 600                  # explicit value wins without --defaults


def test_pkgreqs_freeze_body_word_range_requires_both_bounds(tmp_path):
    from sci_adk.cli import main

    ws = _seed_workspace(tmp_path)
    rc = main(["pkgreqs", "freeze", str(ws), "--body-word-min", "4000"])   # no --body-word-max
    assert rc == 2


def test_pkgreqs_freeze_no_runs_dir_errors(tmp_path):
    from sci_adk.cli import main

    rc = main(["pkgreqs", "freeze", str(tmp_path), "--defaults"])   # no runs/ under it
    assert rc == 2
