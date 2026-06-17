"""
Network-free unit tests for the literature acquisition loop stage.

A fake adapter stands in for paperforge (no subprocess, no network); the Spec is
a minimal stub since the stage only reads ``spec.id``. These verify the stage's
real jobs: turning an acquisition result into a LITERATURE EvidenceItem under
runs/<spec.id>/, persisting it, and raising the right halt (unacquired papers /
Supporting Information needed).
"""

import json
import types
from pathlib import Path

from sci_adk.core.evidence import BearingDirection, EvidenceItem, EvidenceKind
from sci_adk.loop.literature_acquirer import (
    AcquisitionHalt,
    AcquisitionOutcome,
    HaltItem,
    HaltReason,
    LiteratureAcquirer,
    acquire_literature,
)
from sci_adk.search.paperforge_adapter import AcquisitionRecord, AcquisitionResult

PIN = "60fefedacb7349c755c29b2c2f26873464158c12"


class FakeAdapter:
    """Records the fetch call and returns a result built from the given dir."""

    def __init__(self, records, returncode=0):
        self.records = records
        self.returncode = returncode
        self.calls = []

    def fetch(self, dois, output_dir, **options):
        output_dir = Path(output_dir)
        self.calls.append((list(dois), output_dir, options))
        return AcquisitionResult(
            returncode=self.returncode,
            output_dir=output_dir,
            manifest_path=output_dir / "manifest.csv",
            records=self.records,
            provenance={
                "tool": "paperforge",
                "pinned_sha": PIN,
                "installed_version": "0.1.0",
                "returncode": self.returncode,
            },
        )


def _spec(spec_id="test-spec"):
    return types.SimpleNamespace(id=spec_id)


def test_acquire_writes_literature_evidence(tmp_path):
    records = [
        AcquisitionRecord(doi="10.1/a", status="success",
                          source="arxiv", filename="A.pdf"),
        AcquisitionRecord(doi="10.2/b", status="failed", error="no OA PDF"),
    ]
    adapter = FakeAdapter(records, returncode=1)
    acquirer = LiteratureAcquirer(_spec(), workspace_dir=tmp_path, adapter=adapter)

    outcome = acquirer.acquire(["10.1/a", "10.2/b"])
    assert isinstance(outcome, AcquisitionOutcome)
    ev = outcome.evidence

    assert isinstance(ev, EvidenceItem)
    assert ev.kind == EvidenceKind.LITERATURE
    assert ev.spec_id == "test-spec"
    assert ev.result.type == "qualitative"

    summary = json.loads(ev.result.finding)
    assert summary["counts"] == {"succeeded": 1, "failed": 1}
    assert summary["acquired"][0]["doi"] == "10.1/a"
    assert summary["acquired"][0]["source"] == "arxiv"
    assert summary["failed"][0]["doi"] == "10.2/b"

    lit_dir = tmp_path / "runs" / "test-spec" / "literature"
    assert ev.result.artifact_ref == str(lit_dir)
    assert ev.provenance.data_ref == str(lit_dir / "manifest.csv")
    assert "paperforge@60fefed" in ev.provenance.environment

    # the adapter was driven with the run's literature dir
    called_dois, called_dir, _ = adapter.calls[0]
    assert called_dois == ["10.1/a", "10.2/b"]
    assert called_dir == lit_dir

    # evidence is persisted to the append-only log on disk
    ev_files = list((tmp_path / "runs" / "test-spec" / "evidence").glob("*.json"))
    assert len(ev_files) == 1
    on_disk = json.loads(ev_files[0].read_text(encoding="utf-8"))
    assert on_disk["kind"] == "literature"
    assert on_disk["spec_id"] == "test-spec"


def test_no_target_means_empty_bears_on(tmp_path):
    adapter = FakeAdapter([AcquisitionRecord(doi="10.1/a", status="success")])
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/a"])
    assert outcome.evidence.bears_on == []


