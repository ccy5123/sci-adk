"""A paper's PDF name and its references.bib key must agree.

Fixture ``tests/fixtures/lit_bcfkow/`` is trimmed REAL paperforge output (run
SPEC-BCFKOW-001 of ``~/research/lit-search-trial-2``): ``manifest.csv``, the
OpenAlex-derived ``pdfs/*.json`` sidecars and a ``references.bib`` whose entries
come from Crossref content negotiation -- one line per entry, except Bertelsen1998
whose title spans lines. In that run 3 of 6 PDFs were not bib keys:

  * DossouOlory2025.pdf  vs  @inbook{AVDossouOlory2025  (one-line entry never re-keyed)
  * Taherpour2012.pdf    vs  @inbook{Arman2012          (one-line + OpenAlex and Crossref
                                                         disagree on first author)
  * Mannhold2008.pdf     vs  @article{Mannhold2009      (OpenAlex year 2008, Crossref 2009)

Rule under test: a DOI keyed for the first time takes its ``<Surname><Year>`` base
from its OWN bib entry; the PDF, sidecar, manifest filename and bib key are then all
set to that one key. A key assigned before the call never changes.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from sci_adk.core.evidence import (
    Bearing,
    BearingDirection,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    Result,
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
from sci_adk.loop.checkpoint_loop import run_checkpoint_loop
from sci_adk.loop.literature_acquirer import LiteratureAcquirer
from sci_adk.loop.verify import _braces_balanced, verify_run
from sci_adk.search.citation_keys import (
    _rewrite_bib,
    assign_and_apply_citation_keys,
    bib_first_author_family,
)
from sci_adk.search.literature_merge import (
    bib_entry_base,
    key_and_merge,
    parse_bib_entries,
    snapshot_literature,
)
from sci_adk.search.manual_literature import find_recorded_key, normalize_doi
from sci_adk.search.paperforge_adapter import AcquisitionResult, PaperforgeAdapter

FIXTURE = Path(__file__).parent / "fixtures" / "lit_bcfkow"
PIN = "60fefedacb7349c755c29b2c2f26873464158c12"

DOSSOU = "10.5772/intechopen.1006120"
ARMAN = "10.5772/31647"
MANNHOLD = "10.1002/jps.21494"
MANSOURI = "10.1186/s13321-018-0263-1"
KROTKO = "10.1186/s13321-020-00453-4"
SORGUN = "10.1021/acs.jcim.4c02013"
VEITH = "10.1139/f79-146"          # failed: no PDF, bib entry only
BERTELSEN = "10.1002/etc.5620170803"  # failed: no PDF, multi-line bib entry

# The keys the bib-entry rule gives on a first-time keying of the fixture.
EXPECTED_PDF_KEYS = {
    DOSSOU: "AVDossouOlory2025",   # author={A.V. Dossou-Olory, Audace and ...}
    ARMAN: "Arman2012",            # Crossref first author, not OpenAlex's Taherpour
    MANNHOLD: "Mannhold2009",      # Crossref year, not OpenAlex's 2008
    MANSOURI: "Mansouri2018",
    KROTKO: "Krotko2020",
    SORGUN: "Sorgun2025",
}
ALL_DOIS = [VEITH, MANSOURI, BERTELSEN, KROTKO, DOSSOU, MANNHOLD, ARMAN, SORGUN]


def _pdf(text: str) -> bytes:
    """A one-page, text-extractable PDF (so the acquirer's normalizer accepts it)."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = writer._add_object(font)
    resources = DictionaryObject()
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _stage(lit: Path) -> None:
    """Lay the fixture down at ``lit`` as paperforge left it (one PDF per sidecar)."""
    lit.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURE, lit, dirs_exist_ok=True)
    for sidecar in (lit / "pdfs").glob("*.json"):
        doi = json.loads(sidecar.read_text(encoding="utf-8"))["doi"]
        sidecar.with_suffix(".pdf").write_bytes(_pdf(doi))


def _records(lit: Path):
    return PaperforgeAdapter.parse_manifest(lit / "manifest.csv")


def _bib(lit: Path) -> str:
    return (lit / "references.bib").read_text(encoding="utf-8")


def _bib_key_of(lit: Path) -> dict[str, str]:
    return {e.doi: e.key for e in parse_bib_entries(_bib(lit)) if e.doi}


