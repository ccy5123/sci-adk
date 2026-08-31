"""
The conclusion DECLARATION list (design/reader-facing-prose.md §11.3).

The problem it solves. A paper is an ARGUMENT addressed to a skeptical peer, and what is
SUBMITTED is the ``.tex`` SOURCE -- read by reviewers, editors, co-authors on Overleaf, and
publisher typesetting. So the manuscript may carry no opaque shorthand a reviewer would not
recognize (the standing constraint that resolved OD-7,
design/paper-writing-enforcement.md §6a). That rules out binding a verdict with an
in-document macro. But a conclusion still must not drift away from the record.

OD-7's own reasoning generalizes: *the macro was only ever ONE way to bind a number to the
record*. The same is true of a verdict. So the binding moves OUT of the manuscript:

    hypothesis id | the status the author wrote to | the exact sentence that states it

The manuscript stays plain LaTeX. This file is never submitted. ``sci-adk verify`` runs two
checks over it, NEITHER of which reads meaning
(:mod:`sci_adk.render.declaration_checks`):

  1. the declared status is still what the record derives -- belief is NON-MONOTONE, so a
     revision makes the declaration false and must cost a REWRITE of the passage, not a
     silent re-wording;
  2. the quoted sentence still appears in the paper -- if the author edited it, the
     declaration has detached from the sentence it was made about, and must be re-made.

Check 2 is why the quote is stored rather than a line number: a line number survives an
edit, a quote does not. The machine still cannot judge whether a sentence overstates its
status (that is semantic; no LLM sits on the verdict path). It can only refuse to let a
declaration silently detach. The semantic question is escalated to an advisory reviewer
(design §11.4), never auto-decided.

NOT frozen. Unlike :class:`sci_adk.core.pubreqs.PubReqs` (a contract, frozen with a digest
so it cannot be relaxed after a failure), a declaration list is REVISED whenever the paper
is revised -- that is the point of check 2. It is a description of the current manuscript,
not a commitment about it.

It lives at ``runs/<id>/declarations.json`` -- beside ``spec.json`` and ``pubreqs.json``,
NOT inside the regenerated ``paper/`` directory, so ``render`` never clobbers it (the same
placement rule and reason as the publishing contract).

Reference: design/reader-facing-prose.md §11 (the architecture), §11.3 (this file),
design/paper-writing-enforcement.md §6a (the OD-7 clean-source constraint),
src/sci_adk/core/pubreqs.py (the sibling per-run side file).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from sci_adk.core.claim import ClaimStatus

# The manuscript a declaration's sentence is quoted from. Today the submitted paper is
# ``draft.tex``; design §11.1 reassigns that role to a separate artifact, and this field is
# what lets a declaration list follow the paper when it moves.
DEFAULT_DOCUMENT = "draft.tex"


class Declaration(BaseModel):
    """One conclusion the paper states, tied to the hypothesis and status it is written to.

    Attributes:
        hypothesis_id: the Spec hypothesis this conclusion answers. Its experiment Claim
            supplies the recorded status that check 1 compares against.
        status: the status the author wrote the sentence to. Compared to the record; a
            mismatch is a HARD failure naming the passage to rewrite.
        sentence: the conclusion sentence, copied VERBATIM from the manuscript. Matched
            against the document with whitespace normalized (LaTeX line-wraps freely), so
            the copy need not preserve line breaks -- but it must otherwise be exact,
            including any ``\\cite``/``\\ref`` commands inside it.
        note: optional free text for the author's own use; never checked, never gated.
    """

    model_config = {"extra": "forbid"}

    hypothesis_id: str = Field(description="the Spec hypothesis this conclusion answers")
    status: ClaimStatus = Field(description="the status the sentence is written to")
    sentence: str = Field(min_length=1, description="the conclusion sentence, verbatim")
    note: Optional[str] = Field(default=None, description="author note; never checked")


class Declarations(BaseModel):
    """The per-run declaration list (``runs/<id>/declarations.json``).

    Attributes:
        spec_id: the run's Spec id (ties the list to the run, like ``PubReqs.spec_id``).
        document: the manuscript file the sentences are quoted from, relative to
            ``paper/``. Defaults to ``draft.tex``.
        declarations: one entry per conclusion the paper states.
    """

    model_config = {"extra": "forbid"}

    spec_id: str = Field(description="the run's Spec id")
    document: str = Field(default=DEFAULT_DOCUMENT, description="manuscript file")
    declarations: List[Declaration] = Field(default_factory=list)

    @property
    def declared_hypotheses(self) -> set[str]:
        """The hypothesis ids this list makes a claim about."""
        return {d.hypothesis_id for d in self.declarations}


def load_declarations(run_dir: Path) -> Optional[Declarations]:
    """Read ``runs/<id>/declarations.json``, or ``None`` when the run declares nothing.

    PURE-ish (one read, no writes). An ABSENT file means the run has not adopted the
    mechanism: every gate over it is then vacuously clean, so no existing run is
    retro-broken (the same backward-compatibility posture as an absent ``pubreqs.json``).

    Raises:
        ValueError: the file exists but is not valid JSON / does not validate. A malformed
            declaration list is a loud failure, never a silent skip -- a run that HAS the
            file has adopted the mechanism, and quietly ignoring it would be the vacuous
            pass the paper-gate work (OD-1) was built to remove.
    """
    path = run_dir / "declarations.json"
    if not path.is_file():
        return None
    try:
        return Declarations.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001 -- re-raised with the actionable path
        raise ValueError(
            f"{path} exists but is not a readable declaration list: {exc}"
        ) from exc


__all__ = ["DEFAULT_DOCUMENT", "Declaration", "Declarations", "load_declarations"]
