# tdd-mismatch.md — TDD 흐름이 과학적 방법과 갈라지는 지점

> 답하는 질문: **Q2a**(test pass 대응물), **Q2b**(단조 수렴), **Q2c**(순서강제/사전등록).
> 추가 대상(지시서): Self-Verify Loop, Ralph Engine, TRUST 5.
> 분석 기준 repo HEAD. 누적식. Day 3 1차.
>
> sw-assumptions.md A4/A9/A13의 심화. 여기서는 *루프 내부 코드*를 들여다본다.

---

## [Day 3, 2026-05-26] 핵심 발견: 루프의 "성공"은 정수 0의 논리곱이다

### 0. Self-Verify Loop = Ralph Engine = 하나의 피드백 루프

세 이름이 같은 것을 가리킨다. README의 "Self-Verify Loop", skill `moai-workflow-loop`,
패키지 `internal/ralph`+`internal/loop`이 모두 동일 메커니즘:

> Command(`/moai loop|fix`) → PostToolUse Hook(LSP diagnostics) + Stop Hook(loop control)
> → Backend(LSP Client / AST-grep / Test Runner) → **Completion Check(errors==0,
> tests pass, coverage met)** → 계속 or 완료.
> (`.claude/skills/moai-workflow-loop/SKILL.md:57`, `:71`)

### 1. 피드백의 자료형 — 무엇이 측정되는가

```go
// internal/loop/state.go:112-130
type Feedback struct {
    TestsFailed    int               // :116
    LintErrors     int               // :117
    BuildSuccess   bool              // :118
    Coverage       float64           // :119
    LSPDiagnostics []lsp.Diagnostic  // :130
}
```

루프가 인지하는 세계는 **{실패 테스트 수, 린트 에러 수, 빌드 성공 bool, 커버리지%,
LSP 진단 목록}** 이 전부다. 확률·효과크기·신뢰구간·사후분포·잔차 같은 *연속·불확실
척도가 자료형에 아예 없다*.

### 2. "수렴(성공)"의 정의 — 정수 0의 논리곱

```go
// internal/loop/feedback.go:66-74  MeetsQualityGate
return fb.TestsFailed == 0 &&
    fb.LintErrors == 0 &&
    fb.BuildSuccess &&
    fb.Coverage >= float64(config.DefaultTestCoverageTarget)  // 85
```

Ralph 엔진은 이 게이트가 참일 때만 `ActionConverge`(`internal/ralph/engine.go:52-58`).
즉 **"완료"는 0==실패 ∧ 0==린트 ∧ 빌드성공 ∧ 커버리지≥85 라는 boolean**. 부분적
성공·정도의 성공이라는 개념이 없다.

### 3. "진전/정체"의 정의 — 단조 가정이 코드에 박힘

```go
// internal/loop/feedback.go:43-50  IsImproved
return curr.TestsFailed < prev.TestsFailed ||
    curr.LintErrors  < prev.LintErrors  ||
    curr.Coverage    > prev.Coverage

// internal/loop/feedback.go:52-61  IsStagnant
return curr.TestsFailed == prev.TestsFailed &&
    curr.LintErrors == prev.LintErrors &&
    curr.Coverage == prev.Coverage
```

"개선" = 실패↓ 또는 린트↓ 또는 커버리지↑. "정체" = 셋 다 불변. 그리고 `quality.yaml:34`
`allow_regression: false` — **메트릭이 나빠지는 것(regression)은 금지된 결함**.

### 4. Ralph 의사결정 우선순위 (`internal/ralph/engine.go:34-75`)

1. `Iteration >= MaxIter` → **abort** (engine.go:43; 기본 maxIter=5, controller.go:32)
2. `MeetsQualityGate` → **converge** (성공)
3. `AutoConverge && IsStagnant` → **converge** ("no improvement detected", :68)
4. `HumanReview && Phase==Review` → review 요청
5. else → **continue**

→ 루프는 *에러가 0이 될 때까지 코드를 고치고*, 더 못 고치면(정체) 포기하듯 수렴한다.

---

## Q2a — 과학에서 "test pass"의 대응물?

**답: 직접 대응물이 없다. harness의 통과 신호는 정수 카운트의 0-비교 + 커버리지
임계값(연속값을 임계로 이산화)이며, 과학의 검증 척도(p-value, effect size, Bayesian
posterior, 신뢰구간, 예측-관측 RMSE)와 자료형 수준에서 어긋난다.**

