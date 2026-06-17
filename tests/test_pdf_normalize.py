"""
Unit tests for owner-restricted PDF normalization (search/pdf_normalize.py).

Fixtures are built *with* pypdf (no external sample files), so each test
controls exactly the encryption shape it exercises:

  - a plain (unencrypted) text PDF                  -> already_extractable
  - an owner/permission-restricted PDF that OPENS   -> normalized
    (encrypted with an EMPTY user password; extraction permission stripped)
  - a USER-password-locked PDF (won't open at all)  -> locked, NEVER cracked
  - an AES owner-restricted PDF (crypto backend)    -> normalized

The locked case is the ethics firewall: removing an owner/permission
restriction on a document you can already open is the legitimate case (OA
papers); bypassing a user password is circumvention and must not happen.
"""

import io

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions as UAP
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from sci_adk.search.pdf_normalize import NormalizeResult, NormalizeStatus, normalize_pdf

MARKER = "HELLO SCIADK 2026"


# -- fixture builders (pypdf only) -------------------------------------------


def _make_text_pdf(text: str = MARKER) -> bytes:
    """A one-page PDF whose page draws ``text`` (so extract_text() returns it)."""
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


def _owner_restricted(raw: bytes, *, algorithm: str | None = None) -> bytes:
    """Owner/permission-restricted PDF that OPENS (empty user password)."""
    writer = PdfWriter(clone_from=io.BytesIO(raw))
    # Allow printing but forbid text/graphics extraction -- the OA-paper shape.
    perms = UAP.PRINT
    writer.encrypt(
        user_password="",
        owner_password="ownersecret",
        permissions_flag=perms,
        algorithm=algorithm,  # None -> default RC4/AES per use_128bit
    )
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _user_locked(raw: bytes) -> bytes:
    """A real user-password lock: the file does NOT open without the password."""
    writer = PdfWriter(clone_from=io.BytesIO(raw))
    writer.encrypt(user_password="realsecret", owner_password="ownersecret")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _extract(path) -> str:
    """Read + extract text from a PDF on disk (no password supplied)."""
    reader = PdfReader(str(path))
    return reader.pages[0].extract_text()


# -- already-extractable (no-op) ---------------------------------------------


def test_plain_pdf_is_noop(tmp_path):
    pdf = tmp_path / "plain.pdf"
    pdf.write_bytes(_make_text_pdf())
    before = pdf.read_bytes()

    result = normalize_pdf(pdf)

    assert isinstance(result, NormalizeResult)
    assert result.status == NormalizeStatus.ALREADY_EXTRACTABLE
    assert result.path == pdf
    assert result.original_path is None  # nothing rewritten -> nothing preserved
    # file is byte-for-byte untouched
    assert pdf.read_bytes() == before
    # already extractable
    assert MARKER in _extract(pdf)


# (the full status set, now including ``error``, is asserted by
# test_status_set_includes_error below)


# -- owner-restricted -> normalized ------------------------------------------


