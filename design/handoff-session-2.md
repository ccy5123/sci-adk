# Session 2 Handoff

**Date**: 2026-06-05
**Status**: Phase 1-2 Complete ✅
**Commit**: 29cbeb1

---

## Session Summary

Phase 1-2 (Core Types + Input Parsing) 완료. 181/181 테스트 통과.

### Completed Work

**Phase 1: Core Types** (176/176 tests passing)
- Pydantic V2 마이그레이션 완료 (16개 경고 제거)
- Spec: Frozen pre-registration contract (S1-S5 invariants)
- Evidence: Immutable, append-only log (E1-E4 invariants)
- Claim: Revisable belief state (C1-C6 invariants)
- Constitution established (`design/constitution.md`)

**Phase 2: Input Parsing** (5/5 tests passing)
- 4-pane proposal parser 구현 (`src/sci_adk/core/parser.py`)
- Parser 정규식: `#\s+(Section|Name)\b` (단어 경계로 부분 매칭 방지)
- T-1 fixture 작성 (`tests/fixtures/t1_proposal.md`)
- Spec 컴파일 작동 검증

### Key Technical Decisions

**Parser Regex Pattern**
```python
SECTION_PATTERNS = {
    "background": r"#\s+(?:연구\s*배경|Research\s+Background)\b|#\s+Background\b",
    "goal": r"#\s+(?:연구\s*목표|Research\s+Goal)\b|#\s+Goal\b",
    "method": r"#\s+(?:연구\s*방법|Research\s+Method)\b|#\s+Method\b",
    "expected_output": r"#\s+(?:기대\s*산출물|Expected\s+Output)\b|#\s+(?:Expected\s+Output|Output)\b",
}
```

**Decision Rule Pattern**
- No hardcoded metrics (no "85% coverage" globals)
- Each Spec declares own DecisionRule per hypothesis
- Claim.confidence judged against that rule

**T-1 Fixture: Molecular Numbering System**
- Background: Molecular graphs + numbering motivation
- Goal: Gödel-style encoding hypothesis
- Method: Prime factorization approach
- Expected Output: Encoding algorithm + injectivity demonstration

---

## Remaining Work

### Phase 3: Docker Execution (PENDING)

**Reference**: `design/milestone-1.md` Phase 3

**Tasks**:
1. `src/sci_adk/runner/docker_executor.py` 구현
2. Docker 이미지 빌드 (Python, SageMath, Lean 4, LaTeX)
3. Provenance capture (Git commit hash, environment snapshot)
4. Tool execution logging

**Tool Policy**: `design/tool-policy.md`
- Allowed: docker (Python, SageMath, Lean 4, LaTeX per domain)
- Excluded from sci-adk runtime: LSP servers, ast-grep, Conventional Commits, Coverage thresholds

**Files to Create**:
- `src/sci_adk/runner/__init__.py`
- `src/sci_adk/runner/docker_executor.py`
- `src/sci_adk/runner/provenance.py`

**Test Targets**:
- Docker image build test
- Tool execution test (Python calculator, SageMath symbolic, Lean 4 proof)
- Provenance capture test

### Phase 4: Evidence Generation (PENDING)

**Reference**: `design/milestone-1.md` Phase 4

**Tasks**:
1. `src/sci_adk/core/evidence.py` Evidence types 확장
2. Tool result → Evidence 변환
3. Evidence chain 구축 (Result + Bearing[] + Provenance)
4. null/negative results 처리

**Key Design**:
- Evidence is monotone append-only log
- Bearing records "supports" | "refutes" | "inconclusive"
- Provenance includes Git commit + Docker environment

### Phase 5: Claim Update (PENDING)

**Reference**: `design/milestone-1.md` Phase 5

**Tasks**:
1. `src/sci_adk/core/claim.py` Claim status update logic
2. DecisionRule evaluation against Evidence
3. Claim.confidence recalculation
4. Claim.status transition (PROPOSED → SUPPORTED → REJECTED)

**Key Design**:
- Claim is non-monotone (status can move both directions)
- Explicit "contested" status when evidence conflicts
- Each claim links to Evidence[] (evidence_trace)

---

## File State

### Modified Files (Session 2)

**Core Types**:
- `src/sci_adk/core/claim.py` (Pydantic V2, C1-C6 invariants)
- `src/sci_adk/core/evidence.py` (Pydantic V2, E1-E4 invariants)
- `src/sci_adk/core/spec.py` (Pydantic V2, S1-S5 invariants)

**Parser**:
- `src/sci_adk/core/parser.py` (306 lines, 4-pane parser)

**Tests**:
- `tests/test_evidence.py` (66 tests passing)
- `tests/test_spec.py` (54 tests passing)
- `tests/test_parser.py` (61 tests passing)