- harness: `bool = (TestsFailed==0 ∧ LintErrors==0 ∧ Coverage≥85)` — 손실 없는 binary.
- 과학: "효과가 있다"는 *p<.05 그리고 효과크기 0.4 (95% CI [0.2,0.6])* 같은 **연속·
  불확실 진술**. 이것을 binary로 누르면 정보 손실(α/β 오류, 효과크기 무시)이 일어남.
- 결론: `Feedback` 구조체에 연속·확률 필드(예: `posterior float64`, `effectSize`,
  `pValue`, `predictiveError`)를 추가하고 `MeetsQualityGate`를 *임계 통과가 아닌
  신뢰도 평가*로 바꿔야 함. 이는 단순 필드 추가가 아니라 **DecisionEngine 의미 재정의**
  (sw-assumptions A4 심층 D). 단 `DecisionEngine`/`FeedbackGenerator`가 인터페이스라
  교체 지점은 명확함(reusable.md에서 검증).

## Q2b — TDD의 단조 수렴 가정이 과학에서 성립하나?

**답: 성립하지 않는다. 코드가 단조성을 *강제*한다 — 메트릭 악화를 결함으로 본다
(`allow_regression:false`, `IsImproved`는 ↓/↑만 개선으로 인정). 과학 가설은 비단조·
가역이라 충돌한다.**

- SW 루프: 상태는 "에러 N개 → N-1개 → … → 0개"로 단조 하강. 한번 초록이면 회귀=버그.
- 과학: 가설은 통과되지 않고 **기각 / 부분지지 / 추가증거 대기**를 오감. 새 데이터가
  이전 결론을 뒤집는 것은 *결함이 아니라 정상 과학*(베이지안 갱신, 재현 실패).
- 치명적 부작용(sw-assumptions A13): `spec-workflow.md:241` "Test coverage dropping"을
  *정체/발산 신호*로 보아 재계획을 트리거 → harness가 **null result(효과 없음, 유효한
  결과)를 "stuck"으로 오인**해 개입을 강요. 과학적으로 해롭다.
- 결론: 상태기계를 단조 하강에서 *증거 누적에 따른 신뢰도 갱신*(상승·하강 양방향 정상)
  으로 재설계해야 함. `IsImproved`/`IsStagnant`/`allow_regression` 의미가 모두 깨짐 → 심층.

## Q2c — TDD의 순서강제는 pre-registration에 매핑되나?

**답: 부분적으로만. "결과를 보기 전에 검증 기준을 먼저 고정한다"는 정신은 RED-first와
pre-registration이 공유한다. 그러나 추가 메커니즘(데이터 누출 방지, 탐색/확증 분리,
가설-분석계획의 통계적 구체화)이 전부 빠져 있어 그대로는 매핑 불가.**

- 공유점: `spec-workflow.md:190` RED "Write a failing test … Verify it fails" =
  *구현(결과)을 보기 전에 성공 기준을 명문화*. pre-registration도 *데이터를 보기 전에
  가설·분석계획을 고정*. 둘 다 사후 합리화(p-hacking/HARKing) 방지 의도.
- 갭 1 (누출 방지 부재): harness엔 "테스트가 구현을 미리 엿보지 못하게" 같은 장치가
  없음(테스트=결정론적 명세라 누출 개념 자체가 없음). 과학은 *분석자가 결과를 보고
  분석을 바꾸는 것*을 막아야 함 — 별도 메커니즘 필요.
- 갭 2 (탐색/확증 분리 부재): TDD엔 "이건 탐색용, 이건 확증용" 구분이 없음. 과학
  pre-registration의 핵심은 *확증적 분석과 탐색적 분석의 명시적 분리*.
- 갭 3 (기준의 성격): RED의 "기준"은 boolean assert. pre-reg의 "기준"은 *통계 모델 +
  결정 규칙*(예: "베이즈 인수 >10이면 지지"). EARS(`spec-workflow.md:147`)의 "shall"
  요구사항으로는 통계 가설을 표현 못 함(sw-assumptions A8).
