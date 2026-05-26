# sw-assumptions.md — SW 개발 가정이 코드에 박힌 지점

> 답하는 질문: **Q1**(SW 가정 표층 vs 심층). 입력: Q2a/Q2b/Q2c, Q7, Q11, Q16.
> 분석 기준: repo HEAD (v2.14.0+671). 인용은 repo 경로 `moai-adk/...` 기준.
> 누적식. Day 2 1차 — 17개 식별 (목표 10개 초과).
>
> 각 항목: **(a) 위치** path:line / **(b) 가정** / **(c) 과학 워크플로우 충돌**.
> 말미에 "표층/심층" 분류와 Q1 잠정 답.

---

## [Day 2, 2026-05-26] SW 가정 17곳

### 분류 범례
- **표층(S)**: 설정값·문자열·규칙 문서 수정으로 제거/대체 가능
- **중간(M)**: 코드 구조는 일반적이나 SW 의미가 박혀 재배선 필요
- **심층(D)**: 아키텍처/상태기계/도메인 모델 자체가 SW 전제 → 재설계 비용 큼

---

### A1. development_mode = {tdd, ddd} 2분법 [중간 M]
- **(a)** `.moai/config/sections/quality.yaml:2` (`development_mode: tdd`),
  `.claude/rules/moai/workflow/spec-workflow.md:200-204` (auto-detect 표)
- **(b)** 모든 작업이 TDD(test-first) 또는 DDD(characterization-test) 중 하나에
  들어맞는다고 가정. 방법론 선택축이 *테스트 작성 시점* 하나뿐.
- **(c)** 과학 작업의 1급 산출물은 "테스트"가 아니라 *가설·실험설계·데이터·추론*.
  test-first/characterization 어느 쪽도 "데이터를 보고 가설을 갱신한다"는 귀납 루프를
  표현 못 함. 제3의 methodology(가칭 HDD, Hypothesis-Driven)가 필요 → 단순 enum 추가가
  아니라 run-phase 사이클 로직 전체가 갈림.

### A2. test_coverage_target 85% / min_coverage_per_commit 80% [표층 S, 단 의미는 심층]
- **(a)** `quality.yaml:4,15`; `internal/core/quality/trust.go:304` (`TestCoverageTarget: 85`),
  `:794` (`Rule: "tdd-min-coverage"`); `spec-workflow.md:231` ("85%+ code coverage")
- **(b)** 품질 = *코드 라인 커버리지*. 커밋마다 커버리지 하한 강제.
- **(c)** 과학에서 "커버리지"의 대응물이 모호. 분석 스크립트는 커버할 수 있으나,
  *발견(finding)의 타당성*은 커버리지와 무관 — 통계적 검정력/재현성/표본크기가 척도.
  숫자(85)는 표층 수정이나, "coverage가 곧 품질"이라는 *의미 매핑*은 심층(Q2a/Q7).

### A3. LSP 게이트 run-phase max_errors:0 [중간 M]
- **(a)** `quality.yaml:30-34` (`max_errors:0, max_type_errors:0, max_lint_errors:0, allow_regression:false`)
- **(b)** 구현 완료 = 컴파일/타입/린트 에러 0. "깨진 코드"는 미완성.
- **(c)** 탐색적 분석(노트북, 반쯤 짠 모델, 의도적 placeholder)은 정상 상태로
  에러를 품을 수 있음. "0 에러" 게이트는 탐색 단계를 비정상으로 차단. 단 게이트는
  config로 끌 수 있어(enforce_quality:false) 표층-중간.

### A4. TRUST5 "Tested" ≡ unit_tests_pass ∧ lsp_errors==0 [심층 D]
- **(a)** `quality.yaml:46-49` (trust5_integration.tested: `- unit_tests_pass`, `- lsp_errors == 0`)
- **(b)** **"검증(verify)"의 정의가 곧 테스트 통과**. harness 전체의 성공 신호가 binary pass/fail.
- **(c)** **이것이 Q2a/Q7/Q16의 핵심 충돌.** 과학의 verify = 통계적 유의성/효과크기/
  사후확률/예측-관측 일치. 이는 연속값·불확실성을 동반하며 binary로 환원 불가(또는
  손실). harness의 "성공=초록불" 상태기계를 연속 신뢰도 모델로 바꾸는 건 심층 재설계.

