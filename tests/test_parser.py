"""
Tests for proposal parser.
"""

from pathlib import Path

from sci_adk.core.parser import ProposalParser, parse_proposal


class TestProposalParser:
    """Tests for 4-pane proposal parsing."""

    def test_parse_t1_proposal(self):
        """Test parsing T-1 proposal from fixture."""
        parser = ProposalParser()
        fixture_path = Path("tests/fixtures/t1_proposal.md")

        # Read fixture content
        proposal_text = fixture_path.read_text(encoding="utf-8")

        spec = parser.parse(proposal_text, spec_id="t1_proposal")

        # Verify Spec structure
        assert spec.id == "t1_proposal"
        assert spec.raw_proposal.background != ""
        assert "molecular graphs" in spec.raw_proposal.background.lower()

        # Verify hypotheses were derived
        assert len(spec.hypotheses) > 0
        assert any("encoding" in hyp.statement.lower() for hyp in spec.hypotheses)

        # Verify method plan was created
        assert spec.method is not None

        # Verify target claims were derived
        assert len(spec.target_claims) > 0
        assert any("algorithm" in claim.statement.lower() for claim in spec.target_claims)

    def test_parse_empty_sections(self):
        """Test parsing proposal with minimal content."""
        parser = ProposalParser()
        spec = parser.parse(
            """
            # Background
            Minimal background.

            # Goal
            Test goal.

            # Method
            Test method.

            # Expected Output
            Test output.
            """,
            spec_id="test-minimal"
        )

        assert spec.id == "test-minimal"
        assert spec.raw_proposal.background == "Minimal background."
        assert len(spec.hypotheses) >= 1  # Fallback hypothesis created

    def test_parse_string(self):
        """Test parsing from string."""
        parser = ProposalParser()
        spec = parser.parse(
            """
            # Background
            Research background.

            # Goal
            Test objective.

            # Method
            Test methodology.

            # Expected Output
            Test deliverable.
            """,
            spec_id="test-string"
        )

        assert spec.id == "test-string"
        assert len(spec.hypotheses) >= 1


class TestT1Specific:
    """Tests specific to T-1 proposal parsing."""

    def test_t1_has_encoding_hypothesis(self):
        """Test that T-1 proposal has encoding-related hypothesis."""
        parser = ProposalParser()
        fixture_path = Path("tests/fixtures/t1_proposal.md")
        proposal_text = fixture_path.read_text(encoding="utf-8")
        spec = parser.parse(proposal_text, spec_id="t1_proposal")

        # Should have hypothesis about molecular encoding
        encoding_hyps = [
            hyp for hyp in spec.hypotheses
            if "encoding" in hyp.statement.lower()
        ]
        assert len(encoding_hyps) > 0

    def test_t1_has_tool_approaches(self):
        """Test that T1 method has tool approaches."""
        parser = ProposalParser()
        fixture_path = Path("tests/fixtures/t1_proposal.md")
        proposal_text = fixture_path.read_text(encoding="utf-8")
        spec = parser.parse(proposal_text, spec_id="t1_proposal")

        # Should have prime factorization related approaches
        assert len(spec.method.approaches) > 0