def _manifest_filename_of(lit: Path) -> dict[str, str]:
    with open(lit / "manifest.csv", newline="", encoding="utf-8") as f:
        return {normalize_doi(r["doi"]): r["filename"] for r in csv.DictReader(f)}


def _sidecar_doi(path: Path) -> str:
    return normalize_doi(json.loads(path.read_text(encoding="utf-8"))["doi"])


def _assert_all_agree(lit: Path, expected: dict[str, str]) -> None:
    """PDF stem == sidecar stem == manifest filename stem == bib key, per DOI."""
    bib_keys = _bib_key_of(lit)
    filenames = _manifest_filename_of(lit)
    pdfs = lit / "pdfs"
    for doi, key in expected.items():
        assert bib_keys[doi] == key, doi
        assert filenames[doi] == f"{key}.pdf", doi
        assert (pdfs / f"{key}.pdf").is_file(), doi
        assert _sidecar_doi(pdfs / f"{key}.json") == doi, doi
    on_disk = {p.stem for p in pdfs.glob("*.pdf")}
    assert on_disk == set(expected.values())


# -- first-time keying ---------------------------------------------------------


def test_first_time_keys_come_from_the_bib_entry_and_every_artifact_agrees(tmp_path):
    lit = tmp_path / "literature"
    snapshot = snapshot_literature(lit)  # empty store: every DOI is a first-timer
    _stage(lit)

    result = key_and_merge(lit, _records(lit), _bib(lit), snapshot)

    assert {normalize_doi(d): k for d, k in result.mapping.items()} == EXPECTED_PDF_KEYS
    assert result.collisions == []
    _assert_all_agree(lit, EXPECTED_PDF_KEYS)
    # DOIs without a PDF are keyed by the same rule from their own entries.
    assert _bib_key_of(lit)[VEITH] == "Veith1979"
    assert _bib_key_of(lit)[BERTELSEN] == "Bertelsen1998"
    assert _braces_balanced(_bib(lit))


def test_acquire_call_on_real_output_leaves_pdf_and_bib_keys_in_agreement(tmp_path):
    """End to end through LiteratureAcquirer, with paperforge replayed from the fixture."""

    class Replay:
        def fetch(self, dois, output_dir, **_options):
            out = Path(output_dir)
            _stage(out)
            manifest = out / "manifest.csv"
            return AcquisitionResult(
                returncode=1, output_dir=out, manifest_path=manifest,
                records=PaperforgeAdapter.parse_manifest(manifest),
                provenance={"tool": "paperforge", "pinned_sha": PIN,
                            "installed_version": "0.1.0", "returncode": 1},
            )

    import types
    acq = LiteratureAcquirer(types.SimpleNamespace(id="bcfkow"),
                             workspace_dir=tmp_path, adapter=Replay())
    outcome = acq.acquire(ALL_DOIS)

    lit = tmp_path / "runs" / "bcfkow" / "literature"
    assert {normalize_doi(d): k for d, k in outcome.citation_keys.items()} \
        == EXPECTED_PDF_KEYS
    _assert_all_agree(lit, EXPECTED_PDF_KEYS)


def test_first_author_family_name_forms():
    assert bib_first_author_family("A.V. Dossou-Olory, Audace and A. Mojeed, Sodiq") \
        == "A.V. Dossou-Olory"
    assert bib_first_author_family("Arman, Avat and Taherpour, Zhiva") == "Arman"
    assert bib_first_author_family("Gilman D. Veith AND B. Other") == "Veith"
    assert bib_first_author_family("van Gestel, C.A.M. and Otermann, K.") == "van Gestel"
    assert bib_first_author_family("{World Health Organization} and Smith, J.") \
        == "World Health Organization"
    assert bib_first_author_family("{Barnes and Noble}, Inc") == "Barnes and Noble"
    assert bib_first_author_family("") == ""


def test_entry_base_reads_quoted_and_bare_fields_and_rejects_unusable_ones():
    assert bib_entry_base('@article{X, author = "Smith, J.", year = 2001}') == "Smith2001"
    assert bib_entry_base("@article{X, title={The author = Jones}, author={Lee, K.},"
                          " year={2003}}") == "Lee2003"
    assert bib_entry_base("@article{X, author={Smith, J.}, month=Apr }") is None
    assert bib_entry_base("@article{X, year={2001}}") is None
    assert bib_entry_base("@article{X, author={{}}, year={2001}}") is None


