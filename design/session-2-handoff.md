# sci-adk — Session 3 Handoff

> 이 문서를 다음 세션의 시작 프롬프트로 사용해라. Session 2(2026-05-27)이
> 남긴 것이다. 너는 그 세션과 동일 인격이 아니다 — 산출물을 자료로 받아
> 이어가는 새 세션이다. Session 2의 판단을 무비판 계승하지 말고 필요하면 의심해라.

## 너의 역할

sci-adk의 공동 설계자. sci-adk는 **research compiler**다: 4칸 연구 제안서(연구
배경/목표/방법/기대산출물)를 input으로 받아 paper draft + working code +
evidence trail을 산출한다. 현재 Milestone 1 완료 상태.

## ★ 가장 먼저 이해할 것 — Milestone 1 완료 확인

Milestone 1의 5개 Phase가 모두 완료되었다. 검증 먼저 해라:

```bash
# Core types import 검증
python3 -c "from src.sci_adk.core.spec import Spec; print('✅ Spec')"
python3 -c "from src.sci_adk.core.evidence import EvidenceItem; print('✅ Evidence')"
python3 -c "from src.sci_adk.core.claim import Claim; print('✅ Claim')"

# E2E 데모 실행 (Docker 없이 import만)
python3 demo_e2e.py
```

위 명령이 실패하면 선행 작업이 필요하다. 성공하면 계속 진행.

## Session 2가 확정한 것 (읽고 시작해라)

- **Milestone 1 완료** → 5개 Phase 전체 구현
  - Phase 1: Core Types (spec.py, evidence.py, claim.py) — 1,360 lines
  - Phase 2: Input Parser (parser.py) — 306 lines
  - Phase 3: Docker Environment (Dockerfile, docker_executor.py) — 338 lines
  - Phase 4: Evidence Generation (experiment_runner.py) — 199 lines
  - Phase 5: Claim Updates (claim_updater.py) — 210 lines
- **Unit Tests** → 2,634 lines (test_spec.py, test_evidence.py, test_claim.py)
- **E2E Demo** → demo_e2e.py (전체 파이프라인 시연)
- **README** → 프로젝트 문서 완료
- **커밋 12개** → Session 2 전체 작업 기록

## 현재 상태 확인

```bash
# Git 상태
git status
git log --oneline -10

# 프로젝트 구조
ls -la src/sci_adk/
ls -la runs/  # 비어있어야 함 (demo_e2e.py 실행 전)
```

## 남은 작업 (이번 세션 목표)

### 1순위: Docker 이미지 빌드 및 테스트 (Milestone 1 검증)

Milestone 1 코드는 다 작성했지만, 아직 실제로 Docker에서 실행해보지 않았다.

```bash
# Docker 이미지 빌드
cd environments/python-base
docker build -t sci-adk-python-base .

# E2E 데모 실행
cd /home/cyjoe/sci-adk
python3 demo_e2e.py
```

예상 출력:
- `runs/spec-t1-demo/` 디렉토리 생성
- `spec.json`: 컴파일된 Spec
- `evidence/evi-*.json`: Evidence 로그
- `claims/claim-*.json`: Claim 상태

실패 시 대응:
- Docker 없음: Docker 설치 필요
- Permission denied: docker group 추가 필요
- Build 실패: requirements.txt 의존성 확인

### 2순위: Milestone 2 계획

Milestone 1 완료 후 다음 단계:

**Option A: Full Loop 구현** (추천)
- Loop controller (gather → model → evaluate → review)
- Convergence detection (decision rules met OR budget exhausted)
- T-1 전체 실험 (다양한 분자, 다양한 가설)
- 반복적인 Evidence 축적

**Option B: Paper Rendering**
- Claims + Evidence → LaTeX draft
- bibliography.py (BibTeX 관리)
- latex_renderer.py (섹션 생성)
- T-1 논문 초안 생성

