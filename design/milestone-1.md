# Milestone 1: Minimal Viable T-1

> Status: IMPLEMENTED (delivered on master; end-to-end T-1 compiles, suite green). Approved Session 2, 2026-06-04.
> Reference: Session 1 handoff (Deliverable #4) + Session 2 confirmation
> Last Updated: 2026-06-04 (approved); superseded by shipped implementation on master

## Goal

Demonstrate end-to-end research compilation with a **minimal viable T-1** (Molecular Numbering System) using the minimum 4 toolsets.

## Scope

### What IS in Scope

1. **Input Parsing** (4-pane proposal → Spec)
   - Parse four-pane proposal (text/markdown)
   - Compile into frozen Spec instance
   - Derive Hypotheses from "goal" pane
   - Derive MethodPlan from "method" pane
   - Derive TargetClaims from "expected_output" pane
   - Output: `runs/t-1/spec.json`

2. **First Spec Instance**
   - T-1 proposal as concrete test case
   - At least 1 Hypothesis with DecisionRule
   - Pre-registration frozen (version 1)
   - Example hypothesis: "Molecular graphs admit a bijective Gödel-style encoding using prime factorization"

3. **First Evidence**
   - At least 1 experiment run (e.g., small molecule encoding test)
   - Provenance capture: code_ref, seed, environment
   - Result: quantitative (encoding succeeded/failed, properties)
   - Bearing: supports/refutes/inconclusive
   - Output: `runs/t-1/evidence/evidence-001.json`

4. **First Claim**
   - At least 1 Claim derived from Evidence
   - Confidence with required `basis` text
   - Status: proposed/supported/contested/refuted
   - EvidenceLink (supporting AND refuting)
   - Output: `runs/t-1/claims/claim-001.json`

### What is NOT in Scope (Deferred to Milestone 2+)

- **Full T-1 workflow**: Not all T-1 hypotheses, not all experiments
- **Loop convergence**: Single experiment, not iterative loop
- **Paper rendering**: Claims + Evidence → LaTeX (milestone 2)
- **DVC integration**: Data version control (milestone 2)
- **Academic MCP**: arXiv/S2 integration (milestone 2+)
- **Advanced features**: Multi-user collaboration, reproducibility scoring

## Success Criteria

### Functional Requirements

1. **Input → Spec Compilation**
   - [ ] Four-pane proposal parser accepts T-1 text
   - [ ] Spec instance created with frozen version 1
   - [ ] Hypothesis with DecisionRule extracted
   - [ ] `runs/t-1/spec.json` valid JSON

2. **Spec → Evidence Generation**
   - [ ] At least 1 experiment executes (e.g., encode 3 simple molecules)
   - [ ] Provenance captured (commit hash, seed, Python version)
   - [ ] Result recorded (encoding success/failure, encoded numbers)
   - [ ] Bearing assigned to hypothesis
   - [ ] `runs/t-1/evidence/evidence-001.json` valid JSON

3. **Evidence → Claim Update**
   - [ ] At least 1 Claim created from Evidence
   - [ ] Confidence with `basis` text
   - [ ] Status assigned (proposed/supported)
   - [ ] EvidenceLink created
   - [ ] `runs/t-1/claims/claim-001.json` valid JSON

4. **Tool Integration**
   - [ ] Claude Code: Used for orchestration (already available)
   - [ ] Git: Commit provenance in Evidence (already available)
   - [ ] MCP: Basic connectivity (MoAI-ADK provides)
   - [ ] Docker Python: Execute experiment in container (environments/python-base/)

### Non-Functional Requirements

1. **Type Safety**: All invariants (S1-S5, E1-E4, C1-C6) enforced
2. **Null Result Handling**: Inconclusive/negative results valid outcomes
3. **No Hardcoded Metrics**: DecisionRule per Spec, not global constants
4. **Provenance**: Every EvidenceItem reproducible (code_ref + seed + environment)

## Implementation Order

### Phase 1: Core Types (Foundation)
- `src/sci_adk/core/spec.py`
- `src/sci_adk/core/evidence.py`
- `src/sci_adk/core/claim.py`
- Enforce invariants S1-S5, E1-E4, C1-C6

### Phase 2: Input Parsing
- `src/sci_adk/core/parser.py` (4-pane → Spec)
- T-1 proposal as test fixture
- Output: `runs/t-1/spec.json`

### Phase 3: Docker Execution
- `src/sci_adk/runner/docker_executor.py`
- `environments/python-base/Dockerfile`
- Provenance capture (git, seed, environment)

### Phase 4: Evidence Generation
- `src/sci_adk/loop/experiment_runner.py`
- T-1 experiment: encode 3 simple molecules (H2O, CO2, CH4)
- Output: `runs/t-1/evidence/evidence-001.json`

### Phase 5: Claim Update
- `src/sci_adk/core/claim_updater.py`
- Evaluate Evidence against Spec DecisionRule
- Output: `runs/t-1/claims/claim-001.json`

## Concrete Example: T-1 Minimal

### Input (4-pane proposal excerpt)

```
Research Goal:
분자 그래프(원자 = 꼭짓점, 결합 = 간선)를 정수론적 구조로 인코딩하는 일대일 함수를 정의한다.

Hypothesis:
소수를 원자 종류에 할당하고, 결합 구조를 지수부에 인코딩하면 분자 그래프의 일대one 인코딩이 가능하다.

Decision Rule:
interval - "effect-size 95% CI excludes 0 => support; includes 0 => null"
(Example: encoding uniqueness test with 95% CI)
```

### Output (Spec)

```json
{
  "id": "spec-t1-v1",
  "version": 1,
  "hypotheses": [
    {
      "id": "hyp-001",
      "statement": "소수 기반 분자 번호 시스템은 일대one 인코딩을 보장한다",
      "mode": "confirmatory",
      "decision_rule": {
        "kind": "interval",
        "expression": "encoding uniqueness 95% CI excludes 0"
      }
    }
  ]
}
```

### Output (Evidence)

```json
{
  "id": "evi-001",
  "spec_id": "spec-t1-v1",
  "kind": "experiment_run",
  "provenance": {
    "code_ref": "c15c95b:src/t1_test.py",
    "seed": 42,
    "environment": "python-base:3.11"
  },
  "result": {
    "type": "quantitative",
    "point": 3,
    "ci": [3, 3]
  },
  "bears_on": [
    {
      "target_id": "hyp-001",
      "direction": "supports",
      "weight": 1.0
    }
  ]
}
```

### Output (Claim)

```json
{
  "id": "claim-001",
  "spec_id": "spec-t1-v1",
  "answers": "hyp-001",
  "statement": "테스트한 3개 분자(H2O, CO2, CH4)에 대해 소수 기반 인코딩이 일대one 매핑을 보장했다",
  "status": "supported",
  "confidence": {
    "type": "credence",
    "value": 0.8,
    "basis": "3개 분자 테스트에서 모두 유일한 번호 생성 (95% CI: [3,3]). 하지만 테스트 케이스가 작아 일반화에는 제한이 있다."
  },
  "evidence_set": [
    {
      "evidence_id": "evi-001",
      "role": "supporting"
    }
  ],
  "mode": "confirmatory",
  "history": [
    {
      "at": "2026-05-26T...",
      "from": "proposed",
      "to": "supported",
      "triggered_by": "evi-001"
    }
  ]
}
```

## Testing Strategy

### Unit Tests (`tests/test_*.py`)
- Type invariant enforcement (S1-S5, E1-E4, C1-C6)
- Spec compilation from 4-pane text
- Evidence creation with provenance
- Claim update with confidence computation

### Integration Test
- End-to-end: T-1 proposal → Spec → Evidence → Claim
- Verify: `runs/t-1/` contains all artifacts

## Dependencies

### Required
- `pydantic`: JSON validation
- `docker`: Docker Python SDK

### Optional (Milestone 2+)
- `gitpython`: Git operations (currently manual)
- DVC: Data version control (deferred)

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Docker setup complexity | Medium | Medium | Use simple base image, documented in README |
| Type invariant bugs | Low | High | Comprehensive unit tests for all invariants |
| T-1 experiment scope creep | High | High | Strictly limit to 3 molecules, 1 hypothesis |

## Definition of Done

- [ ] All Phase 1-5 tasks complete
- [ ] `runs/t-1/` contains spec.json, evidence/, claims/
- [ ] All unit tests pass
- [ ] Integration test passes
- [ ] Documented in README: how to run milestone 1
- [ ] Commit: "Milestone 1: Minimal viable T-1"

---

Version: 1.0 (IMPLEMENTED)
Status: Delivered on master (historical milestone record)
Source: Session 1 handoff Deliverable #4 + Session 2 confirmation
Confirmed: 2026-06-04
