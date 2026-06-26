"""
Capability registry + ``--capability`` selector (RED-first).

design/rigor-shell-architecture.md §3.2 (F3): the adapter holds a registry of
``ExperimentFn`` providers keyed by a runtime ``capability id``. A runtime selector
(``--capability`` / adapter default) resolves the provider; the kernel sees only the
resolved ``ExperimentFn`` -- never the registry, the selector, or the domain (§3.2,
the kernel sees ``experiment: ExperimentFn`` at compiler.py:121).

T-1 is the FIRST registered capability under ``T1_CAPABILITY_ID`` (§3.3): it wraps
``t1_experiment`` / ``build_t1_spec`` / ``build_t1_demo_molecules``. Registration is
adapter-side (importing ``sci_adk.adapter.registry`` registers it); it does NOT make
the kernel import the adapter.

Anti method-shopping (§3.2 step 4, F3 strengthening): the resolved capability id is
recorded in ``EvidenceItem.provenance`` and each run appends its own append-only
``EvidenceItem`` (E1) -- it never overwrites.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sci_adk.adapter.registry import (
    CapabilityProvider,
    available,
    register,
    resolve,
)
from sci_adk.adapter.t1_capability import T1_CAPABILITY_ID
from sci_adk.adapter.t1_encoding import Molecule
from sci_adk.cli import main


class _PureExecutor:
    """Non-Docker executor seam (mirrors test_t1_adapter): the real verifier in-process."""

    image_name = "pure-inproc"

    def run_t1(self, molecules: list[Molecule]) -> dict:
        from sci_adk.adapter.t1_encoding import verify_injectivity

        stats = verify_injectivity(list(molecules))
        return {
            "success": True,
            "stats": stats,
            "provenance": {
                "image_name": self.image_name,
                "image_id": "inproc-0000",
                "commit_hash": "deadbeef",
            },
        }


class TestRegistryResolution:
    def test_t1_is_registered_under_its_id(self):
        # Importing the registry registers T-1; resolving its id yields a provider.
        provider = resolve(T1_CAPABILITY_ID)
        assert isinstance(provider, CapabilityProvider)
        assert provider.id == T1_CAPABILITY_ID

    def test_t1_id_is_in_available(self):
        assert T1_CAPABILITY_ID in available()

    def test_resolve_unknown_id_raises_valueerror_listing_available(self):
        with pytest.raises(ValueError) as exc:
            resolve("no-such-capability")
        msg = str(exc.value)
        # The error must name the bad id AND list what IS available (so the caller can
        # correct it without reading source).
        assert "no-such-capability" in msg
        assert T1_CAPABILITY_ID in msg

    def test_provider_produces_a_working_experiment_fn(self, tmp_path):
        provider = resolve(T1_CAPABILITY_ID)
        # The provider builds an ExperimentFn (Spec, Path) -> [EvidenceItem]. Inject the
        # pure executor + the demo molecules so no Docker is needed.
        spec = provider.demo_spec("reg-fn")
        molecules = provider.demo_options()["molecules"]
        fn = provider.experiment_fn(molecules=molecules, executor=_PureExecutor())
        evidence = fn(spec, tmp_path)
        assert len(evidence) == 1
        assert evidence[0].result.point == 0.0  # demo set is collision-free

    def test_demo_spec_carries_the_numeric_threshold_rule(self):
        provider = resolve(T1_CAPABILITY_ID)
        spec = provider.demo_spec("reg-spec")
        # The demo Spec is the real T-1 Spec: a numeric threshold rule (autonomous path).
        assert spec.hypotheses[0].decision_rule.kind.value == "threshold"


class TestRegistryRegistration:
    def test_register_then_resolve_roundtrips(self):
        sentinel = CapabilityProvider(
            id="test-only-cap",
            experiment_fn=lambda **_: (lambda s, w: []),
            demo_spec=None,
            demo_options=None,
        )
        register(sentinel)
        assert resolve("test-only-cap") is sentinel
        assert "test-only-cap" in available()

    def test_register_duplicate_id_raises(self):
        # Registering a second provider under T-1's id would silently shadow it -- refuse.
        dup = CapabilityProvider(
            id=T1_CAPABILITY_ID,
            experiment_fn=lambda **_: (lambda s, w: []),
            demo_spec=None,
            demo_options=None,
        )
        with pytest.raises(ValueError):
            register(dup)


class TestCliCapabilitySelector:
    """``--capability <id>`` resolves the provider; ``--t1-demo`` stays an alias."""

    @pytest.mark.integration
    def test_capability_t1_demo_mode_runs_and_supports(self, tmp_path, capsys):
        # No proposal + --capability t1-molecular-godel => the provider's demo Spec +
        # demo molecules drive an autonomous SUPPORTED verdict (the real container path).
        # Skip if Docker is unavailable: the CLI demo path uses the default Docker executor.
        import shutil

        if shutil.which("docker") is None:
            pytest.skip("docker CLI not available; CLI demo path uses Docker executor")
        # --no-strict-science: this is a CAPABILITY-SELECTION plumbing test, not a science
        # rigor test. The bare t1 demo carries no falsifying negative control, so a strict
        # run (the default) would correctly HALT it (design/science-guards.md G3); run lenient
        # to exercise the selector path. Strict enforcement is covered in test_science_guards.
        rc = main(["run", "--capability", T1_CAPABILITY_ID, "-o", str(tmp_path),
                   "--spec-id", "cap-demo", "--no-strict-science"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "compiled Spec 'cap-demo'" in out

    @pytest.mark.integration
    def test_t1_demo_alias_still_works(self, tmp_path, capsys):
        # Regression: the legacy --t1-demo flag must keep working as an alias for
        # --capability t1-molecular-godel (demo mode). No breakage.
        import shutil

        if shutil.which("docker") is None:
            pytest.skip("docker CLI not available; --t1-demo path uses Docker executor")
        # --no-strict-science: plumbing (alias) test -- run lenient (see the sibling test).
        rc = main(["run", "--t1-demo", "-o", str(tmp_path), "--spec-id", "alias-demo",
                   "--no-strict-science"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "compiled Spec 'alias-demo'" in out

    def test_unknown_capability_friendly_error(self, tmp_path, capsys):
        # An unknown --capability id must produce a friendly stderr message (naming the
        # bad id) and a nonzero exit -- never a raw traceback.
        rc = main(["run", "--capability", "bogus-cap", "-o", str(tmp_path)])
        captured = capsys.readouterr()
        assert rc != 0
        assert "bogus-cap" in captured.err
        assert "Traceback (most recent call last)" not in captured.err

    def test_t1_demo_and_capability_conflict_is_rejected(self, tmp_path, capsys):
        # --t1-demo IS --capability t1-molecular-godel; passing both an explicit
        # --capability and --t1-demo is contradictory -> reject with a clear error
        # rather than silently picking one.
        rc = main(["run", "--t1-demo", "--capability", "some-other", "-o", str(tmp_path)])
        captured = capsys.readouterr()
        assert rc != 0
        assert captured.err  # a message, not a traceback
        assert "Traceback (most recent call last)" not in captured.err

    def test_proposal_plus_capability_is_rejected_not_silently_demoed(
        self, tmp_path, capsys
    ):
        # Minimal scope: a capability runs its built-in DEMO (no proposal). Combining a
        # proposal with --capability must NOT silently feed demo molecules to the
        # proposal's Spec -- it is rejected with a clear message (proposal-driven
        # experiment authoring is the unbuilt agent-authored path, design §3.2).
        proposal = tmp_path / "p.md"
        proposal.write_text(
            "# Background\nb\n# Goal\ng\n# Expected Output\no\n# Method\nm\n",
            encoding="utf-8",
        )
        rc = main(["run", str(proposal), "--capability", T1_CAPABILITY_ID,
                   "-o", str(tmp_path)])
        captured = capsys.readouterr()
        assert rc != 0
        assert "not implemented" in captured.err or "cannot be combined" in captured.err
        assert "Traceback (most recent call last)" not in captured.err


class TestCapabilityProvenanceAppendOnly:
    """The resolved capability id is recorded in provenance; runs append (E1)."""

    def test_capability_id_recorded_in_evidence_provenance(self, tmp_path):
        provider = resolve(T1_CAPABILITY_ID)
        spec = provider.demo_spec("prov-cap")
        molecules = provider.demo_options()["molecules"]
        fn = provider.experiment_fn(molecules=molecules, executor=_PureExecutor())
        evidence = fn(spec, tmp_path)
        ev = evidence[0]
        # The capability id travels in provenance.environment (E3) AND the finding JSON.
        assert T1_CAPABILITY_ID in (ev.provenance.environment or "")
        finding = json.loads(ev.result.finding)
        assert finding["capability"] == T1_CAPABILITY_ID

    def test_repeated_runs_append_evidence_not_overwrite(self, tmp_path):
        # Two runs over the same Spec must leave TWO EvidenceItems on disk (append-only,
        # E1) -- the structural anti-method-shopping guarantee. The experiment fn writes
        # one EvidenceItem per call into runs/<spec.id>/evidence/.
        provider = resolve(T1_CAPABILITY_ID)
        spec = provider.demo_spec("prov-append")
        molecules = provider.demo_options()["molecules"]
        fn = provider.experiment_fn(molecules=molecules, executor=_PureExecutor())

        fn(spec, tmp_path)
        fn(spec, tmp_path)

        ev_dir = tmp_path / "runs" / spec.id / "evidence"
        ev_files = list(ev_dir.glob("*.json"))
        assert len(ev_files) == 2, "second run must APPEND a new EvidenceItem, not overwrite"
        # Both carry the capability id.
        for f in ev_files:
            on_disk = json.loads(f.read_text(encoding="utf-8"))
            assert T1_CAPABILITY_ID in (on_disk["provenance"]["environment"] or "")
