"""
Normalize permission-restricted PDFs so acquired Open-Access papers are readable.

Acquired OA paper PDFs are sometimes *owner-password ("permission") restricted*:
they OPEN fine, but text extraction / copying is disabled. Downstream reading
(the agent's literature review) then fails -- and environments often lack a PDF
library. This module re-writes such a PDF without its restrictions so its text
becomes extractable, while recording (honestly) that the transformation happened.

ETHICS BOUNDARY -- HARD (do not exceed):

  * Normalize ONLY owner/permission-restricted PDFs that ALREADY OPEN -- i.e. a
    PDF that is encrypted but decrypts with an EMPTY user password. Removing
    owner/permission restrictions on a document you legitimately possess, for
    your own text extraction, is the legitimate case (OA research papers). The
    file already opens without a password; we only strip the copy/extract lock.

  * NEVER crack a USER password. A PDF that will not even open without a password
    (decrypting with the empty password grants no access) is access-controlled.
    We do NOT attempt to bypass it: we return a "locked" status, leave the file
    byte-for-byte unmodified, and surface it (the user must supply the password
    or use another source). No non-empty password is ever tried.

  * When the legitimate-vs-circumvention boundary is ambiguous, default to the
    conservative side: do not modify, return "locked", report the reason.

The discriminator is pypdf's ``PdfReader.decrypt("")`` return value:
  - ``USER_PASSWORD`` / ``OWNER_PASSWORD`` -> the empty password opened the file
    -> it is already openable -> safe to re-write without encryption.
  - ``NOT_DECRYPTED``                      -> the empty password did NOT open it
    -> a real user-password lock -> ``locked``; never bypassed.

This module is acquisition/IO only. It does not touch the evidence-validity gate
(core/validity.py), claim updating, or data_source/referent semantics, and it
uses no LLM. Reference: src/sci_adk/loop/literature_acquirer.py (caller),
design/literature-acquisition.md, design/tool-policy.md.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from pypdf import PdfReader, PdfWriter, PasswordType
from pypdf.errors import PyPdfError

# The on-disk suffix a preserved original gets, alongside the normalized file
# (``paper.pdf`` -> ``paper.orig.pdf``). Kept simple and adjacent so the record
# of "what we transformed" sits next to the result.
_ORIG_SUFFIX = ".orig.pdf"


class NormalizeStatus(str, Enum):
    """
    Outcome of :func:`normalize_pdf`.

    Attributes:
        already_extractable: not encrypted -- nothing to do, text already extracts.
        normalized: was owner/permission-restricted (opens with empty user
            password); re-written without restrictions -> now extractable.
        locked: a real user-password lock; left unmodified and NOT cracked.
        error: the file could not be PARSED (truncated download, an HTML error
            page saved as .pdf, corrupt bytes); left unmodified. The caller
            (literature_acquirer) drives a re-download retry before giving up.
    """

    ALREADY_EXTRACTABLE = "already_extractable"
    NORMALIZED = "normalized"
    LOCKED = "locked"
    ERROR = "error"


class NormalizeResult(BaseModel):
    """
    The result of normalizing one PDF (Pydantic v2; frozen -- a record).

    Attributes:
        path: the PDF that was inspected (the normalized file, in place, when the
            status is ``normalized``).
        status: ``already_extractable`` | ``normalized`` | ``locked``.
        original_path: where the untouched original was preserved, when a copy
            was kept (only for ``normalized`` with ``keep_original=True``).
        note: a short, honest description of what happened / why.
    """

    model_config = {"frozen": True}

    path: Path = Field(..., description="The PDF inspected (normalized in place if rewritten)")
    status: NormalizeStatus = Field(..., description="Normalization outcome")
    original_path: Optional[Path] = Field(
        default=None, description="Preserved original, if a copy was kept"
    )
    note: str = Field(default="", description="Short honest description of the outcome")


def normalize_pdf(path: Path | str, *, keep_original: bool = True) -> NormalizeResult:
    """
    Make ``path`` text-extractable when it is an owner-restricted-but-openable PDF.

    Behavior (see the module ETHICS BOUNDARY):
      * not encrypted -> no-op, ``already_extractable`` (the file is untouched).
      * encrypted, opens with an empty user password (owner/permission
        restricted) -> re-write decrypted, WITHOUT encryption, into place ->
        ``normalized``; the original is preserved when ``keep_original`` is True.
      * encrypted, does NOT open with an empty user password (real user lock) ->
        ``locked``; the file is left byte-for-byte unmodified and NEVER cracked.
      * cannot be parsed (truncated/corrupt bytes, an HTML error page saved as
        .pdf) -> ``error``; the file is left unmodified and the parse error is
        returned (not raised), so a caller can re-download and retry.

    Args:
        path: the PDF to normalize (modified in place only for ``normalized``).
        keep_original: when True (default), preserve the pre-normalization file
            alongside as ``<name>.orig.pdf`` before re-writing it.

    Returns:
        A :class:`NormalizeResult` recording the outcome. A parse failure yields
        an ``error``-status result rather than propagating an exception.

    Raises:
        FileNotFoundError: if ``path`` does not exist (a missing file is a
            programming error, not a corrupt download).
    """
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    original_path: Optional[Path] = None
    try:
        reader = PdfReader(str(pdf_path))

        # Case 1: not encrypted -> already extractable, nothing to do.
        if not reader.is_encrypted:
            return NormalizeResult(
                path=pdf_path,
                status=NormalizeStatus.ALREADY_EXTRACTABLE,
                note="PDF is not encrypted; already extractable (no-op).",
            )

        # Try the EMPTY user password ONLY. This is the whole ethics test: an
        # empty password either opens the file (legitimate -> normalize) or it
        # does not (real user lock -> stop). We never try a non-empty password.
        password_type = reader.decrypt("")

        # Case 3: empty password did not grant access -> real user-password lock.
        # ETHICS: do not modify, do not crack, surface it. This is a deliberate
        # outcome, NOT a parse error -- returned before any rewrite.
        if password_type == PasswordType.NOT_DECRYPTED:
            return NormalizeResult(
                path=pdf_path,
                status=NormalizeStatus.LOCKED,
                note=(
                    "PDF requires a user password to open (empty password "
                    "rejected); left unmodified and NOT bypassed. Supply the "
                    "password or use another source."
                ),
            )

        # Case 2: empty password opened it (USER_PASSWORD or OWNER_PASSWORD) ->
        # the document is already openable; strip restrictions by re-writing it
        # without encryption so its text extracts.
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        # Carry over document metadata when present (best-effort; absence is fine).
        if reader.metadata is not None:
            writer.add_metadata(reader.metadata)

        # Write to a temp sibling first, then atomically replace -- so the
        # original on disk is never touched until a full, successful rewrite.
        # If anything above raised, we never reach here and the file is intact.
        tmp_path = pdf_path.with_suffix(".normtmp.pdf")
        with open(tmp_path, "wb") as fh:  # WITHOUT encrypt() -> no restriction
            writer.write(fh)

        if keep_original:
            original_path = pdf_path.with_suffix(_ORIG_SUFFIX)
            original_path.write_bytes(pdf_path.read_bytes())
        tmp_path.replace(pdf_path)
    except (PyPdfError, OSError, ValueError) as exc:
        # Case 4: the file could not be parsed/rewritten (truncated download,
        # HTML error page saved as .pdf, corrupt bytes). Return an error result
        # instead of propagating, so the acquirer can re-download and retry --
        # one bad file must not abort the whole batch. PyPdfError covers pypdf's
        # read errors (PdfStreamError/EmptyFileError/...), OSError covers IO, and
        # ValueError covers malformed-structure parses pypdf raises outside its
        # own hierarchy. The original file is left unmodified (we replace only
        # after a full write); clean up temp/backup artifacts so nothing stale
        # is left behind.
        for artifact in (
            pdf_path.with_suffix(".normtmp.pdf"),
            pdf_path.with_suffix(_ORIG_SUFFIX),
        ):
            if artifact.exists():
                artifact.unlink()
        return NormalizeResult(
            path=pdf_path,
            status=NormalizeStatus.ERROR,
            note=f"PDF could not be parsed ({type(exc).__name__}: {exc}).",
        )

    return NormalizeResult(
        path=pdf_path,
        status=NormalizeStatus.NORMALIZED,
        original_path=original_path,
        note=(
            "Owner/permission-restricted PDF (opens with empty user password); "
            "re-written without restrictions -> text now extractable."
        ),
    )


__all__ = ["NormalizeStatus", "NormalizeResult", "normalize_pdf"]