def test_target_id_attaches_neutral_bearing(tmp_path):
    adapter = FakeAdapter([AcquisitionRecord(doi="10.1/a", status="success")])
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/a"], target_id="hyp-1")
    bears_on = outcome.evidence.bears_on
    assert len(bears_on) == 1
    assert bears_on[0].target_id == "hyp-1"
    # acquisition asserts no direction of its own -> NEUTRAL context link
    assert bears_on[0].direction == BearingDirection.NEUTRAL


def test_options_passthrough_via_convenience(tmp_path):
    adapter = FakeAdapter([AcquisitionRecord(doi="10.1/a", status="success")])
    outcome = acquire_literature(
        _spec("s2"), ["10.1/a"], workspace_dir=tmp_path, adapter=adapter,
        source_order=["arxiv"], no_metadata=True,
    )
    assert isinstance(outcome, AcquisitionOutcome)
    _, _, options = adapter.calls[0]
    assert options["source_order"] == ["arxiv"]
    assert options["no_metadata"] is True


# -- halt gates --------------------------------------------------------------

def test_unacquired_papers_trigger_halt(tmp_path):
    records = [
        AcquisitionRecord(doi="10.1/ok", status="success", source="arxiv"),
        AcquisitionRecord(doi="10.2/miss", status="failed", error="no OA PDF"),
        AcquisitionRecord(doi="10.3/miss", status="failed", error="paywalled"),
    ]
    adapter = FakeAdapter(records, returncode=1)
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(
                                     ["10.1/ok", "10.2/miss", "10.3/miss"])

    assert outcome.should_halt is True
    assert outcome.halt.reason == HaltReason.UNACQUIRED_PAPERS
    # the halt lists exactly the misses, with their reasons, for user feedback
    halted = {it.doi: it.detail for it in outcome.halt.items}
    assert halted == {"10.2/miss": "no OA PDF", "10.3/miss": "paywalled"}
    fb = outcome.halt.feedback()
    assert "10.2/miss" in fb and "paywalled" in fb
    # the whole batch is still recorded (the success too) -- halt != skip
    assert json.loads(outcome.evidence.result.finding)["counts"]["succeeded"] == 1


def test_all_acquired_means_no_halt(tmp_path):
    records = [
        AcquisitionRecord(doi="10.1/a", status="success", source="arxiv"),
        AcquisitionRecord(doi="10.2/b", status="success", source="unpaywall"),
    ]
    adapter = FakeAdapter(records, returncode=0)
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/a", "10.2/b"])
    assert outcome.should_halt is False
    assert outcome.halt is None


def test_supporting_info_halt_factory():
    # Condition 2 is agent-judged: the orchestrator builds this after Claude
    # reads a main text and decides the SI is required.
    halt = AcquisitionHalt.for_supporting_info(
        [HaltItem(doi="10.1/a", detail="needs SI table S3", title="Paper A")],
        note="dataset lives only in the SI.",
    )
    assert halt.reason == HaltReason.SUPPORTING_INFO_NEEDED
    assert halt.items[0].doi == "10.1/a"
    fb = halt.feedback()
    assert "Supporting Information" in fb
    assert "10.1/a" in fb and "table S3" in fb
    assert "dataset lives only in the SI." in fb


# -- auto-normalization of acquired PDFs -------------------------------------
#
# paperforge writes each acquired PDF into ``<output_dir>/pdfs/<filename>``
# (confirmed against runs/.../literature/pdfs/). The acquirer must, after
# fetch, normalize each acquired PDF in place: owner/permission-restricted-but-
# openable PDFs get re-written extractable; a real user-password lock is
# surfaced (never bypassed). The outcome must record what happened per PDF.

import io  # noqa: E402  (kept local to this PDF-fixture section)