def test_entry_without_usable_author_falls_back_to_sidecar_then_paperforge_key(tmp_path):
    lit = tmp_path / "literature"
    snapshot = snapshot_literature(lit)
    _stage(lit)
    bib = _bib(lit)
    # Strip the author field from one PDF entry (-> sidecar) and one no-PDF entry
    # (-> paperforge's key).
    bib = bib.replace("author={Arman, Avat and Taherpour, Zhiva and Taherpour, Omid}, ", "")
    bib = bib.replace(
        "author={Veith, Gilman D. and DeFoe, David L. and Bergstedt, Barbara V.}, ", "")

    key_and_merge(lit, _records(lit), bib, snapshot)

    keys = _bib_key_of(lit)
    assert keys[ARMAN] == "Taherpour2012"
    assert (lit / "pdfs" / "Taherpour2012.pdf").is_file()
    assert keys[VEITH] == "Veith1979"


# -- re-keying one-line entries --------------------------------------------------


def test_one_line_entry_is_rekeyed_with_the_rest_of_the_line_intact(tmp_path):
    bib_path = tmp_path / "references.bib"
    shutil.copy(FIXTURE / "references.bib", bib_path)
    before = bib_path.read_text(encoding="utf-8")
    assert "@inbook{Arman2012, title=" in before  # the real one-line layout

    _rewrite_bib(bib_path, {ARMAN: "Taherpour2012"})

    after = bib_path.read_text(encoding="utf-8")
    assert after == before.replace("@inbook{Arman2012,", "@inbook{Taherpour2012,", 1)
    assert _braces_balanced(after)


def test_rewrite_bib_matches_dois_case_insensitively_and_skips_unmapped(tmp_path):
    bib_path = tmp_path / "references.bib"
    shutil.copy(FIXTURE / "references.bib", bib_path)
    before = bib_path.read_text(encoding="utf-8")

    _rewrite_bib(bib_path, {"10.1002/ETC.5620170803": "Bertelsen1998x",
                            "10.9999/not-there": "Nobody2000"})

    after = bib_path.read_text(encoding="utf-8")
    assert after == before.replace("@article{Bertelsen1998,",
                                   "@article{Bertelsen1998x,", 1)


def test_sidecar_keying_path_rekeys_one_line_bib_entries(tmp_path):
    """assign_and_apply_citation_keys (sidecar-based) must reach one-line entries too."""
    lit = tmp_path / "literature"
    _stage(lit)

    result = assign_and_apply_citation_keys(lit, _records(lit))

    bib_keys = _bib_key_of(lit)
    for doi, key in result.mapping.items():
        assert bib_keys[normalize_doi(doi)] == key
        assert (lit / "pdfs" / f"{key}.pdf").is_file()


def test_find_recorded_key_reads_one_line_entries():
    assert find_recorded_key(FIXTURE, VEITH) == "Veith1979"
    assert find_recorded_key(FIXTURE, ARMAN) == "Arman2012"


# -- keys never change once assigned ------------------------------------------------


def test_already_keyed_doi_keeps_its_key_on_a_later_call(tmp_path):
    """A DOI keyed earlier (under the old sidecar rule) keeps that key and entry text."""
    lit = tmp_path / "literature"
    _stage(lit)
    prior = _bib(lit).replace("@inbook{AVDossouOlory2025,", "@inbook{DossouOlory2025,", 1)
    (lit / "references.bib").write_text(prior, encoding="utf-8")
    snapshot = snapshot_literature(lit)

    # paperforge re-run for that DOI: success row skipped, bib rewritten raw.
    raw_entry = next(e.text for e in parse_bib_entries(
        (FIXTURE / "references.bib").read_text(encoding="utf-8")) if e.doi == DOSSOU)
    records = [r for r in _records(lit) if normalize_doi(r.doi) == DOSSOU]
    result = key_and_merge(lit, records, raw_entry + "\n", snapshot)

    assert result.mapping == {records[0].doi: "DossouOlory2025"}
    assert _bib(lit) == prior
    assert (lit / "pdfs" / "DossouOlory2025.pdf").is_file()
    assert _manifest_filename_of(lit)[DOSSOU] == "DossouOlory2025.pdf"


