# sci-adk — DecisionEngine M2 Handoff (다음 세션 시작 프롬프트)

> 이 문서를 다음 세션의 시작점으로 사용해라. DecisionEngine Milestone-2 작업
> 세션(2026-06-15)이 남긴 것이다. 너는 그 세션과 동일 인격이 아니다 — 산출물을
> 자료로 받아 이어가는 새 세션이다. 이전 판단을 무비판 계승하지 말고 필요하면 의심해라.

## 너의 역할

sci-adk의 공동 설계자. sci-adk는 **research compiler**다: 4칸 제안서를 받아
paper draft + working code + evidence trail을 산출한다. 핵심 철학은 record(증거,
단조·append-only)와 belief(주장, 비단조·수정가능)의 분리.

## ★ 가장 먼저 이해할 것

이번 세션은 sci-adk의 최대 미구현 갭이던 **DecisionEngine(Milestone-2)** 의 수치형
부분을 설계·구현·검증·커밋했다. 사전등록된 per-Spec `DecisionRule`이 옛 득표식
(support/refute counting)을 대체해 belief를 판정하고, 새 증거가 도착하면 Claim이
비단조로 강등된다. **단일 출처는 `design/decision-engine.md` (CONFIRMED)** — D1-D8
불변식 + D0-D5 phase plan + 결정 로그(§0)가 모두 거기 있다.

## 현재 위치

- 브랜치 **`feat/decision-engine`**, 커밋 **`decf114`** (origin에 push됨, master 미병합)
- 완료(검증됨): D0 설계 CONFIRMED · D1 엔진 골격 · import 정규화 · D2 수치형 kind
  (threshold/bayesian/interval) · D4 ClaimUpdater 위임 + 비단조 업데이트
- 작업 트리 전체 테스트: **286 passed / 15 failed**. 실패 15건은 전부 Docker 의존
  통합 테스트(`test_docker_executor.py`, `test_phase4_evidence_generation.py`)이며
  WSL에 docker 미설치가 원인 — 내 코드와 무관.

## 상태 확인 (시작 시 먼저 실행)

```bash
# (지난 세션의 Bash 도구는 Windows에서 돌아 WSL 경로에 직접 못 닿았다. 그 경우
#  아래 명령을 wsl -d ubuntu -- bash -lc "cd /home/cyjoe/sci-adk && ..." 로 감싸라.)
cd /home/cyjoe/sci-adk
git checkout feat/decision-engine        # 작업 브랜치로 (master 아님)
git log --oneline -3
python3 -m pytest -q                      # 기대: 15 failed(Docker), 나머지 passed
```

## 남은 작업

### D3 — proof/qualitative → LLM-judge  (가장 복잡, 외부 LLM 동작)
`decision_engine.py`의 `_eval_proof` / `_eval_qualitative`는 현재 Phase D1 스텁
(INCONCLUSIVE 반환)이다. 이를 LLM-judge 라우팅으로 구현.

> ⚠️ **재개 시 반드시 확인할 override**: 설계 원안은 proof를 인간 체크포인트로만
> 보냈으나, 사용자가 이를 **뒤집어** proof도 LLM-judge로 보내기로 했다. 따라서
> proof judge의 고신뢰 "verified" 판정은 *반례 탐색 의무화 + 인간 spot-check*를
> 거쳐야 Claim이 `supported`가 된다. 저신뢰/반례는 인간 에스컬레이션. (근거:
> `design/decision-engine.md` §0 확정 로그 + Decision 4 + 불변식 D8.)

### D5 — T-1 종단 검증  (Docker 필요)
parser → Spec → Docker 실험 → Evidence → DecisionEngine → Claim 전체를 T-1
fixture로 돌려, 엔진이 실제로 verdict를 내리는지 + 반박 증거가 supported Claim을
강등하는지 확인. **선행 조건: Docker 설치** (현재 WSL 미설치 → 위 15개 테스트가
막혀 있는 이유와 동일). `docker build -t sci-adk-python-base environments/python-base/`.

## 알려진 이슈 / 함정

- **Import 컨벤션**: 소스/테스트/demo 전부 단일 루트 `from sci_adk...` 사용. 절대
  `from src.sci_adk...`로 되돌리지 마라 — 같은 모듈을 두 객체로 로드해 경계 간
  `isinstance`가 깨진다. `tests/test_import_convention.py`가 가드한다. standalone
  스크립트는 `sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))`.
- **Docker 미설치** → D5 막힘 + 통합 테스트 15개 실패 (환경 문제, 코드 아님).
- **작업 트리의 미커밋 잔여물**: `decf114`는 DecisionEngine 마일스톤만 담았다. MoAI
  하네스 변경(`.claude/hooks/`, `.moai/`), `environments/python-base/requirements.txt`,
  `check-docker.sh`, 미추적 Docker 테스트 2개는 의도적으로 제외돼 미커밋 상태다.
  별개 관심사이니 따로 처리하라.
- **체크포인트 모드 유지**: 각 주요 결정에서 사용자 승인을 받아라. 이번 세션도
  매 phase 게이트마다 확인받았다.

## 이번 세션의 핵심 결정 (design/decision-engine.md 8개 결정 중)

- D3(interval 귀무값): `params`에 `null_value`+side 필수화, 0 기본값 거부.
- D4(proof/qualitative): 둘 다 LLM-judge + proof 안전장치 (위 override 참조).
- D7(집계): 기본 `latest`, params로 mean/pool; proof 반례는 결정적.
- D1/D2/D5/D6/D8: 문서 권장안대로 수용.

## 참고 문서 / 메모리

- **단일 출처**: `design/decision-engine.md` (CONFIRMED, D1-D8 + phase plan + §0 로그)
- 코어 타입 스키마: `design/abstractions.md` / 구현 `src/sci_adk/core/`
- 도구 정책: `design/tool-policy.md` (LLM-judge는 허용된 Claude 백엔드)
- 자동 메모리: `decision-engine-status`, `import-convention` (새 세션에 자동 로드됨)

## 시작 절차

1. 위 "상태 확인" 명령 실행 (브랜치 + 테스트 그린 확인)
2. `design/decision-engine.md` 정독 (특히 §0 + Decision 4 override + §6 phase plan)
3. 사용자와 D3(LLM-judge) vs D5(Docker 설치 후 종단검증) 우선순위 결정
4. 결정된 phase부터 진행 (TDD: RED → GREEN → REFACTOR, phase 게이트마다 검증)

---

Version: 1.0
Source: DecisionEngine M2 session (2026-06-15) completion
Status: Ready for next session — resume at D3 or D5
Last Updated: 2026-06-16
