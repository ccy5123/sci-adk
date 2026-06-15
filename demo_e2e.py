#!/usr/bin/env python3
"""
End-to-end demo: sci-adk Milestone 1

Demonstrates full pipeline: 4-pane proposal → Spec → Evidence → Claims
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from sci_adk.core.parser import parse_proposal
from sci_adk.loop.experiment_runner import run_t1_experiments
from sci_adk.loop.claim_updater import update_claims


def main():
    """Run end-to-end demo."""
    print("=" * 60)
    print("sci-adk Milestone 1: End-to-End Demo")
    print("=" * 60)
    print()

    # Step 1: Parse proposal
    print("Step 1: Parsing T-1 proposal...")
    t1_proposal = """
연구 배경: 분자는 원자 종류, 결합 구조, 입체화학적 정보를 포함한다.
현재의 분자 식별 시스템은 수학적 구조가 결여되어 있다.

연구 목표: 분자 그래프를 정수론적 구조로 인코딩하는 일대one 함수를 정의한다.
소수를 원자 종류에 할당하고, 결합 구조를 지수부에 인코딩한다.

연구 방법: 소인수분해 정리를 핵심 도구로 활용하며,
Python으로 소규모 분자 집합에 대한 프로토타입 구현을 수행한다.

기대 산출물: 정수론적 분자 번호 시스템 이론 논문 1편,
Python 프로토타입 코드.
"""

    spec = parse_proposal(t1_proposal, spec_id="spec-t1-demo")
    print(f"✅ Spec created: {spec.id}")
    print(f"   Hypotheses: {len(spec.hypotheses)}")
    print(f"   Target claims: {len(spec.target_claims)}")
    print()

    # Step 2: Run experiment
    print("Step 2: Running T-1 molecular encoding experiment...")
    molecules = ["H2O", "CO2", "CH4", "NH3"]
    print(f"   Molecules: {molecules}")

    evidence_items = run_t1_experiments(spec, molecules)
    print(f"✅ Evidence generated: {len(evidence_items)} items")
    for ev in evidence_items:
        print(f"   - {ev.id}: {ev.result.point} successful encodings")
    print()

    # Step 3: Update claims
    print("Step 3: Evaluating evidence and updating claims...")
    claims = update_claims(spec, evidence_items)
    print(f"✅ Claims updated: {len(claims)} claims")
    for claim in claims:
        print(f"   - {claim.id}: {claim.status}")
        print(f"     Confidence: {claim.confidence.value:.2f}")
        print(f"     Basis: {claim.confidence.basis}")
    print()

    # Step 4: Show output structure
    print("Step 4: Output structure")
    output_dir = Path("runs/spec-t1-demo")
    if output_dir.exists():
        print(f"✅ Output directory: {output_dir.absolute()}")
        print(f"   Contents:")
        for item in sorted(output_dir.rglob("*")):
            if item.is_file():
                rel_path = item.relative_to(output_dir)
                print(f"   - {rel_path}")
    print()

    print("=" * 60)
    print("Milestone 1 Demo Complete!")
    print("=" * 60)
    print()
    print("Summary:")
    print(f"  - Spec ID: {spec.id}")
    print(f"  - Evidence items: {len(evidence_items)}")
    print(f"  - Claims: {len(claims)}")
    print(f"  - Output location: runs/{spec.id}/")
    print()


if __name__ == "__main__":
    main()