def test_later_call_moves_a_mismatched_pdf_to_its_existing_bib_key(tmp_path):
    """The trial-run state heals on re-request: the bib key stands, the PDF follows."""
    lit = tmp_path / "literature"
    _stage(lit)  # PDF DossouOlory2025.pdf, bib key AVDossouOlory2025
    prior = _bib(lit)
    snapshot = snapshot_literature(lit)

    records = [r for r in _records(lit) if normalize_doi(r.doi) == DOSSOU]
    key_and_merge(lit, records, prior, snapshot)

    assert _bib(lit) == prior
    assert (lit / "pdfs" / "AVDossouOlory2025.pdf").is_file()
    assert (lit / "pdfs" / "AVDossouOlory2025.json").is_file()
    assert not (lit / "pdfs" / "DossouOlory2025.pdf").exists()
    assert _manifest_filename_of(lit)[DOSSOU] == "AVDossouOlory2025.pdf"


# -- verify advisory ------------------------------------------------------------------


_NON_CIRC = "the verifier checks a property not baked into the generator"


def _seed_run(tmp_path: Path, spec_id: str) -> Path:
    spec = Spec(
        id=spec_id,
        version=1,
        raw_proposal=RawProposal(background="b", goal="g", method="m", expected_output="o"),
        hypotheses=[
            Hypothesis(
                id="hyp-n", statement="Z holds",
                mode=HypothesisMode.CONFIRMATORY,
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.THRESHOLD,
                    expression="point >= threshold => support",
                    params={"statistic": "point", "op": ">=", "value": 0.9},
                ),
                referent="formal",
                non_circularity=_NON_CIRC,
            )
        ],
        method=MethodPlan(approaches=["a"], tools=[]),
        target_claims=[TargetClaim(id="tc", statement="t", answers="hyp-n")],
    )

    def experiment(s, w):
        return [EvidenceItem(
            id="ev-num", spec_id=s.id, kind=EvidenceKind.EXPERIMENT_RUN,
            provenance=Provenance(code_ref="fixture", data_source="generated"),
            result=Result(type="quantitative", point=0.95),
            bears_on=[Bearing(target_id="hyp-n", direction=BearingDirection.SUPPORTS)],
        )]

    run_dir = tmp_path / "runs" / spec.id
    run_checkpoint_loop(run_dir=run_dir, spec=spec, experiment=experiment,
                        workspace_dir=tmp_path)
    shutil.rmtree(run_dir / "paper", ignore_errors=True)
    return run_dir


def _key_notes(report) -> list[str]:
    return [n for n in report.paper_advisory if n.startswith("literature key:")]


def test_verify_advises_on_each_pdf_whose_name_is_not_a_bib_key(tmp_path):
    run_dir = _seed_run(tmp_path, "lk-mismatch")
    baseline = verify_run(run_dir)
    _stage(run_dir / "literature")  # the trial run's real state

    report = verify_run(run_dir)

    notes = _key_notes(report)
    assert len(notes) == 3
    for pdf, key in (("DossouOlory2025.pdf", "AVDossouOlory2025"),
                     ("Taherpour2012.pdf", "Arman2012"),
                     ("Mannhold2008.pdf", "Mannhold2009")):
        assert any(pdf in n and key in n for n in notes), pdf
    assert report.passed == baseline.passed  # advisory only, never gated


def test_verify_is_silent_when_every_pdf_is_a_bib_key(tmp_path):
    run_dir = _seed_run(tmp_path, "lk-clean")
    lit = run_dir / "literature"
    snapshot = snapshot_literature(lit)
    _stage(lit)
    key_and_merge(lit, _records(lit), _bib(lit), snapshot)
    # A supplementary file of a keyed paper is not a mismatch.
    (lit / "pdfs" / "Mansouri2018_SI.pdf").write_bytes(_pdf("si"))

    assert _key_notes(verify_run(run_dir)) == []


def test_verify_advises_on_a_pdf_with_no_bib_entry(tmp_path):
    run_dir = _seed_run(tmp_path, "lk-orphan")
    lit = run_dir / "literature"
    snapshot = snapshot_literature(lit)
    _stage(lit)
    key_and_merge(lit, _records(lit), _bib(lit), snapshot)
    (lit / "pdfs" / "Orphan2001.pdf").write_bytes(_pdf("orphan"))
    (lit / "pdfs" / "Ghost1999_SI.pdf").write_bytes(_pdf("ghost si"))

    notes = _key_notes(verify_run(run_dir))

    assert len(notes) == 2
    assert any("Orphan2001.pdf" in n for n in notes)
    assert any("Ghost1999_SI.pdf" in n for n in notes)
