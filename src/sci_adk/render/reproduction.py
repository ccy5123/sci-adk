"""
Reproduction bundle renderers (F3, design/paper-publishing-requirements.md §3).

F3 retains the GENERATING CODE with the paper in two complementary forms, BOTH
derived from the record's ``provenance.code_ref`` (evidence.py:161):

  - an SI "Reproduction code" section -- the code listed for the reader (a resolvable
    co-located script is INLINED as a LaTeX ``lstlisting``; a bare commit/ref is recorded
    as a POINTER line, honestly, because no body is held);
  - ``paper/reproduce.py`` -- a thin DRIVER that re-runs the resolvable scripts through
    the existing docker executor so a reader runs ``python paper/reproduce.py`` on the
    spot. Pointer-only refs are DOCUMENTED (the commit to check out), never fabricated.

This module is PURE (data in, string out): it imports nothing from ``loop``/``runner``
and never touches the filesystem -- the COMPILER (``loop/compiler.py``, the sole
filesystem toucher) resolves each ``code_ref`` -> ``(script body | pointer)``, builds the
:class:`ReproListing` list, lands ``paper/code/`` + ``paper/reproduce.py``, and feeds the
resolved listings to these renderers and to :func:`sci_adk.render.si.render_si_latex`.
The code listing lives in the SI (the exempt record dump), NEVER in the tool-agnostic
``draft.tex`` (design/paper-publishing-requirements.md §0).

Determinism: same inputs -> byte-identical strings. An empty listing list -> ``""`` (the
SI emits no "Reproduction code" section and no ``listings`` package, and no ``paper/code/``
or ``reproduce.py`` is written) -- the F3 backward-compatibility / regression invariant.

Reference: design/paper-publishing-requirements.md (F3 §3), design/abstractions.md
(Provenance / code_ref), design/directory-structure.md (render/, runner/).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from sci_adk.render.paper import _latex_sanitize

# The LaTeX listings environment cannot verbatim-hold a body that itself contains the
# closing delimiter. A script whose source text contains this sequence is recorded as a
# POINTER instead of inlined, so the SI is never a broken document (honest: we hold the
# bytes, but cannot safely typeset them inline; the runnable bundle still carries them).
_LSTLISTING_END = r"\end{lstlisting}"


@dataclass(frozen=True)
class ReproListing:
    """One Evidence item's reproduction entry, as resolved by the compiler.

    The compiler resolves ``provenance.code_ref`` (evidence.py:161) to exactly one of:
      - ``kind="script"`` -- ``code_ref`` pointed at an existing readable co-located
        file; ``text`` holds its body (inlined in the SI, copied into ``paper/code/``,
        re-run by ``reproduce.py``) and ``filename`` is its co-located ``paper/code/``
        basename.
      - ``kind="pointer"`` -- a bare commit/ref (e.g. a 40-hex git hash) with no
        resolvable file; ``text``/``filename`` are ``None`` (a POINTER -- the SI records
        the ref, ``reproduce.py`` documents the commit; NOTHING is fabricated).

    Frozen + deterministic: the renderers below take a sequence of these and emit
    byte-stable strings.
    """

    evidence_id: str
    code_ref: str
    kind: str  # "script" | "pointer"
    text: Optional[str] = None       # script body (kind=="script") else None
    filename: Optional[str] = None   # paper/code/<filename> (kind=="script") else None

    @property
    def is_script(self) -> bool:
        return self.kind == "script" and self.text is not None


def listing_inlinable(text: str) -> bool:
    """Whether a resolved script body can be SAFELY inlined as an ``lstlisting``.

    ``listings`` typesets its body verbatim, but cannot hold a body that itself contains
    the closing ``\\end{lstlisting}`` delimiter. Such a body is recorded as a POINTER by
    the compiler instead of inlined, so the SI never compiles to a broken document. Pure
    + deterministic.
    """
    return _LSTLISTING_END not in text


def reproduction_uses_listings(listings: Optional[Sequence[ReproListing]]) -> bool:
    """Whether the SI preamble must add ``\\usepackage{listings}`` for these entries.

    True iff at least one entry is an inlinable script (only then is an ``lstlisting``
    emitted). A pointer-only (or empty/``None``) set needs no ``listings`` package, so the
    SI preamble stays byte-identical to today -- the same per-kind guarding the SI already
    uses for ``pgfplots``/``graphicx`` (design/paper-publishing-requirements.md F2/F3).
    """
    return any(item.is_script for item in (listings or []))


def render_reproduction_section(
    listings: Optional[Sequence[ReproListing]],
) -> str:
    """Render the SI "Reproduction code" section body (or ``""`` when there is nothing).

    For each entry, in the GIVEN order (deterministic):
      - a ``script`` entry inlines its body inside an ``lstlisting`` (verbatim; the body
        is NOT LaTeX-escaped -- ``listings`` handles raw code), under a sanitized caption
        naming the evidence id + the co-located ``paper/code/<filename>``;
      - a ``pointer`` entry emits one honest POINTER line recording the ``code_ref`` (the
        commit/ref to check out) -- no body is fabricated.

    An empty or ``None`` list returns ``""`` so the SI emits NO section (the F3
    regression invariant: a run with no ``code_ref`` is byte-identical to today). PURE
    + deterministic.
    """
    items = list(listings or [])
    if not items:
        return ""

    lines: List[str] = [r"\section{Reproduction code}"]
    lines.append(
        "The generating code recorded with each Evidence item, retained for "
        "reproduction. Resolvable scripts are co-located under "
        r"\texttt{paper/code/} and re-runnable via \texttt{python paper/reproduce.py}; "
        "a bare commit reference is recorded as a pointer (the body is not held)."
    )
    lines.append("")
    for item in items:
        if item.is_script:
            fname = item.filename or f"{item.evidence_id}.py"
            caption = _latex_sanitize(
                f"{item.evidence_id} -- code_ref {item.code_ref} "
                f"(paper/code/{fname})"
            )
            lines.append(r"\begin{lstlisting}[basicstyle=\ttfamily\small,"
                         f"caption={{{caption}}},breaklines=true]")
            # Body is verbatim -- listings handles raw code; NEVER _latex_sanitize here
            # (that would corrupt the source). The compiler guarantees the body has no
            # \\end{lstlisting} (else it recorded a pointer), so this cannot break.
            lines.append(item.text or "")
            lines.append(r"\end{lstlisting}")
            lines.append("")
        else:
            lines.append(
                r"\noindent\textbf{Pointer:} \texttt{"
                f"{_latex_sanitize(item.evidence_id)}"
                r"} -- code\_ref \texttt{"
                f"{_latex_sanitize(item.code_ref)}"
                r"} (a recorded reference; no co-located script body is held). "
                r"\\"
            )
            lines.append("")
    return "\n".join(lines).rstrip("\n")


def render_reproduce_driver(
    listings: Optional[Sequence[ReproListing]],
    spec_id: str,
) -> str:
    """Render the ``paper/reproduce.py`` driver text (or a documenting stub).

    The driver re-runs the resolvable co-located scripts through the EXISTING execution
    path -- :meth:`sci_adk.runner.docker_executor.DockerExecutor.execute_python` -- so a
    reader runs ``python paper/reproduce.py`` on the spot to regenerate results. It
    re-executes only from the RECORD (the scripts co-located from each resolvable
    ``code_ref``); a pointer-only ``code_ref`` is DOCUMENTED as a commit to check out,
    never fabricated and never executed.

    Generated content references ONLY real recorded refs (the given ``code_ref`` values).
    An all-pointer run (no resolvable script -- e.g. a run whose ``code_ref``s
    are bare git hashes) produces a driver that can only DOCUMENT the commits; it cannot
    re-execute, and says so plainly. PURE + deterministic.
    """
    items = list(listings or [])
    scripts = [it for it in items if it.is_script]
    pointers = [it for it in items if not it.is_script]

    lines: List[str] = []
    lines.append('"""')
    lines.append(
        f"reproduce.py -- re-run the recorded generating code for run {spec_id}."
    )
    lines.append("")
    lines.append(
        "Auto-emitted by sci-adk (design/paper-publishing-requirements.md F3). Re-runs"
    )
    lines.append(
        "each resolvable co-located script under paper/code/ through the same docker"
    )
    lines.append(
        "executor sci-adk used, regenerating the recorded results FROM THE RECORD. Bare"
    )
    lines.append(
        "commit references are documented (the commit to check out), never fabricated."
    )
    lines.append('"""')
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from pathlib import Path")
    lines.append("")
    lines.append("from sci_adk.runner.docker_executor import DockerExecutor")
    lines.append("")
    lines.append("# Resolvable scripts co-located from each Evidence item's code_ref.")
    lines.append("# (evidence_id, code_ref, paper/code/ filename)")
    lines.append("SCRIPTS = [")
    for it in scripts:
        lines.append(
            "    ("
            f"{_py_str(it.evidence_id)}, "
            f"{_py_str(it.code_ref)}, "
            f"{_py_str(it.filename or '')}"
            "),"
        )
    lines.append("]")
    lines.append("")
    lines.append("# Pointer-only references (a recorded commit/ref, no co-located")
    lines.append("# script body): documented for manual checkout, NOT executed.")
    lines.append("POINTERS = [")
    for it in pointers:
        lines.append(
            "    ("
            f"{_py_str(it.evidence_id)}, "
            f"{_py_str(it.code_ref)}"
            "),"
        )
    lines.append("]")
    lines.append("")
    lines.append("")
    lines.append("def main() -> int:")
    lines.append("    here = Path(__file__).resolve().parent")
    lines.append("    executor = DockerExecutor(workspace_dir=here / \"code\")")
    lines.append("    failures = 0")
    lines.append("    for evidence_id, code_ref, filename in SCRIPTS:")
    lines.append("        script_path = here / \"code\" / filename")
    lines.append("        print(f\"[reproduce] {evidence_id}: running {filename} \"")
    lines.append("              f\"(code_ref={code_ref})\")")
    lines.append("        body = script_path.read_text(encoding=\"utf-8\")")
    lines.append("        result = executor.execute_python(body)")
    lines.append("        if not result.get(\"success\"):")
    lines.append("            failures += 1")
    lines.append("            print(f\"[reproduce] {evidence_id}: FAILED \"")
    lines.append("                  f\"(returncode={result.get('returncode')})\")")
    lines.append("    for evidence_id, code_ref in POINTERS:")
    lines.append("        print(f\"[reproduce] {evidence_id}: pointer only -- check out \"")
    lines.append("              f\"commit/ref {code_ref} to obtain the generating code \"")
    lines.append("              f\"(no co-located script; not executed).\")")
    lines.append("    if not SCRIPTS and POINTERS:")
    lines.append("        print(\"[reproduce] no co-located scripts: this run records \"")
    lines.append("              \"only commit pointers; check out the refs above to \"")
    lines.append("              \"reproduce. Nothing was executed.\")")
    lines.append("    return 1 if failures else 0")
    lines.append("")
    lines.append("")
    lines.append("if __name__ == \"__main__\":")
    lines.append("    raise SystemExit(main())")
    lines.append("")
    return "\n".join(lines)


def _py_str(s: str) -> str:
    """A safe Python string literal for the generated driver (deterministic)."""
    return repr(s)


__all__ = [
    "ReproListing",
    "listing_inlinable",
    "reproduction_uses_listings",
    "render_reproduction_section",
    "render_reproduce_driver",
]