### A5. 언어별 test/lint 명령 하드코딩 (6+ 언어) [중간 M]
- **(a)** `internal/hook/quality/gate.go:80-131` — toolchains 테이블: Go(`go test ./...`,
  `go vet`, golangci-lint), Node(`npm test`, eslint), Python(`pytest`, ruff, mypy),
  Rust(`cargo test`, clippy), Java(`mvn test`, checkstyle), Kotlin(:133~)
- **(b)** 산출물은 *6개 SW 언어 중 하나로 된 코드*이며 표준 test runner를 가진다.
- **(c)** 과학 분석은 R/Julia/MATLAB/Mathematica/Stan/Jupyter 등이 주력 — 다수는
  "test runner" 개념이 약하거나(스크립트 실행=결과 산출), 출력이 stochastic. 테이블에
  과학 언어를 추가해도 "test step"이 무엇인지가 비자명. 구조는 확장 가능(표→항목 추가)
  하나 *"실행=검증" 의미*가 안 맞음 → 중간.

### A6. Ralph/loop 피드백 = go test + go vet 출력 [중간 M]
- **(a)** `internal/loop/go_feedback.go:75` ("Collect runs go test and go vet"),
  `:87` (`-coverprofile=`), `:111` ("Run go vet for lint errors")
- **(b)** 자동 수렴 루프(Ralph 엔진)의 "피드백 신호"가 *컴파일러/테스트 출력*.
  루프는 에러가 0이 될 때까지 코드를 고친다.
- **(c)** 과학 루프의 피드백은 "모델이 데이터에 맞는가 / 예측이 관측과 일치하는가 /
  잔차가 줄었는가". 즉 피드백 생성기(FeedbackGenerator 인터페이스)를 과학 메트릭
  생산자로 교체해야 함. **단 인터페이스화돼 있다는 점은 긍정 신호**(Q3/reusable 후보).

### A7. MX 태그 트리거가 코드구조 기반 [심층 D — 도메인 모델]
- **(a)** `.claude/rules/moai/workflow/mx-tag-protocol.md:37` (complexity≥15),
  `:42`/`:73` (fan_in≥3), `:47` (public function no test file); `internal/mx/tag.go`
- **(b)** 코드 컨텍스트 단위 = 함수/콜그래프. ANCHOR=fan_in, WARN=순환복잡도/goroutine,
  TODO=무테스트 public 함수.
- **(c)** 과학 산출물의 단위는 함수 콜그래프가 아니라 *데이터셋·수식·가정·도출·그림*.
  "fan_in≥3", "goroutine without context"는 과학 맥락에서 의미 없음. MX 개념(세션 간
  컨텍스트 전달 주석)은 흥미로우나 트리거 규칙 전체를 과학 도메인 모델로 재정의해야 함.

### A8. SPEC = EARS format 요구사항 + acceptance criteria [심층 D]
- **(a)** `spec-workflow.md:147` ("using EARS format"), `:151`,`:163`;
  `internal/harness/proposalgen/scaffolder.go:6` ("EARS-style placeholders")
- **(b)** 작업은 "the system shall …" 형태의 *검증가능한 요구사항*으로 분해된다.
  결과물은 사전에 acceptance criteria로 확정 가능.
- **(c)** 과학은 *연구 질문/가설*에서 출발하며 결과가 사전 미지(unknown a priori).
  "shall" 요구사항이 아니라 "X가 Y에 영향을 주는가?"의 검증. acceptance는 "가설이
  지지/기각되었나"이지 "기능이 동작하나"가 아님. Q8(SPEC=pre-registration) 재해석은
  부분 가능하나 EARS 골격은 재작성 필요.

