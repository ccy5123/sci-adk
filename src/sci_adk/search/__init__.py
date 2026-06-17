"""
sci-adk search / academic acquisition.

Currently exposes the paperforge adapter (DOI -> Open Access PDF acquisition)
and PDF normalization (making owner-permission-restricted acquired papers
extractable). Academic *discovery* (arXiv / Semantic Scholar / CrossRef MCP
glue) lands here too; discovery finds DOIs, paperforge acquires the full-text
PDFs, normalization makes restricted ones readable.
"""

from sci_adk.search.paperforge_adapter import (
    PINNED_SHA,
    AcquisitionRecord,
    AcquisitionResult,
    PaperforgeAdapter,
    PaperforgeNotInstalled,
)
from sci_adk.search.pdf_normalize import (
    NormalizeResult,
    NormalizeStatus,
    normalize_pdf,
)

__all__ = [
    "AcquisitionRecord",
    "AcquisitionResult",
    "PaperforgeAdapter",
    "PaperforgeNotInstalled",
    "PINNED_SHA",
    "NormalizeResult",
    "NormalizeStatus",
    "normalize_pdf",
]