### New Files (Session 2)

**Constitution**:
- `design/constitution.md` (sci-adk identity + rules)

**Fixtures**:
- `tests/fixtures/t1_proposal.md` (T-1: Molecular Numbering System)

### Untracked Files

**Session Reports**:
- `.moai/reports/session-*.md` (9 session reports)

---

## Test Status

```
181/181 tests passing (100%)

Phase 1 (Core Types):
- test_claim.py: 62/62 passing
- test_evidence.py: 66/66 passing
- test_spec.py: 54/54 passing

Phase 2 (Input Parsing):
- test_parser.py: 61/61 passing
```

---

## Technical Debt

### Resolved ✅
- Pydantic V2 migration (16 warnings → 0)
- Parser regex edge cases (partial matches fixed)
- T-1 fixture format (missing `#` prefix added)

### Remaining ⏳
- Docker executor implementation (Phase 3)
- Evidence chain validation (Phase 4)
- Claim status transition logic (Phase 5)

---

## Next Session Checklist

### Startup Sequence

1. **Read Handoff** (this file)
2. **Read Core Documents**:
   - `design/constitution.md`
   - `design/abstractions.md`
   - `design/tool-policy.md`
   - `design/milestone-1.md`
3. **Verify Environment**:
   - Docker daemon running: `docker ps`
   - Python 3.12+: `python3 --version`
4. **Check Tests**: `pytest --tb=no -q`
5. **Start Phase 3**: Docker Execution

### Phase 3 Entry Point

**File**: `src/sci_adk/runner/docker_executor.py`

**Reference Implementation** (pseudo-code):
```python
class DockerExecutor:
    def execute_tool(self, tool_ref: ToolRef, input_data: str) -> Evidence:
        # Build Docker image based on tool_ref.domain
        # Execute code in container
        # Capture result + provenance
        # Return Evidence instance
        pass
```

**First Test**:
```python
def test_python_calculator():
    executor = DockerExecutor()
    tool_ref = ToolRef(domain="python", name="calculator")
    result = executor.execute_tool(tool_ref, "2+2")
    assert result.result == "4"
```

---

## Known Issues

### Git Ownership (WSL-over-Windows)
- **Status**: Session 1 reported, user approval required
- **Command**: `git config --global --add safe.directory /home/cyjoe/sci-adk`

### .gitignore Additions
- `runs/*/data/` (research artifacts)
- LaTeX temp files (`*.aux`, `*.log`)

---

## Milestone 1 Roadmap

```
┌──────────────────────────────┬─────────┬────────┐
│            Phase             │  상태   │ 진행률 │
├──────────────────────────────┼─────────┼────────┤
│ Phase 1: Core Types          │ ✅ 완료 │ 100%   │
├──────────────────────────────┼─────────┼────────┤
│ Phase 2: Input Parsing       │ ✅ 완료 │ 100%   │
├──────────────────────────────┼─────────┼────────┤
│ Phase 3: Docker Execution    │ ⏸️ 대기 │ -      │
├──────────────────────────────┼─────────┼────────┤
│ Phase 4: Evidence Generation │ ⏸️ 대기 │ -      │
├──────────────────────────────┼─────────┼────────┤
│ Phase 5: Claim Update        │ ⏸️ 대기 │ -      │
└──────────────────────────────┴─────────┴────────┘

전체 진행률: 40% (Phase 1-2/5 완료)
```

---

## Session 2 Achievements

1. **Quality Gate**: 181/181 tests passing (179→181, fixed edge cases)
2. **Technical Debt**: Pydantic V2 migration complete (16→0 warnings)
3. **Parser Production**: 306-line parser with word-boundary regex
4. **T-1 Fixture**: Molecular Numbering System proposal ready
5. **Constitution**: sci-adk identity documented in `design/constitution.md`

---

## Command Reference

### Test Commands
```bash
# All tests
pytest --tb=no -q

# Specific phase
pytest tests/test_parser.py -v

# With coverage
pytest --cov=src/sci_adk --cov-report=html
```

### Docker Commands
```bash
# Verify Docker daemon
docker ps

# Build image (Phase 3)
docker build -t sci-adk-python -f environments/Dockerfile.python

# Run container (Phase 3)
docker run --rm sci-adk-python python3 -c "print(2+2)"
```

### Git Commands
```bash
# Check status
git status

# View commit
git show 29cbeb1 --stat

# View diff
git diff master~1 master
```

---

**End of Handoff**

Next session: Start Phase 3 (Docker Execution) from `src/sci_adk/runner/docker_executor.py`.

Reference: `design/milestone-1.md` Phase 3 specification.
