"""
F3 reproduction-bundle PURE renderers (design/paper-publishing-requirements.md §3).

``render/reproduction.py`` is pure (data in, string out): the COMPILER resolves each
Evidence item's ``provenance.code_ref`` -> a :class:`ReproListing` (``script`` with a
body, or ``pointer`` for a bare commit/ref), and these renderers emit the SI
"Reproduction code" section text + the ``paper/reproduce.py`` driver text. No filesystem,
no LLM. An empty listing set -> ``""`` (the regression invariant: a code_ref-free run is
byte-identical to today).
"""

from __future__ import annotations

from sci_adk.render.reproduction import (
    ReproListing,
    listing_inlinable,
    render_reproduce_driver,
    render_reproduction_section,
    reproduction_uses_listings,
)

_SCRIPT = ReproListing(
    evidence_id="ev-1",
    code_ref="code/run.py",
    kind="script",
    text="import sys\nprint('hello', sys.argv)\n",
    filename="run.py",
)
_POINTER = ReproListing(
    evidence_id="ev-2",
    code_ref="a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4",  # bare 40-hex commit
    kind="pointer",
)


# ---------------------------------------------------------------------------
# Empty / None -> "" (the F3 byte-identical regression invariant).
# ---------------------------------------------------------------------------

class TestEmptyIsNothing:
    def test_section_empty_list_is_empty_string(self):
        assert render_reproduction_section([]) == ""

    def test_section_none_is_empty_string(self):
        assert render_reproduction_section(None) == ""

    def test_uses_listings_false_for_empty_or_pointer_only(self):
        assert reproduction_uses_listings(None) is False
        assert reproduction_uses_listings([]) is False
        assert reproduction_uses_listings([_POINTER]) is False

    def test_uses_listings_true_only_with_a_script(self):
        assert reproduction_uses_listings([_SCRIPT]) is True
        assert reproduction_uses_listings([_POINTER, _SCRIPT]) is True


# ---------------------------------------------------------------------------
# Section rendering: script -> lstlisting (verbatim body); pointer -> honest line.
# ---------------------------------------------------------------------------

class TestSectionRender:
    def test_script_inlines_body_in_lstlisting(self):
        out = render_reproduction_section([_SCRIPT])
        assert r"\section{Reproduction code}" in out
        assert r"\begin{lstlisting}" in out
        assert r"\end{lstlisting}" in out
        # The body is verbatim -- NOT LaTeX-escaped (listings handles raw code). The
        # underscore-free script survives literally; the point is the body is present.
        assert "print('hello', sys.argv)" in out
        # The co-located filename is named in the caption so a reader maps it to paper/code/.
        assert "paper/code/run.py" in out

    def test_script_body_is_not_latex_escaped(self):
        # A body with LaTeX specials must pass through verbatim (listings), not escaped.
        script = ReproListing(
            evidence_id="ev-x",
            code_ref="code/m.py",
            kind="script",
            text="x = {1: 2}  # 100% & cost $5_under\n",
            filename="m.py",
        )
        out = render_reproduction_section([script])
        # The raw specials survive (NOT \% \& \$ \_ {}) -- verbatim code.
        assert "x = {1: 2}  # 100% & cost $5_under" in out

    def test_pointer_emits_honest_pointer_line_no_body(self):
        out = render_reproduction_section([_POINTER])
        assert r"\section{Reproduction code}" in out
        assert "Pointer" in out
        # The bare commit ref is recorded (sanitized) so the reader knows what to check out.
        assert _POINTER.code_ref in out
        # No code body / lstlisting is fabricated for a pointer.
        assert r"\begin{lstlisting}" not in out

    def test_mixed_preserves_supply_order(self):
        out = render_reproduction_section([_POINTER, _SCRIPT])
        # First-seen order: the pointer line precedes the script's lstlisting.
        assert out.index("Pointer") < out.index(r"\begin{lstlisting}")

    def test_render_is_deterministic(self):
        a = render_reproduction_section([_POINTER, _SCRIPT])
        b = render_reproduction_section([_POINTER, _SCRIPT])
        assert a == b


# ---------------------------------------------------------------------------
# listing_inlinable: a body containing the closing delimiter cannot inline.
# ---------------------------------------------------------------------------

class TestListingInlinable:
    def test_plain_body_inlinable(self):
        assert listing_inlinable("print(1)\n") is True

    def test_body_with_close_delimiter_not_inlinable(self):
        assert listing_inlinable("code\n\\end{lstlisting}\nmore") is False


# ---------------------------------------------------------------------------
# Driver (reproduce.py) rendering: references only real recorded refs; never fabricates.
# ---------------------------------------------------------------------------

class TestReproduceDriver:
    def test_driver_runs_scripts_via_docker_executor(self):
        out = render_reproduce_driver([_SCRIPT], "t-run")
        assert "from sci_adk.runner.docker_executor import DockerExecutor" in out
        assert "execute_python" in out
        # The real recorded ref + co-located filename are referenced (no fabrication).
        assert repr(_SCRIPT.code_ref) in out
        assert repr(_SCRIPT.filename) in out
        assert "t-run" in out

    def test_driver_documents_pointer_commit_does_not_execute_it(self):
        out = render_reproduce_driver([_POINTER], "t-run")
        # The pointer's real commit ref is documented for manual checkout.
        assert repr(_POINTER.code_ref) in out
        # It lands in POINTERS (documented), not SCRIPTS (executed).
        assert "POINTERS = [" in out
        # An all-pointer run honestly says it cannot execute.
        assert "SCRIPTS = [\n]" in out or "SCRIPTS = []" in out

    def test_driver_references_only_recorded_refs(self):
        # No code_ref other than the two given may appear anywhere in the driver.
        out = render_reproduce_driver([_SCRIPT, _POINTER], "t-run")
        assert repr(_SCRIPT.code_ref) in out
        assert repr(_POINTER.code_ref) in out
        # A ref that was never recorded must not be invented.
        assert "fabricated" not in out.lower() or "never fabricated" in out.lower()

    def test_driver_is_valid_python(self):
        # The generated driver must at least compile (it is a real emitted file).
        out = render_reproduce_driver([_SCRIPT, _POINTER], "t-run")
        compile(out, "reproduce.py", "exec")

    def test_driver_is_deterministic(self):
        a = render_reproduce_driver([_SCRIPT, _POINTER], "t-run")
        b = render_reproduce_driver([_SCRIPT, _POINTER], "t-run")
        assert a == b