- 결론: SPEC 5종 산출물을 pre-registration 템플릿(가설/예측/표본·검정력/분석계획/
  정지규칙)으로 *재해석*은 가치 있고 가능하나, EARS·acceptance 골격은 재작성 수준.

---

## Self-Verify Loop / Ralph Engine / TRUST 5 — 종합 판정

| 대상 | SW 의미 (현재) | 과학 매핑 가능성 | 비용 |
|------|----------------|------------------|------|
| **Self-Verify Loop** | 에러 0까지 코드 수정 반복 | 루프 *구조*(반복+피드백+수렴판정)는 재사용 가치 큼; *피드백 내용*은 교체 필요 | 중간 |
| **Ralph Engine** (`DecisionEngine`) | maxiter/gate/stagnant 우선순위 결정 | 결정 *프레임*은 유용; gate·stagnant 정의는 재작성 | 중간 |
| **FeedbackGenerator** (인터페이스) | go test+vet 출력 파싱 | **인터페이스라 과학 메트릭 생산자로 깔끔히 교체 가능** — 긍정 | 낮음 |
| **MeetsQualityGate** | 정수 0 논리곱 | 신뢰도 평가로 *의미 재정의* 필요 | 높음(심층) |
| **TRUST 5 "Tested"** | unit_tests_pass ∧ lsp_errors==0 (`quality.yaml:46-49`) | "검증됨"의 의미를 재현성/유의성으로 재정의 | 높음(심층) |

**핵심 통찰:** 루프의 *골격*(controller + DecisionEngine + FeedbackGenerator 인터페이스,
반복·정체감지·수렴·최대반복·인간개입 분기)은 과학 루프에도 그대로 쓸 만한 **잘 설계된
제어 구조**다. 갈라지는 건 *세 곳의 의미*뿐:
1. `Feedback`이 측정하는 것 (정수 카운트 → 연속·확률 메트릭)
2. `MeetsQualityGate`의 수렴 정의 (0 논리곱 → 신뢰도 임계)
3. 단조성 가정 (`IsImproved`/`allow_regression` → 양방향 정상)

즉 **"루프 인프라는 fork로 살리고, 판정 로직 3곳을 갈아끼우는" 전략이 기술적으로
성립**한다. 이것이 Q2(전체)·Q6(Ralph 재활용)·Q16(stochastic)의 교차 결론이며,
fork 비용 견적의 가장 구체적인 근거 — reusable.md에서 이 인터페이스 경계를 확정한다.

### 미검증/확신 못 함
- `DecisionEngine`/`FeedbackGenerator` 외에 루프가 SW 가정에 *암묵적으로* 의존하는 곳
  (예: controller.go의 phase enum이 RED/GREEN/REFACTOR에 묶였는지) — controller.go 정독 필요.
- LSPDiagnostics 의존이 루프 전체에 얼마나 깊은지 (LSP 없는 과학 언어에서 graceful
  degradation 되는지 — SKILL.md:65는 "fallback to linters" 언급, 과학용은 그것도 부재).
- TRUST5의 나머지 4차원(Readable/Unified/Secured/Trackable)의 과학적 의미 — Day 4.

---

## [Day 4 pre-verification, 2026-05-26] 사용자 메타검증 — "3곳 교체" 프레이밍 수정

사용자 요구로 reusable.md 전에 3개 검증 수행. **결과: 프레이밍을 보강·수정한다.**

### 검증 1 — Feedback/MeetsQualityGate 호출처 (→ 6-20곳 구간: "3곳 + fanout")
- `Feedback` 타입 참조: **22곳**(non-test), 대부분 `internal/loop` 내부. 외부 소비자는
  `internal/ralph/engine.go`(교체대상 엔진)·`internal/hook/post_tool.go:498`(생산자).