from pypdf import PdfReader, PdfWriter  # noqa: E402
from pypdf.constants import UserAccessPermissions as UAP  # noqa: E402
from pypdf.generic import (  # noqa: E402
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

PDF_MARKER = "ACQUIRED PAPER TEXT"


def _text_pdf_bytes(text: str = PDF_MARKER) -> bytes:
    """A one-page PDF whose page draws ``text`` (pypdf only, no reportlab)."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    content = f"BT /F1 18 Tf 20 100 Td ({text}) Tj ET".encode("latin-1")
    stream = DecodedStreamObject()
    stream.set_data(content)
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


def _owner_restricted_bytes(raw: bytes) -> bytes:
    writer = PdfWriter(clone_from=io.BytesIO(raw))
    writer.encrypt(user_password="", owner_password="x", permissions_flag=UAP.PRINT)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _user_locked_bytes(raw: bytes) -> bytes:
    writer = PdfWriter(clone_from=io.BytesIO(raw))
    writer.encrypt(user_password="secret", owner_password="x")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class FileDroppingAdapter:
    """A fake adapter that writes real PDF files into ``<output_dir>/pdfs/``.

    ``files`` maps a filename -> bytes; each becomes a successful record whose
    ``filename`` points at the dropped file (paperforge's contract).
    """

    def __init__(self, files: dict, extra_records=None, returncode=0):
        self.files = files
        self.extra_records = extra_records or []
        self.returncode = returncode
        self.calls = []

    def fetch(self, dois, output_dir, **options):
        output_dir = Path(output_dir)
        self.calls.append((list(dois), output_dir, options))
        pdf_dir = output_dir / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        records = []
        for i, (filename, data) in enumerate(self.files.items(), start=1):
            (pdf_dir / filename).write_bytes(data)
            records.append(
                AcquisitionRecord(
                    doi=f"10.{i}/x", status="success",
                    source="arxiv", filename=filename,
                )
            )
        records.extend(self.extra_records)
        return AcquisitionResult(
            returncode=self.returncode,
            output_dir=output_dir,
            manifest_path=output_dir / "manifest.csv",
            records=records,
            provenance={"tool": "paperforge", "pinned_sha": PIN,
                        "installed_version": "0.1.0", "returncode": self.returncode},
        )


def _pdfs_dir(tmp_path, spec_id="test-spec"):
    return tmp_path / "runs" / spec_id / "literature" / "pdfs"


def test_acquire_normalizes_owner_restricted_pdf(tmp_path):
    raw = _text_pdf_bytes()
    adapter = FileDroppingAdapter({"restricted.pdf": _owner_restricted_bytes(raw)})
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/x"])

    pdf = _pdfs_dir(tmp_path) / "restricted.pdf"
    # auto-normalized in place: no longer encrypted, text extracts
    assert PdfReader(str(pdf)).is_encrypted is False
    assert PDF_MARKER in PdfReader(str(pdf)).pages[0].extract_text()
    # original preserved alongside
    assert (_pdfs_dir(tmp_path) / "restricted.orig.pdf").exists()

    # the LITERATURE evidence honestly records the normalization
    summary = json.loads(outcome.evidence.result.finding)
    norm = summary["normalization"]
    assert norm["counts"]["normalized"] == 1
    entry = norm["pdfs"][0]
    assert entry["filename"] == "restricted.pdf"
    assert entry["status"] == "normalized"
    assert entry["original_preserved"] is True
    # not a locked-surfacing situation
    assert outcome.locked_pdfs == []


def test_acquire_noop_for_already_extractable_pdf(tmp_path):
    raw = _text_pdf_bytes()
    adapter = FileDroppingAdapter({"plain.pdf": raw})
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/x"])

    pdf = _pdfs_dir(tmp_path) / "plain.pdf"
    # untouched
    assert pdf.read_bytes() == raw
    assert not (_pdfs_dir(tmp_path) / "plain.orig.pdf").exists()

    summary = json.loads(outcome.evidence.result.finding)
    norm = summary["normalization"]
    assert norm["counts"]["already_extractable"] == 1
    assert norm["pdfs"][0]["status"] == "already_extractable"
    assert outcome.locked_pdfs == []


def test_acquire_surfaces_user_locked_pdf(tmp_path):
    raw = _text_pdf_bytes()
    locked = _user_locked_bytes(raw)
    # one normal + one locked in the same batch
    adapter = FileDroppingAdapter(
        {"good.pdf": _owner_restricted_bytes(raw), "locked.pdf": locked}
    )
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/x", "10.2/x"])

    # the locked file is surfaced (never silently passed) ...
    assert "locked.pdf" in outcome.locked_pdfs
    # ... and ETHICS: it is left byte-for-byte unmodified, still encrypted
    locked_path = _pdfs_dir(tmp_path) / "locked.pdf"
    assert locked_path.read_bytes() == locked
    assert PdfReader(str(locked_path)).is_encrypted is True

    # recorded in provenance/finding honestly
    summary = json.loads(outcome.evidence.result.finding)
    norm = summary["normalization"]
    assert norm["counts"]["locked"] == 1
    assert norm["counts"]["normalized"] == 1
    locked_entry = next(p for p in norm["pdfs"] if p["filename"] == "locked.pdf")
    assert locked_entry["status"] == "locked"
    assert locked_entry["note"]  # a clear reason

    # the good one was still normalized
    assert PdfReader(str(_pdfs_dir(tmp_path) / "good.pdf")).is_encrypted is False


def test_acquire_locked_surfacing_visible_in_outcome_helper(tmp_path):
    raw = _text_pdf_bytes()
    adapter = FileDroppingAdapter({"locked.pdf": _user_locked_bytes(raw)})
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/x"])
    # a convenience flag the orchestrator can check, parallel to should_halt
    assert outcome.has_locked_pdfs is True
    assert outcome.locked_pdfs == ["locked.pdf"]


def test_acquire_failed_record_is_not_normalized(tmp_path):
    # A failed DOI has no file on disk; normalization must skip it cleanly.
    raw = _text_pdf_bytes()
    adapter = FileDroppingAdapter(
        {"ok.pdf": raw},
        extra_records=[AcquisitionRecord(doi="10.9/miss", status="failed",
                                         error="no OA PDF")],
        returncode=1,
    )
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/x", "10.9/miss"])
    # the unacquired-papers halt still fires (existing behavior preserved)
    assert outcome.should_halt is True
    # normalization only covered the one acquired file
    norm = json.loads(outcome.evidence.result.finding)["normalization"]
    assert norm["counts"]["already_extractable"] == 1
    assert {p["filename"] for p in norm["pdfs"]} == {"ok.pdf"}


# -- corrupt acquired PDF: re-download retry (exactly 2 extra attempts) -------
#
# When an acquired PDF cannot be PARSED (truncated, HTML-as-pdf, corrupt), the
# acquirer re-downloads that single DOI up to 2 more times (total 3 attempts),
# re-normalizing each fresh file. Stays-corrupt -> status ``error``, surfaced via
# ``unreadable_pdfs``, recorded in provenance; the batch continues. Corrupt-then-
# good -> ends ``normalized``. A ``locked`` (user-password) PDF is NOT retried.

CORRUPT = b"%PDF-1.4\nnot a real pdf body at all"


class RetryAdapter:
    """A fake adapter that maps DOI -> (filename, [bytes_per_attempt]).

    Each ``fetch`` call writes, for every requested DOI, the payload for that
    DOI's current attempt (the last payload sticks once exhausted). It counts how
    many times each DOI was fetched -- so a test can assert "3x total" (1 original
    + 2 retries). The original batch fetch requests all DOIs; each retry requests
    exactly one DOI.
    """

    def __init__(self, plan: dict, returncode: int = 0):
        # plan: doi -> {"filename": str, "payloads": [bytes, bytes, ...]}
        self.plan = plan
        self.returncode = returncode
        self.calls = []                  # list of (dois, options)
        self.fetch_count = {}            # doi -> times fetched

    def fetch(self, dois, output_dir, **options):
        output_dir = Path(output_dir)
        dois = list(dois)
        self.calls.append((dois, options))
        pdf_dir = output_dir / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        records = []
        for doi in dois:
            spec = self.plan[doi]
            n = self.fetch_count.get(doi, 0)        # 0-based attempt index
            payloads = spec["payloads"]
            data = payloads[min(n, len(payloads) - 1)]
            (pdf_dir / spec["filename"]).write_bytes(data)
            self.fetch_count[doi] = n + 1
            records.append(
                AcquisitionRecord(doi=doi, status="success",
                                  source="arxiv", filename=spec["filename"])
            )
        return AcquisitionResult(
            returncode=self.returncode,
            output_dir=output_dir,
            manifest_path=output_dir / "manifest.csv",
            records=records,
            provenance={"tool": "paperforge", "pinned_sha": PIN,
                        "installed_version": "0.1.0", "returncode": self.returncode},
        )


def test_corrupt_pdf_retried_exactly_twice_then_error_batch_not_aborted(tmp_path):
    good = _text_pdf_bytes()
    # "bad" DOI is corrupt on every attempt; "ok" DOI is a fine owner-restricted
    # paper (so we also prove the batch is NOT aborted by the bad one).
    adapter = RetryAdapter({
        "10.1/bad": {"filename": "bad.pdf", "payloads": [CORRUPT]},   # always corrupt
        "10.2/ok": {"filename": "ok.pdf",
                    "payloads": [_owner_restricted_bytes(good)]},
    })
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/bad", "10.2/ok"])

    # the bad DOI was fetched 3x total: 1 original + exactly 2 retries
    assert adapter.fetch_count["10.1/bad"] == 3
    # the good DOI was fetched once (no spurious retry)
    assert adapter.fetch_count["10.2/ok"] == 1

    # the corrupt file ends as an error, surfaced via unreadable_pdfs
    assert outcome.unreadable_pdfs == ["bad.pdf"]
    assert outcome.has_unreadable_pdfs is True

    # the OTHER good PDF in the same batch was still normalized -- batch NOT aborted
    ok_pdf = _pdfs_dir(tmp_path) / "ok.pdf"
    assert PdfReader(str(ok_pdf)).is_encrypted is False
    assert PDF_MARKER in PdfReader(str(ok_pdf)).pages[0].extract_text()

    # the evidence records the error count + retries spent
    norm = json.loads(outcome.evidence.result.finding)["normalization"]
    assert norm["counts"]["error"] == 1
    assert norm["counts"]["normalized"] == 1
    bad_entry = next(p for p in norm["pdfs"] if p["filename"] == "bad.pdf")
    assert bad_entry["status"] == "error"
    assert bad_entry["retries_spent"] == 2


def test_corrupt_then_good_on_retry_ends_normalized(tmp_path):
    good = _text_pdf_bytes()
    # corrupt on attempt 1, then a valid owner-restricted PDF on retry 1
    adapter = RetryAdapter({
        "10.1/x": {"filename": "paper.pdf",
                   "payloads": [CORRUPT, _owner_restricted_bytes(good)]},
    })
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/x"])

    # exactly 2 fetches: original (corrupt) + 1 retry (good) -> stop early
    assert adapter.fetch_count["10.1/x"] == 2
    # ended normalized, nothing surfaced as unreadable
    assert outcome.unreadable_pdfs == []
    assert outcome.has_unreadable_pdfs is False
    pdf = _pdfs_dir(tmp_path) / "paper.pdf"
    assert PdfReader(str(pdf)).is_encrypted is False
    assert PDF_MARKER in PdfReader(str(pdf)).pages[0].extract_text()
    norm = json.loads(outcome.evidence.result.finding)["normalization"]
    assert norm["counts"]["normalized"] == 1
    assert norm["counts"]["error"] == 0


def test_corrupt_then_good_on_second_retry_ends_normalized(tmp_path):
    good = _text_pdf_bytes()
    # corrupt, corrupt, then good on the 2nd (final allowed) retry
    adapter = RetryAdapter({
        "10.1/x": {"filename": "paper.pdf",
                   "payloads": [CORRUPT, CORRUPT, _owner_restricted_bytes(good)]},
    })
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/x"])

    # 3 fetches: original + 2 retries, the last one succeeds
    assert adapter.fetch_count["10.1/x"] == 3
    assert outcome.unreadable_pdfs == []
    pdf = _pdfs_dir(tmp_path) / "paper.pdf"
    assert PdfReader(str(pdf)).is_encrypted is False
    norm = json.loads(outcome.evidence.result.finding)["normalization"]
    assert norm["counts"]["normalized"] == 1


def test_locked_pdf_is_not_retried(tmp_path):
    # A user-password lock would re-download to the same lock; surface it
    # immediately WITHOUT spending retries (re-fetch called exactly once).
    adapter = RetryAdapter({
        "10.1/x": {"filename": "locked.pdf",
                   "payloads": [_user_locked_bytes(_text_pdf_bytes())]},
    })
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/x"])

    # NOT retried: exactly one fetch for the locked DOI
    assert adapter.fetch_count["10.1/x"] == 1
    # surfaced as locked (unchanged behavior), not as unreadable
    assert outcome.locked_pdfs == ["locked.pdf"]
    assert outcome.unreadable_pdfs == []
    # ETHICS: still encrypted, never bypassed
    locked_path = _pdfs_dir(tmp_path) / "locked.pdf"
    assert PdfReader(str(locked_path)).is_encrypted is True
    norm = json.loads(outcome.evidence.result.finding)["normalization"]
    assert norm["counts"]["locked"] == 1


# -- citation-key naming wired into acquire ----------------------------------
#
# After fetch + PDF-normalize, the acquirer applies sci-adk's OWN citation-key
# convention (<Surname><Year>, a/b-by-DOI on collision) to the acquired files:
# the PDF/sidecar are renamed, references.bib + manifest.csv are updated, and the
# DOI->key mapping is recorded in the LITERATURE evidence + surfaced on the
# outcome. paperforge already wrote surname+year filenames; sci-adk owns the
# a/b disambiguation as a post-acquisition step.


class KeyingAdapter:
    """A fake adapter that lays out the full acquired dir paperforge produces.

    ``papers`` is a list of (doi, author, year, on_disk_filename, pdf_bytes).
    Writes each PDF + its ``<stem>.json`` sidecar into ``pdfs/``, plus a
    ``manifest.csv`` and a ``references.bib`` -- everything the keying step reads.
    """

    def __init__(self, papers, returncode=0):
        self.papers = papers
        self.returncode = returncode
        self.calls = []

    def fetch(self, dois, output_dir, **options):
        output_dir = Path(output_dir)
        self.calls.append((list(dois), output_dir, options))
        pdf_dir = output_dir / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        records = []
        manifest = ["index,doi,status,source,license,filename,origin,error"]
        bib = []
        for i, (doi, author, year, filename, data) in enumerate(self.papers, start=1):
            stem = Path(filename).stem
            (pdf_dir / filename).write_bytes(data)
            (pdf_dir / f"{stem}.json").write_text(
                json.dumps({"doi": doi, "author": author, "year": year}),
                encoding="utf-8",
            )
            records.append(AcquisitionRecord(doi=doi, status="success",
                                             source="arxiv", filename=filename))
            manifest.append(f"{i},{doi},success,arxiv,,{filename},cli,")
            bib.append(f"@article{{orig{i},\n  author = {{{author}, X.}},\n"
                       f"  year = {{{year}}},\n  doi = {{{doi}}}\n}}\n")
        (output_dir / "manifest.csv").write_text("\n".join(manifest) + "\n",
                                                 encoding="utf-8")
        (output_dir / "references.bib").write_text("\n".join(bib),
                                                   encoding="utf-8")
        return AcquisitionResult(
            returncode=self.returncode,
            output_dir=output_dir,
            manifest_path=output_dir / "manifest.csv",
            records=records,
            provenance={"tool": "paperforge", "pinned_sha": PIN,
                        "installed_version": "0.1.0", "returncode": self.returncode},
        )


def test_acquire_applies_citation_keys_and_records_mapping(tmp_path):
    good = _text_pdf_bytes()
    # two Jager 1998 papers (collision) + one Joe 2026; raw on-disk names differ
    # from the keys so we prove the rename ran.
    adapter = KeyingAdapter([
        ("10.9/zzz", "Jager", "1998", "raw_b.pdf", good),
        ("10.1/aaa", "Jager", "1998", "raw_a.pdf", good),
        ("10.5/joe", "Joe", "2026", "raw_joe.pdf", good),
    ])
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(
                                     ["10.9/zzz", "10.1/aaa", "10.5/joe"])

    pdfs = _pdfs_dir(tmp_path)
    # renamed by key; a/b by DOI ascending
    assert (pdfs / "Jager1998a.pdf").exists()   # lower DOI 10.1/aaa
    assert (pdfs / "Jager1998b.pdf").exists()   # higher DOI 10.9/zzz
    assert (pdfs / "Joe2026.pdf").exists()
    assert (pdfs / "Jager1998a.json").exists()
    assert not (pdfs / "raw_a.pdf").exists()

    # the DOI->key mapping is recorded in the LITERATURE evidence finding
    summary = json.loads(outcome.evidence.result.finding)
    assert summary["citation_keys"]["10.1/aaa"] == "Jager1998a"
    assert summary["citation_keys"]["10.9/zzz"] == "Jager1998b"
    assert summary["citation_keys"]["10.5/joe"] == "Joe2026"

    # ... and surfaced on the outcome for the orchestrator
    assert outcome.citation_keys["10.1/aaa"] == "Jager1998a"
    assert outcome.key_collisions == []

    # bib + manifest updated consistently
    bib = (tmp_path / "runs" / "test-spec" / "literature"
           / "references.bib").read_text(encoding="utf-8")
    assert "@article{Jager1998a," in bib and "@article{Joe2026," in bib


def test_acquire_surfaces_overwrite_collision(tmp_path):
    good = _text_pdf_bytes()
    # two distinct DOIs that paperforge overwrote into ONE on-disk file: the
    # keyer must surface the loss on the outcome + in evidence, not drop it.
    adapter = KeyingAdapter([
        ("10.1/a", "Jager", "1998", "Jager1998.pdf", good),
        ("10.2/b", "Jager", "1998", "Jager1998.pdf", good),
    ])
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.1/a", "10.2/b"])

    assert outcome.key_collisions, "overwrite collision must be surfaced"
    assert outcome.has_key_collisions is True
    summary = json.loads(outcome.evidence.result.finding)
    assert summary["citation_key_collisions"]  # recorded honestly
    coll = summary["citation_key_collisions"][0]
    assert coll["filename"] == "Jager1998.pdf"
    assert set(coll["dois"]) == {"10.1/a", "10.2/b"}


def test_acquire_keying_is_noop_when_nothing_acquired(tmp_path):
    # a batch where every DOI failed: no files, no keying, no crash.
    adapter = FakeAdapter(
        [AcquisitionRecord(doi="10.9/miss", status="failed", error="no OA PDF")],
        returncode=1,
    )
    outcome = LiteratureAcquirer(_spec(), workspace_dir=tmp_path,
                                 adapter=adapter).acquire(["10.9/miss"])
    assert outcome.citation_keys == {}
    assert outcome.key_collisions == []
    # the existing unacquired-papers halt still fires
    assert outcome.should_halt is True
