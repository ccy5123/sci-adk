"""
sci-adk search / academic acquisition.

Currently exposes the paperforge adapter (DOI -> Open Access PDF acquisition).
Academic *discovery* (arXiv / Semantic Scholar / CrossRef MCP glue) lands here
too; discovery finds DOIs, paperforge acquires the full-text PDFs.
"""

from sci_adk.search.paperforge_adapter import (
    PINNED_SHA,
    AcquisitionRecord,
    AcquisitionResult,
    PaperforgeAdapter,
    PaperforgeNotInstalled,
)

__all__ = [
    "AcquisitionRecord",
    "AcquisitionResult",
    "PaperforgeAdapter",
    "PaperforgeNotInstalled",
    "PINNED_SHA",
]