- `MeetsQualityGate` non-test 호출처: **단 1곳** (`internal/ralph/engine.go:52`). ✓ 좁음.
- `IsImproved`/`IsStagnant` non-test 호출처: **단 1곳** (`internal/ralph/engine.go:64`). ✓ 좁음.
- **그러나** "SW 성공 = tests pass ∧ coverage ∧ lint 0" 의미는 루프 밖에서 *독립
  재구현*돼 있다 — 평행 게이트 fanout:
  1. `internal/loop/feedback.go:43-73` (루프 수렴 판정 — 본문의 "3곳")
  2. `internal/ralph/engine.go:138-189` (`ClassifyFeedback` — `fb.TestsFailed>5` 등으로
     에러 분류/심각도; **본문 3곳에 포함 안 됐던 4번째 소비자**)
  3. `internal/core/quality/trust.go:562,627-630` (**TRUST5 별도 게이트** —
     `MaxLintErrors` 비교, "run phase requires zero lint errors")
  4. `internal/lsp/hook/gate.go:216` (**LSP hook 게이트** — `counts.LintErrors > Run.MaxLintErrors`)
  5. `internal/hook/quality/gate.go:80-131` (**언어별 toolchain 게이트** — Day 2 A5)
  6. `internal/hook/teammate_idle.go:128-165` (**team idle 커버리지 게이트**)
- **수정된 프레이밍:** 루프의 판정 함수 자체는 호출처가 좁다(각 1곳, 교체 쉬움). 그러나
  *"무엇이 좋은 결과인가"라는 SW 가정은 최소 5-6개 독립 서브시스템에 평행 구현*돼 있어,
  과학용으로 바꾸려면 루프 3곳 + **평행 게이트 5-6곳**을 함께 다뤄야 한다. → "3곳 교체"는
  과소평가. 정확히는 **"루프 판정 3함수(교체 용이) + 평행 품질게이트 5-6곳(중복 재구현)"**.

### 검증 2 — 새 필드를 *채우는 계산 인프라* 비용 (별도 섹션 — 누락됐었음)
- **통계 계산 인프라는 존재하지 않는다.** `bayes|posterior|effect size|p-value|CI|mcmc`
  grep 결과 0건(코드). `Feedback`에 `BayesFactor`/`EffectSize` *필드 추가*는 사소하나,
  그것을 *계산하는 엔진*(통계 검정 러너, 모델피팅 평가기, 효과크기 추정기, 사후분포
  계산)은 **전무 → scratch 작성 필요**.
- `FeedbackGenerator` 인터페이스(`internal/loop/state.go:160` `Collect`)가 플러그 지점을
  깔끔히 제공하는 건 맞지만, **플러그에 꽂을 계산기 자체가 fork에 없다**. 이 비용은
  reusable.md/REPORT의 fork 견적에 *별도 항목*으로 계상한다.
- **반전 발견(긍정):** `internal/research/` 는 SW 리서치가 아니라 **"Self-Research
  System"** — `experiment/types.go:1-2`("experiment loop state machine … baseline
  measurement, mutation application, evaluation, scoring"). 상태기계
  `Idle→Baseline→Mutating→Evaluating→Scoring→Complete`(:16-26) + `Decision
  keep/discard`(:30-38) + `Experiment{Hypothesis}`(:50-53) + `eval/`·`observe/`·
  `safety/`(frozen/canary/limiter). 즉 **가설→베이스라인→변이→평가→점수→채택/기각의
  experiment 루프가 이미 존재**(harness 자기진화용). Day 1 architecture.md의 "research =
  SW 리서치" 메모는 부정확 → 정정 필요. Q5/Q6/Q17 재평가 대상. 단 eval 점수가 SW-특화인지
  일반인지는 미확인(Day 4 reusable에서 `eval/engine.go` 정독).

### 검증 3 — "null=stuck" 해결에 controller 골격 수정 필요한가? (→ 불필요, 골격 무손상 유지)
- `internal/loop/controller.go:289-339`: controller는 feedback을 `c.feedback.Collect()`
  (인터페이스)로 수집, 판정을 `c.engine.Decide()`(인터페이스)에 위임, generic action
  (`Converge/Continue/Abort/RequestReview`, `state.go:36-39`)만 처리. **controller 자체는
  test-pass·커버리지·단조성 의미를 내장하지 않는다.**
- "null=stuck" 문제의 실제 위치: (a) `internal/ralph/engine.go:62-70` `IsStagnant→
  ActionConverge` — **교체대상 엔진 안**, (b) `spec-workflow.md:239-243` 재계획 게이트 —
  **agent 프롬프트 규칙**(코드 아님). 둘 다 controller 밖.
- **결론: controller.go 골격은 무손상 재사용 가능** — 엔진(swappable) + 프롬프트 규칙만
  고치면 됨. "골격 fork" 주장 이 부분은 **유지**.
