# sci-adk Session 3: Complete Start Prompt

> 다음 세션 시작 시 이 프롬프트를 그대로 사용하세요. 2026-05-27 Session 2 완료 상태입니다.

## 🎯 당신의 역할

당신은 **sci-adk의 공동 설계자**다. sci-adk는 **research compiler**로서 4칸 연구 제안서를 받아 paper + code + evidence trail을 산출한다.

현재 **Milestone 1 완료** 상태이며, 이번 세션에서는 **Docker 테스트** 또는 **Milestone 2 계획**을 진행한다.

---

## 📋 1. 먼저 확인할 것 (5분)

### 상태 검증

```bash
# 1. Core types 작동 확인
cd /home/cyjoe/sci-adk
python3 -c "from src.sci_adk.core.spec import Spec; print('✅ Spec OK')"
python3 -c "from src.sci_adk.core.evidence import EvidenceItem; print('✅ Evidence OK')"
python3 -c "from src.sci_adk.core.claim import Claim; print('✅ Claim OK')"

# 2. Git 상태 확인
git status
git log --oneline -5

# 3. 문서 확인
ls -la QUICKSTART.md design/session-2-handoff.md README.md
```

**모두 성공해야만 계속한다.** 실패 시 문제 해결 후 진행.

---

## 📖 2. 필독 문서 (15분)

다음 순서대로 읽으세요:

1. **QUICKSTART.md** (3분) - 빠른 시작 가이드
2. **README.md** (5분) - 프로젝트 전체 개요
3. **design/session-2-handoff.md** (7분) - Session 2 상세 상황

**중요**: 이 문서들을 읽지 않고 작업을 시작하지 마세요.

---

## 🚀 3. 선택해야 할 경로

다음 세 가지 옵션 중 하나를 선택하세요:

### Option A: Docker 테스트 (추천, 30분)

**목적**: Milestone 1 완성도 검증

**작업**:
```bash
# Docker 이미지 빌드
cd environments/python-base
docker build -t sci-adk-python-base .

# E2E 데모 실행
cd ../..
python3 demo_e2e.py

# 결과 확인
ls -la runs/spec-t1-demo/
cat runs/spec-t1-demo/spec.json | python3 -m json.tool | head -30
```

**예상 결과**:
- `runs/spec-t1-demo/` 디렉토리 생성
- `spec.json`, `evidence/*.json`, `claims/*.json` 파일들
- T-1 분자 인코딩 실험 결과

**실패 시 대응**:
- Docker 없음: Docker 설치 필요
- Permission denied: `sudo usermod -aG docker $USER` 후 재로그인

### Option B: Milestone 2 계획 (1시간+)

**목적**: Full loop 구현 또는 Paper rendering

**선택지**:
- B1: Loop controller (gather → model → evaluate → review)
- B2: Paper rendering (Claims + Evidence → LaTeX)
- B3: DecisionRule engine (interval, bayesian, proof)

**작업 흐름**:
1. design/milestone-1.md 참조하여 현재 완료된 것 확인
2. design/abstractions.md 참조하여 설계 제약조건 확인
3. 세부 계획 수립 (사용자와 논의)
4. 구현 시작

### Option C: 테스트 실행 (15분)

**목적**: 코드 품질 검증

**작업**:
```bash
# pytest 설치
pip install pytest

# 테스트 실행
pytest tests/test_spec.py -v
pytest tests/test_evidence.py -v
pytest tests/test_claim.py -v

# 커버리지 확인 (선택)
pytest tests/ --cov=src/sci_adk --cov-report=html
```

---

## 📊 4. 현재 프로젝트 상태

### 완료된 것 (Milestone 1)

✅ **Phase 1: Core Types** (1,360 lines)
- `src/sci_adk/core/spec.py` - Spec + invariants S1-S5
- `src/sci_adk/core/evidence.py` - Evidence + invariants E1-E4
- `src/sci_adk/core/claim.py` - Claim + invariants C1-C6

✅ **Phase 2: Input Parsing** (306 lines)
- `src/sci_adk/core/parser.py` - 4-pane proposal → Spec

✅ **Phase 3: Docker Environment** (338 lines)
- `environments/python-base/Dockerfile`
- `src/sci_adk/runner/docker_executor.py`

✅ **Phase 4: Evidence Generation** (199 lines)
- `src/sci_adk/loop/experiment_runner.py`

✅ **Phase 5: Claim Updates** (210 lines)
- `src/sci_adk/loop/claim_updater.py`

