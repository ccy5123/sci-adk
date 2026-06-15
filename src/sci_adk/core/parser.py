"""
Four-pane proposal parser for sci-adk.

Parses research proposals in 4-pane format (Background/Goal/Method/Expected Output)
and compiles them into frozen Spec instances.

Reference: design/abstractions.md (RawProposal → Spec compilation)
"""

import re
from datetime import datetime, timezone
from typing import Optional, List

from sci_adk.core.spec import (
    Spec,
    RawProposal,
    Hypothesis,
    DecisionRule,
    MethodPlan,
    TargetClaim,
    ToolRef,
    HypothesisMode,
    DecisionRuleKind,
)


class ProposalParser:
    """
    Parser for 4-pane research proposals.

    Extracts structured data from free-form proposal text and compiles
    into frozen Spec instances with derived Hypotheses, MethodPlan, and TargetClaims.
    """

    # Section markers for 4-pane format
    # Support both "# Background" and "Background" formats
    # Handle split lines (no trailing newline)
    SECTION_PATTERNS = {
        "background": r"#\s+(?:연구\s*배경|Research\s+Background)\b|#\s+Background\b",
        "goal": r"#\s+(?:연구\s*목표|Research\s+Goal)\b|#\s+Goal\b",
        "method": r"#\s+(?:연구\s*방법|Research\s+Method)\b|#\s+Method\b",
        "expected_output": r"#\s+(?:기대\s*산출물|Expected\s+Output)\b|#\s+(?:Expected\s+Output|Output)\b",
    }

    def __init__(self):
        """Initialize parser with compiled regex patterns."""
        self._section_regex = self._compile_section_patterns()

    def _compile_section_patterns(self) -> dict:
        """Compile regex patterns for section detection."""
        return {
            key: re.compile(pattern, re.IGNORECASE)
            for key, pattern in self.SECTION_PATTERNS.items()
        }

    def parse(self, proposal_text: str, spec_id: Optional[str] = None) -> Spec:
        """
        Parse 4-pane proposal text and compile into Spec instance.

        Args:
            proposal_text: Free-form proposal text with 4 sections
            spec_id: Optional Spec ID (auto-generated if None)

        Returns:
            Frozen Spec instance with derived Hypotheses, MethodPlan, TargetClaims

        Raises:
            ValueError: If required sections are missing or parsing fails
        """
        # Extract sections
        sections = self._extract_sections(proposal_text)

        # Validate required sections
        required = ["background", "goal", "method", "expected_output"]
        missing = [s for s in required if not sections.get(s)]
        if missing:
            raise ValueError(f"Missing required sections: {missing}")

        # Create RawProposal
        raw_proposal = RawProposal(
            background=sections["background"],
            goal=sections["goal"],
            method=sections["method"],
            expected_output=sections["expected_output"],
        )

        # Derive components
        hypotheses = self._derive_hypotheses(sections["goal"])
        method = self._derive_method_plan(sections["method"])
        target_claims = self._derive_target_claims(
            sections["expected_output"], hypotheses
        )

        # Create Spec
        return Spec(
            id=spec_id or self._generate_spec_id(),
            created_at=datetime.now(timezone.utc).isoformat(),
            version=1,
            raw_proposal=raw_proposal,
            hypotheses=hypotheses,
            method=method,
            target_claims=target_claims,
        )

    def _extract_sections(self, text: str) -> dict:
        """
        Extract 4 sections from proposal text.

        Handles both delimiter-separated and continuous formats.
        """
        sections = {}

        # Try delimiter-separated format first
        lines = text.split("\n")
        current_section = None
        current_content = []

        # DEBUG
        import sys
        print(f"DEBUG: Lines count: {len(lines)}", file=sys.stderr)

        for line_idx, line in enumerate(lines):
            # Check if line is a section header
            matched = False
            for section_name, pattern in self._section_regex.items():
                if pattern.search(line):
                    print(f"DEBUG: Line {line_idx} matched {section_name}: {repr(line)}", file=sys.stderr)
                    # Save previous section if exists
                    if current_section:
                        saved = "\n".join(current_content).strip()
                        print(f"DEBUG: Saving {current_section}: {repr(saved[:50])}", file=sys.stderr)
                        sections[current_section] = saved
                    # Start new section
                    current_section = section_name
                    current_content = []
                    matched = True
                    break

            if not matched and current_section:
                print(f"DEBUG: Line {line_idx} added to {current_section}: {repr(line)}", file=sys.stderr)
                current_content.append(line)

        # Save last section
        if current_section:
            saved = "\n".join(current_content).strip()
            print(f"DEBUG: Saving final {current_section}: {repr(saved[:50])}", file=sys.stderr)
            sections[current_section] = saved

        # DEBUG: Print extraction result
        print(f"DEBUG: Extracted sections: {sections}", file=sys.stderr)

        # Fallback: if no sections found, treat entire text as goal
        if not sections:
            sections["goal"] = text.strip()

        return sections

    def _derive_hypotheses(self, goal_text: str) -> List[Hypothesis]:
        """
        Derive Hypotheses from goal section.

        Simple heuristic: extract sentences that look like hypotheses.
        Full NLP-based extraction deferred to future milestone.

        Args:
            goal_text: Goal section text

        Returns:
            List of Hypothesis objects with DecisionRules
        """
        hypotheses = []
        sentences = self._split_sentences(goal_text)

        for idx, sentence in enumerate(sentences, start=1):
            # Skip very short sentences
            if len(sentence) < 20:
                continue

            # Create hypothesis with default rule
            # TODO: Better hypothesis extraction (milestone 2+)
            hyp = Hypothesis(
                id=f"hyp-{idx:03d}",
                statement=sentence.strip(),
                mode=HypothesisMode.EXPLORATORY,  # Default to exploratory
                decision_rule=DecisionRule(
                    kind=DecisionRuleKind.QUALITATIVE,
                    expression="Expert judgment based on evidence",
                ),
            )
            hypotheses.append(hyp)

        # Ensure at least one hypothesis
        if not hypotheses and goal_text.strip():
            hypotheses.append(
                Hypothesis(
                    id="hyp-001",
                    statement=goal_text.strip(),
                    mode=HypothesisMode.EXPLORATORY,
                    decision_rule=DecisionRule(
                        kind=DecisionRuleKind.QUALITATIVE,
                        expression="Expert judgment based on evidence",
                    ),
                )
            )

        return hypotheses

    def _derive_method_plan(self, method_text: str) -> MethodPlan:
        """
        Derive MethodPlan from method section.

        Extracts mentioned approaches and tools.

        Args:
            method_text: Method section text

        Returns:
            MethodPlan with approaches and tools
        """
        # Simple heuristic: extract sentences as approaches
        approaches = self._split_sentences(method_text)
        approaches = [a.strip() for a in approaches if len(a.strip()) > 10]

        # TODO: Tool extraction (milestone 2+)
        tools = []

        return MethodPlan(approaches=approaches, tools=tools)

    def _derive_target_claims(
        self, expected_output_text: str, hypotheses: List[Hypothesis]
    ) -> List[TargetClaim]:
        """
        Derive TargetClaims from expected_output section.

        Each claim references an existing hypothesis.

        Args:
            expected_output_text: Expected output section text
            hypotheses: List of existing hypotheses (for reference validation)

        Returns:
            List of TargetClaim objects
        """
        claims = []
        sentences = self._split_sentences(expected_output_text)

        # Use first hypothesis as default reference
        default_hyp_id = hypotheses[0].id if hypotheses else "hyp-001"

        for idx, sentence in enumerate(sentences, start=1):
            # Skip very short sentences
            if len(sentence) < 15:
                continue

            claim = TargetClaim(
                id=f"claim-{idx:03d}",
                statement=sentence.strip(),
                answers=default_hyp_id,  # References first hypothesis
            )
            claims.append(claim)

        # Ensure at least one claim
        if not claims and expected_output_text.strip():
            claims.append(
                TargetClaim(
                    id="claim-001",
                    statement=expected_output_text.strip(),
                    answers=default_hyp_id,
                )
            )

        return claims

    def _split_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences.

        Simple rule-based split. Full NLP deferred to milestone 2+.

        Args:
            text: Input text

        Returns:
            List of sentences
        """
        # Split on common sentence delimiters
        sentences = re.split(r"[.!?]+\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _generate_spec_id(self) -> str:
        """Generate unique Spec ID using timestamp."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"spec-{timestamp}"


def parse_proposal(
    proposal_text: str, spec_id: Optional[str] = None
) -> Spec:
    """
    Convenience function to parse proposal and compile Spec.

    Args:
        proposal_text: 4-pane proposal text
        spec_id: Optional Spec ID (auto-generated if None)

    Returns:
        Compiled Spec instance

    Example:
        >>> proposal = '''
        ... Research Background: ...
        ... Research Goal: Develop a numbering system.
        ... Research Method: Use prime factorization.
        ... Expected Output: Working prototype.
        ... '''
        >>> spec = parse_proposal(proposal)
        >>> print(spec.id)
        >>> print(len(spec.hypotheses))
    """
    parser = ProposalParser()
    return parser.parse(proposal_text, spec_id)