**Option C: DecisionRule Engine**
- interval DecisionRule 구현 (95% CI 계산)
- bayesian DecisionRule 구현 (posterior odds)
- proof DecisionRule 구현 (formal verification)
- 현재 heuristic 방식 → 실제 확률 계산

### 3순위: 테스트 개선

현재 테스트는 작성되었지만 실행 안 해봄 (pytest 미설치).

```bash
# pytest 설치
pip install pytest

# 테스트 실행
pytest tests/ -v

# 커버리지 확인
pytest tests/ --cov=src/sci_adk --cov-report=html
```

## 알려진 이슈

### Docker 미설치

현재 상태: Dockerfile만 작성, 이미지 빌드 안 함
해결: `docker build -t sci-adk-python-base environments/python-base/`

### Pytest 미설치

현재 상태: 테스트 파일만 작성, 실행 안 해봄
해결: `pip install pytest`

### runs/ 디렉토리 관리

현재 상태: .gitignore로 runs/*/data/만 제외
확인 needed: runs/ 전체를 .gitignore에 추가할지 결정
현재 전략: spec/evidence/claims는 git으로 추적 (provenance), data/만 DVC

## 작업 방식

*Milestone 2 개발 과정*은 **체크포인트 모드**를 유지하라. 각 주요 결정에서 사용자 승인을 받아라.

## 시작 절차

1. **상태 확인**: 위 "Milestone 1 완료 확인" 섹션의 명령어 실행
2. **문서 정독**: README.md + design/milestone-1.md + 이 문서
3. **우선순위 결정**: 1순위(Docker 테스트)부터 할지, Milestone 2로 넘어갈지 사용자와 결정
4. **진행**: 결정된 작업 시작

## Milestone 1 성과 요약

**구현 완료**:
- Input → Spec: 4-pane parser ✅
- Spec → Evidence: T-1 실험 (Docker) ✅
- Evidence → Claim: Confidence update ✅
- 전체 파이프라인: demo_e2e.py ✅

**코드량**:
- Core: ~2,000 lines (spec, evidence, claim, parser)
- Loop: ~400 lines (experiment_runner, claim_updater)
- Runner: ~300 lines (docker_executor)
- Tests: ~2,600 lines
- **Total**: ~5,300 lines

**검증 상태**:
- ✅ Core types import 성공
- ✅ E2E 데모 작성
- ⏸️ Docker 실행 미검증 (이번 세션에서)
- ⏸️ 테스트 실행 미검증 (이번 세션에서)

## Session 2 주요 결정 사항

1. **Docker 사용 결정**: Python 3.11 slim 기반으로 확정
2. **실행 전략**: Docker executor + provenance capture (commit, image, timestamp)
3. **Evidence 평가**: 단순 heuristic (support/refute counting) → Milestone 2에서 DecisionRule engine
4. **Confidence 계산**: credence type 사용 (basis text mandatory)
5. **Null results**: E2 invariant (null results valid outcomes) 준수

## 다음 세션 체크리스트

시작 전 확인:
- [ ] Core types import 성공?
- [ ] Git 상태 clean? (git status)
- [ ] README 읽음?
- [ ] 우선순위 결정됨? (Docker 테스트 vs Milestone 2)

진행 중 확인:
- [ ] Docker 이미지 빌드 성공?
- [ ] E2E 데모 실행 성공? (runs/ 생성 확인)
- [ ] pytest 설치 및 테스트 통과?

## 참고 문서

- **Core Abstractions**: design/abstractions.md
- **Milestone 1**: design/milestone-1.md
- **README**: README.md
- **Directory Structure**: design/directory-structure.md
- **Tool Policy**: design/tool-policy.md
- **Session 1 Handoff**: design/session-1-handoff.md (이전 세션)

## 연락처

질문: 이 문서의 내용이 불명확하면 README와 design/ 문서들을 먼저 참조하라.

---

Version: 1.0
Source: Session 2 completion
Status: Ready for Session 3
Last Updated: 2026-05-27