def test_owner_restricted_is_normalized_and_extractable(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(_owner_restricted(_make_text_pdf()))

    # precondition: it's encrypted and extraction is blocked on the raw file
    assert PdfReader(str(pdf)).is_encrypted

    result = normalize_pdf(pdf)

    assert result.status == NormalizeStatus.NORMALIZED
    assert result.path == pdf
    # restrictions gone: the in-place file is no longer encrypted, text extracts
    assert PdfReader(str(pdf)).is_encrypted is False
    assert MARKER in _extract(pdf)
    # the note records the transformation honestly
    assert result.note
    assert "normaliz" in result.note.lower() or "restrict" in result.note.lower()


def test_owner_restricted_preserves_original_by_default(tmp_path):
    pdf = tmp_path / "paper.pdf"
    original_bytes = _owner_restricted(_make_text_pdf())
    pdf.write_bytes(original_bytes)

    result = normalize_pdf(pdf)  # keep_original=True default

    assert result.status == NormalizeStatus.NORMALIZED
    assert result.original_path is not None
    orig = result.original_path
    assert orig.exists()
    # the preserved copy is the untouched encrypted original
    assert orig.read_bytes() == original_bytes
    assert PdfReader(str(orig)).is_encrypted is True


def test_owner_restricted_keep_original_false_leaves_no_backup(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(_owner_restricted(_make_text_pdf()))

    result = normalize_pdf(pdf, keep_original=False)

    assert result.status == NormalizeStatus.NORMALIZED
    assert result.original_path is None
    assert MARKER in _extract(pdf)
    # no stray .orig.pdf left behind
    assert not (tmp_path / "paper.orig.pdf").exists()
    assert list(tmp_path.glob("**/*.orig.pdf")) == []


# -- user-locked -> locked, NEVER cracked ------------------------------------


def test_user_locked_returns_locked_and_is_not_cracked(tmp_path):
    pdf = tmp_path / "locked.pdf"
    locked_bytes = _user_locked(_make_text_pdf())
    pdf.write_bytes(locked_bytes)

    result = normalize_pdf(pdf)

    assert result.status == NormalizeStatus.LOCKED
    # ETHICS: the file is left byte-for-byte unmodified -- nothing was bypassed
    assert pdf.read_bytes() == locked_bytes
    assert result.original_path is None
    # a clear, honest reason is given
    assert result.note
    assert "password" in result.note.lower()
    # and it is STILL encrypted / unreadable without the password (NOT cracked)
    reader = PdfReader(str(pdf))
    assert reader.is_encrypted is True
    with pytest.raises(Exception):
        # extracting text from a still-locked PDF must fail; we did not open it
        _ = reader.pages[0].extract_text()


def test_locked_is_never_rewritten_even_with_keep_original_false(tmp_path):
    pdf = tmp_path / "locked.pdf"
    locked_bytes = _user_locked(_make_text_pdf())
    pdf.write_bytes(locked_bytes)

    result = normalize_pdf(pdf, keep_original=False)

    assert result.status == NormalizeStatus.LOCKED
    # conservative side: do NOT modify a user-locked file under any flag
    assert pdf.read_bytes() == locked_bytes


# -- corrupt / unreadable -> error (no uncaught exception) -------------------
#
# A truncated download, an HTML error page saved as .pdf, or corrupt bytes
# cannot be PARSED. normalize_pdf must catch the parse failure and return an
# ``error``-status result (the acquirer drives the re-download retry), not let
# the exception propagate and abort the whole batch.


def test_corrupt_pdf_returns_error_status_not_exception(tmp_path):
    pdf = tmp_path / "corrupt.pdf"
    pdf.write_bytes(b"%PDF-1.4\nthis is not a real pdf body")  # unparseable

    result = normalize_pdf(pdf)  # must NOT raise

    assert isinstance(result, NormalizeResult)
    assert result.status == NormalizeStatus.ERROR
    assert result.path == pdf
    assert result.original_path is None
    assert result.note  # a clear reason (the parse error)


def test_html_saved_as_pdf_returns_error(tmp_path):
    pdf = tmp_path / "page.pdf"
    pdf.write_bytes(b"<!DOCTYPE html><html><body>403 Forbidden</body></html>")

    result = normalize_pdf(pdf)

    assert result.status == NormalizeStatus.ERROR


def test_empty_file_returns_error(tmp_path):
    pdf = tmp_path / "empty.pdf"
    pdf.write_bytes(b"")

    result = normalize_pdf(pdf)

    assert result.status == NormalizeStatus.ERROR


def test_status_set_includes_error():
    assert {s.value for s in NormalizeStatus} == {
        "already_extractable",
        "normalized",
        "locked",
        "error",
    }


# -- AES owner-restricted -> normalized (crypto backend) ---------------------


def test_aes_owner_restricted_is_normalized(tmp_path):
    pdf = tmp_path / "aes.pdf"
    try:
        pdf.write_bytes(_owner_restricted(_make_text_pdf(), algorithm="AES-256"))
    except Exception as exc:  # pragma: no cover - only if crypto backend missing
        pytest.skip(f"AES encryption unavailable in this env: {exc}")

    assert PdfReader(str(pdf)).is_encrypted

    result = normalize_pdf(pdf)

    assert result.status == NormalizeStatus.NORMALIZED
    assert PdfReader(str(pdf)).is_encrypted is False
    assert MARKER in _extract(pdf)


# -- robustness --------------------------------------------------------------


def test_missing_file_raises(tmp_path):
    with pytest.raises((FileNotFoundError, OSError)):
        normalize_pdf(tmp_path / "does-not-exist.pdf")