- **단서(경미):** phase enum이 `analyze→implement→test→review`(`state.go:28-47`)로
  *약하게 SW-편향*("implement"/"test"). RED/GREEN/REFACTOR 하드코딩은 아님 — 과학용
  `gather→model→evaluate→review`로 라벨 재정의 가능(저비용). 골격 차단요인 아님.

### Day 4 pre-verification 종합 (수정된 프레이밍)
- **유지**: controller 골격 + FeedbackGenerator/DecisionEngine 인터페이스는 재사용 가능(검증3).
- **보강**: "판정 3곳"이 아니라 "루프 3함수 + 평행 품질게이트 5-6곳"(검증1).
- **추가비용**: 과학 메트릭을 *계산하는 인프라*는 fork에 전무 → scratch(검증2). 단
  `internal/research`의 experiment 루프가 의외의 출발점일 수 있음(긍정, 추가 조사).
- → reusable.md는 이 수정된 인식 위에서 작성한다.

---

## [Day 7 정정, 2026-05-26] 검증1·3 — "4중 방어선" 주장은 비관 편향이었다

사용자 메타검증(검증1 비대칭성 + 검증3 비관편향 의심)으로 Day 5 B2의 "null=stuck
prompt+engine+hook+rule **4중 방어선**" 주장을 코드로 재검토. **결과: 과대계상이었다.**

### 검증1 — 4층은 독립 강제자가 아니다 (비대칭)
- **engine (유일한 hard 강제자)**: `internal/ralph/engine.go:62-71` — stagnation→converge.
  **단 `if e.cfg.AutoConverge`로 gating**(`:62`). 기본값 true(`internal/config/defaults.go:280`)
  이나 `yaml:"auto_converge"`(`types.go:158`)로 **config 토글 가능**.
- **hook (다른 가정 강제, null=stuck 아님)**: `internal/hook/` grep 결과 stagnation/
  no-progress/IsStagnant **0건**. hook(gate.go)은 *완료=binary pass*(tests pass/lint)를
  block/pass로 강제할 뿐 — 이는 별개 가정(MeetsQualityGate). **Day5에서 두 가정을 혼동**.
- **prompt + rule (advisory text)**: `manager-develop.md:221`은 "## Ralph-Style LSP
  Integration" 하위의 *engine 동작 설명*("stale after 5 no-progress"). agent가 독립 계산
  하지 않음 — engine이 함. `spec-workflow.md:239` 재계획 게이트도 LLM 대상 지침(soft).

→ **null=stuck의 hard 강제는 사실상 engine 1곳**(게다가 config-gated). 나머지는 (a) 다른
가정을 강제하거나(hook), (b) engine을 묘사하는 advisory text(prompt/rule)였다.

### 검증3 — 우회 시나리오 2개 (비관 편향 자가반증)
- **시나리오 A (config 토글, XS)**: `ralph.yaml`에 `auto_converge: false` → engine의
  stagnation→converge 분기 자체가 skip(`engine.go:62`), 루프는 MaxIter까지 continue.
  **코드 0줄, null=stuck의 hard 강제 소멸.**
- **시나리오 B (engine 교체, M, 기존 swap과 공유)**: `DecisionEngine` 구현을 "no improvement
  =유효한 null result(미수렴 아님)"로 교체. 인터페이스라 깔끔.
- (advisory text reword는 LLM soft 행동용으로 S, A/B 후 보조적.)

### 정정된 결론
- Day 5 "4중 방어선 → fork 두뇌부 비쌈(L)"은 **비관 편향**. 실제 null=stuck 제거 = **XS-S**
  (config 토글 + advisory reword), engine 교체는 어차피 하는 작업.
- **단 한정**: 이 정정은 *stagnation(null=stuck)* 가정에 국한. *binary 완료*(MeetsQualityGate)
  는 engine+hook+trust.go 등 **평행 5-6곳**에 실재(Day4-pre 검증1 유효) — 그건 여전히 다층.
- **메타**: Day4 fork-낙관 편향 + Day5 fork-비관 편향이 *둘 다* 발견됨 → CC 추정은 한쪽으로
  치우친 게 아니라 **양방향 노이즈**. REPORT 권고 신뢰도를 낮춰야 함(meta-eval.md, Q19).