✅ **Unit Tests** (2,634 lines)
- `tests/test_spec.py`, `test_evidence.py`, `test_claim.py`

✅ **Demo & Docs**
- `demo_e2e.py` - End-to-end demo
- `README.md` - Complete documentation

### 검증되지 않은 것

⏸️ **Docker 실행** - 이미지 빌드 및 실제 컨테이너 실행 미검증
⏸️ **테스트 실행** - pytest 미설치, 테스트 실행 안 해봄
⏸️ **E2E 파이프라인** - demo_e2e.py 실제 실행 미검증

### 코드량

- Core 구현: ~2,000 lines
- Loop 구현: ~400 lines
- Runner 구현: ~300 lines
- Tests: ~2,600 lines
- **Total**: ~5,300 lines

---

## 🎯 5. 이번 세션의 목표

### 최소 목표 (Mandatory)

Docker 테스트 성공:
- [ ] Docker 이미지 빌드 성공
- [ ] demo_e2e.py 실행 성공
- [ ] runs/ 디렉토리 생성 확인
- [ ] spec.json, evidence/, claims/ 파일 확인

### 권장 목표 (Recommended)

Docker 테스트 후 Milestone 2 시작:
- [ ] Loop controller 설계
- [ ] Paper rendering 또는 DecisionRule engine 선택
- [ ] 상세 계획 수립

---

## ⚠️ 6. 알려진 이슈

### Docker 관련

**이슈**: Dockerfile만 작성, 이미지 빌드 안 함
**해결**: `docker build -t sci-adk-python-base environments/python-base/`

**이슈**: Docker permission 에러 가능
**해결**: `sudo usermod -aG docker $USER` 후 재로그인

### 테스트 관련

**이슈**: pytest 미설치
**해결**: `pip install pytest`

**이슈**: Import 에러
**해결**: `cd /home/cyjoe/sci-adk` 먼저 실행

### 데이터 관련

**이슈**: runs/ 디렉토리 git 추적 정책
**현재**: spec/evidence/claims는 git으로 추적, data/는 .gitignore
**확인 needed**: 전체 runs/를 .gitignore에 추가할지 결정

---

## 🔧 7. 작업 방식

### 체크포인트 모드

주요 결정마다 사용자 승인을 받으세요:
- Docker 빌드 성공 확인
- E2E 데모 실행 전 확인
- Milestone 2 방향 결정

### 질문 시 참조

**작업 중 질문**: design/session-2-handoff.md 참조
**전체 개요**: README.md 참조
**빠른 참조**: QUICKSTART.md 참조

---

## 📁 8. 주요 파일 참조

### 문서
- `QUICKSTART.md` - 세션 시작 가이드
- `README.md` - 프로젝트 개요
- `design/session-2-handoff.md` - 상세 핸드오프
- `design/milestone-1.md` - Milestone 1 정의
- `design/abstractions.md` - 코어 추상화 설계

### 코드
- `src/sci_adk/core/` - Spec/Evidence/Claim 구현
- `src/sci_adk/core/parser.py` - 4-pane 파서
- `src/sci_adk/runner/` - Docker 실행기
- `src/sci_adk/loop/` - 실험 및 Claim 업데이트
- `demo_e2e.py` - E2E 데모

### 테스트
- `tests/test_spec.py` - Spec 테스트
- `tests/test_evidence.py` - Evidence 테스트
- `tests/test_claim.py` - Claim 테스트

---

## ✅ 9. 시작 전 체크리스트

시작 전 모든 항목 확인:

- [ ] Core types import 성공?
- [ ] Git 상태 clean? (`git status`)
- [ ] QUICKSTART.md 읽음?
- [ ] README.md 읽음?
- [ ] session-2-handoff.md 읽음?
- [ ] 옵션 선택 (A/B/C)?
- [ ] 작업 경로 명확함?

---

## 🎬 10. 지금 시작하세요

**Step 1**: 위 "1. 먼저 확인할 것" 섹션의 명령어 실행
**Step 2**: 위 "2. 필독 문서" 섹션의 문서들 읽기
**Step 3**: 위 "3. 선택해야 할 경로"에서 옵션 선택
**Step 4**: 작업 시작

---

**준비되셨나요? 지금 바로 시작하세요!** 🚀

---

Version: 3.0 (Complete Session Start Prompt)
Source: Session 2 completion
Status: Ready for Session 3
Last Updated: 2026-05-27