### A9. RED-GREEN-REFACTOR 단조 수렴 [심층 D]
- **(a)** `spec-workflow.md:190-194` (RED: "Verify it fails", GREEN: "simplest that
  passes", REFACTOR: "keeping tests green"); 성공기준 "No test written after
  implementation code"(워크플로우 규칙)
- **(b)** 상태가 빨강→초록으로 *단조 전진*하며 한번 초록이면 회귀는 결함.
- **(c)** **Q2b 직결.** 가설은 "통과"되지 않고 기각/부분지지/추가증거대기를 오감
  (비단조·가역). 새 데이터로 이전 결론이 뒤집히는 것은 결함이 아니라 정상 과학.
  단조 상태기계로는 이 가역성을 표현 못 함.

### A10. git 커밋/PR/브랜치-per-SPEC가 배포 단위 [중간 M]
- **(a)** `spec-workflow.md` § SPEC Phase Discipline (4-step lifecycle, `plan/feat/sync`
  브랜치 + squash PR); `.moai/config/sections/git-convention.yaml`, `git-strategy.yaml`
- **(b)** 작업 단위 = git 브랜치 + PR. Conventional Commits. 완료 = main 머지.
- **(c)** 과학 단위는 *실험 run / 노트북 / 데이터셋 버전 / 분석 파이프라인*. provenance
  (어떤 데이터+코드+시드로 이 그림이 나왔나)가 PR보다 중요. git 자체는 유용하나
  "PR 머지=완료" 프레임은 안 맞음. DVC/MLflow류 실험 추적이 더 적합.

### A11. 방법론 자동선택을 *테스트 커버리지%*로 [중간 M]
- **(a)** `spec-workflow.md:200-204` (Greenfield→TDD, Brownfield <10%→DDD)
- **(b)** 기존 테스트 커버리지가 프로젝트 상태의 핵심 신호.
- **(c)** 과학 프로젝트에 "테스트 커버리지" 개념 자체가 없음 → 자동선택 입력이 부재.
  새 신호(데이터 가용성? 선행연구 유무? 모델 성숙도?)로 대체 필요.

### A12. Drift Guard: 계획 파일 vs 실제 수정 비교 [중간 M]
- **(a)** `spec-workflow.md:214` ("compare planned files against actual modifications,
  warns at ≤30% drift, triggers re-planning above 30%")
- **(b)** 계획 단계에서 *어떤 파일이 바뀔지 예측 가능*하며 예측 이탈은 위험신호.
- **(c)** 탐색적 분석은 어떤 데이터/스크립트를 건드릴지 사전 예측 불가가 정상.
  "30% drift = 재계획"은 탐색을 페널티화. 발견 과정의 본질(예측 못 한 방향 전환)과 충돌.

### A13. 재계획 게이트: "커버리지 하락 / 새 에러 > 고친 에러" = 정체 [심층 D]
- **(a)** `spec-workflow.md:239-243` (Re-planning triggers: "Test coverage dropping
  instead of increasing", "New errors introduced exceed errors fixed")
- **(b)** 진전의 척도 = 커버리지↑·에러↓. 그 반대는 "stuck/diverging"으로 개입 트리거.
- **(c)** 과학에서 "가설이 지지되지 않음 / 효과 없음"은 *유효한 결과(null result)*이지
  정체가 아님. harness는 null result를 실패로 오인해 재계획을 강요 → 과학적으로 해로움.

### A14. /simplify 자동 + "더 적은 줄" 3x LOC 트리거 [표층 S]
- **(a)** `spec-workflow.md:216` ("`/simplify` runs automatically after REFACTOR");
  `.claude/rules/moai/development/karpathy-quickref.md` (Simplicity First: "3x LOC trigger",
  "Can this be done in fewer lines?")
- **(b)** 코드 간결성(최소 줄수)이 보편적 선(善).
- **(c)** 과학 코드는 *명시성·재현성*이 간결성보다 우선일 때가 많음(모든 전처리 단계를
  명시적으로 남기는 것이 재현성에 유리). "fewer lines" 자동 압박은 재현성과 상충 가능.
  단 끄거나 기준 바꾸기 쉬움 → 표층.

### A15. 16개 언어 심층 SW 규칙 (go.md 등) [표층 S — 폐기/교체]
- **(a)** `.claude/rules/moai/languages/go.md` (errgroup, GORM, cobra, sqlc, Fiber/Gin…),
  + 15개 언어 동급 규칙
- **(b)** 대상 도메인 = 웹/백엔드/CLI SW. 프레임워크 관용구가 1급 지식.
- **(c)** 과학 분석 언어(R tidyverse, Julia 벡터화, NumPy/SciPy/PyMC, Stan)의 관용구는
  전혀 다름(재현 시드, 벡터화, 통계 모델링). 기존 언어규칙은 과학용에서 dead weight →
  폐기 후 과학 스택 규칙으로 교체(Q11). 파일 교체라 표층.

### A16. coverage_exemptions max 5% + 정당화 필수 [표층 S, 의미는 중간]
- **(a)** `quality.yaml:17-20` (`coverage_exemptions.enabled:false, max_exempt_percentage:5`)
- **(b)** 거의 모든 코드가 테스트 가능하다는 전제(면제는 5% 예외).
- **(c)** 과학 코드 상당부분(난수 시뮬, 외부 solver 호출, 플로팅)은 결정론적 단위
  테스트가 어렵거나 무의미. 5% 면제 상한은 과학 현실과 안 맞음.

### A17. 완료 마커 binary + 성공기준 "요구사항 구현+테스트 통과" [심층 D]
- **(a)** `spec-workflow.md` § Completion Markers (`<moai>DONE</moai>`/`COMPLETE`);
  Run Phase 성공기준 "All SPEC requirements implemented / tests passing / 85% coverage"
- **(b)** 작업은 *완료(DONE)라는 이산 종착*을 가진다.
- **(c)** 연구는 "불확실성을 동반한 주장(claim with CI)"으로 마무리되지 binary DONE이
  드묾. 추가 실험/재현/동료검토로 열린 채 끝남. 완료 모델 자체가 SW적.

---

## Day 2 잠정 종합 (Q1 1차 답)

**분포: 심층 D = 6곳(A4, A7, A8, A9, A13, A17), 중간 M = 7곳, 표층 S = 4곳.**

- **표층(S, 4)**: 숫자·언어규칙·simplify — config/파일 교체로 처리. fork 시 저비용.
- **중간(M, 7)**: 구조는 일반적이나 SW 의미가 박힘 — 인터페이스 재배선(A6 FeedbackGenerator는
  실제로 인터페이스화돼 있어 유리). fork 시 중간 비용.
- **심층(D, 6)**: **harness의 핵심 가치 명제 자체가 SW**다 — "verify=test pass"(A4),
  "단조 수렴"(A9), "binary 완료"(A17), "null=정체"(A13), 코드구조 도메인 모델(A7),
  요구사항 분해(A8). 이 6곳은 *config로 못 끄며 상태기계·도메인 모델 재설계*가 필요.

**Q1 잠정 답:** SW 가정은 *표층과 심층이 섞여 있고, 핵심 가치(verify 루프·완료 모델)는
심층*이다. 인프라(reusable.md에서 검증할 hook/config/worktree/template)는 SW-중립에
가깝지만, **"무엇이 좋은 결과인가"를 판정하는 두뇌부(quality/loop/spec/constitution)는
SW 전제가 골수까지** 박혀 있다. → fork하면 인프라는 살지만 두뇌부는 사실상 재작성.
이 경계선이 fork vs scratch 견적의 핵심. (tdd-mismatch.md에서 A4/A9/A13을 심화.)

### 미검증/확신 못 함
- A6 FeedbackGenerator가 정말 깔끔한 인터페이스인지 코드 정독 필요(Day 3/Day 4 reusable).
- `internal/constitution`(2121 LOC), `internal/core/quality`(trust.go 외)의 binary 게이트
  강도 — 아직 표면만 봄.
- harness.yaml(minimal/standard/thorough)이 verify 의미를 얼마나 깊이 박았는지 미확인.
