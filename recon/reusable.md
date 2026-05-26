# reusable.md — fork/scratch 무관 그대로 쓸 만한 인프라

> 답하는 질문: **Q3**(인프라 독립추출 가능?), 부분 **Q6**(Ralph 재활용), **Q10**(외부의존),
> **Q18**(외부도구 통합 패턴). 분석 기준 repo HEAD. 누적식. Day 4.
> 평가 3축: **(a) 무엇** / **(b) 과학용 가치** / **(c) 독립 추출성(internal 의존성 기반)**.
>
> 추출성 근거 = `grep "modu-ai/moai-adk/internal/"` 패키지별 의존성 맵 (Day 4 측정).

---

## [Day 4, 2026-05-26] 의존성 기반 추출성 등급

### 등급 정의
- **Tier A (lift-and-use)**: internal 의존성 **0**. 패키지째 복사 가능.
- **Tier B (leaf)**: leaf 패키지(config/defs 등)만 의존. 소폭 수정으로 추출.
- **Tier C (개념만 재사용)**: 코드는 SW에 결합 — *패턴/인터페이스*만 가져오고 재구현.
- **Tier D (SW 특화, 인프라 아님)**: 재사용 부적합.

---

## Tier A — 완전 독립 (internal 의존성 0, 그대로 추출)

### RA1. `internal/worktree` (489 LOC)
- **(a)** git worktree 생성/정리/검증 관리자. `moai worktree new/done/verify`.
- **(b)** **과학용 가치 높음.** 파라미터 스윕·다중 가설·재현 실험을 *격리된 트리에서
  병렬* 실행. 한 실험이 다른 실험의 작업트리를 오염시키지 않음.
- **(c)** **의존성 0 → 그대로 추출.** git 바이너리에만 의존.

### RA2. `internal/telemetry` (723 LOC)
- **(a)** 토큰/사용량 메트릭을 `.moai/evolution/telemetry/usage-YYYY-MM-DD.jsonl`로 기록
  (`recorder.go:30,47`; async_recorder.go). 일자별 집계·리포트.
- **(b)** **높음.** 비싼 과학 에이전트 run의 토큰/비용 추적은 그대로 필요. 포맷 무관.
- **(c)** **의존성 0 → 그대로 추출.** 가장 깨끗한 재사용 후보 중 하나.

### RA3. `internal/session` (5753 LOC: registry/store/state/task_ledger + unix/win lock)
- **(a)** 세션 상태 영속화 + 멀티세션 레지스트리(`registry.go`, OS별 파일락) + task ledger.
- **(b)** **높음.** 장시간 연구 세션의 상태 보존·재개·핸드오프, 동시 세션 충돌 방지.
- **(c)** **의존성 0 → 그대로 추출.** 단 일부 의미(SPEC 스코프 등)는 라벨 재정의.

### RA4. `internal/sandbox` (986 LOC)
- **(a)** `SandboxBackend interface { Exec(opts, cmd) }` + Bubblewrap/Docker 백엔드
  (`context.go:95`, `bubblewrap.go:52`, `docker.go:46`).
- **(b)** **높음.** LLM이 생성한 분석 코드(임의 Python/R)를 *격리 실행*하는 1급 프리미티브.
  과학 harness의 안전 실행에 직접 유용.
- **(c)** **의존성 0 → 그대로 추출.** Q18의 실행 프리미티브 후보(아래 Q18 참조).

### RA5. `internal/tmux` (632), `internal/git` (627), `internal/mcp` (443)
- **(a)** tmux 멀티페인(CG 모드), git 작업 래퍼, MCP 서버 통합.
- **(b)** tmux=중(병렬 에이전트 원할 때), git=중(provenance, 단 데이터버전은 DVC류 별도),
  mcp=중상(외부 데이터/도구 연결).
- **(c)** **모두 의존성 0 → 그대로 추출.**

## Tier B — leaf 의존 (소폭 수정 추출)

### RB1. `internal/config` (5184 LOC) — 의존: `defs`만
- **(a)** 28개 YAML 섹션 로더 + 기본값 + struct 매핑 + CI 대칭성 가드.
- **(b)** **높음(메커니즘)**. 설정 로딩 *기계*는 재사용; 섹션 *스키마*(quality/lsp/mx 등)는
  과학용으로 재작성. "섹션 추가 5단계 절차"가 잘 문서화됨(settings-management.md).
- **(c)** Tier B. defs만 의존 → 추출 용이. 단 SW 섹션 스키마는 폐기·교체.

### RB2. `internal/template` (2446 LOC) — 의존: `config`, `manifest`
- **(a)** go:embed 기반 `.claude/.moai` 스캐폴딩 배포(`moai init`). + `model_policy.go`.
- **(b)** **중.** 프로젝트 초기화 스캐폴딩 메커니즘은 유용; 배포되는 *콘텐츠*(agent/skill
  템플릿)는 전면 재작성.
- **(c)** Tier B. config/manifest 의존.

### RB3. `internal/statusline` (3350 LOC) — 의존: config/core/defs/tui
- **(a)** 토큰 사용량·모델·진행 statusline 렌더(bubbletea/tui).
- **(b)** **중.** 토큰/비용/진행 표시는 UX로 유용. 표시 *항목*만 과학용으로.
- **(c)** Tier B.

## Tier C — 개념/인터페이스만 재사용 (코드는 SW 결합)

### RC1. 루프 골격 — `internal/loop` controller + `DecisionEngine`/`FeedbackGenerator` 인터페이스
- **(a)** `LoopController`(controller.go) + 2개 swappable 인터페이스(`state.go:148,160,165`).
  반복·정체감지·수렴·최대반복·인간개입(`ActionContinue/Converge/Abort/RequestReview`).
- **(b)** **높음(골격).** tdd-mismatch.md 결론대로 *제어 구조*는 과학 루프에 유효. Day 4
  pre-verification 검증3: controller는 판정을 인터페이스에 위임 → **골격 무손상 재사용**.
- **(c)** **Tier C-상.** controller는 거의 그대로; 단 (1) `FeedbackGenerator` 구현
  (go_feedback.go)은 과학 메트릭 생산자로 교체, (2) `RalphEngine`의 gate/stagnant 의미
  교체, (3) phase enum(analyze/implement/test/review) 라벨 재정의. **+ 평행 품질게이트
  5-6곳(검증1)은 별개로 정리 필요.**

### RC2. hook dispatcher — `internal/hook` (16823 LOC)
- **(a)** Claude Code 11개 이벤트(SessionStart/End, Pre/PostToolUse, Stop, SubagentStop,
  Notification, UserPromptSubmit, PreCompact, TeammateIdle, TaskCompleted) 디스패처 +
  observer 패턴(`router.go`, `observer.go`).
- **(b)** **개념 높음** — 관측/제어 평면(observability + control)은 과학 harness에도 필수.
- **(c)** **Tier C(주의).** 통념과 달리 **그대로 추출 불가** — `internal/hook`는 16개
  패키지(spec/loop/mx/lsp/evolution/harness/workflow/astgrep/merge/migration/tmux 등)에
  결합된 *통합 허브*다. 재사용 가능한 건 **router/observer 패턴 + JSON I/O 계약 + 이벤트
  vocabulary**이지 패키지 자체가 아님. → 패턴 차용 후 재배선.

### RC3. 모델 라우팅 — `internal/template/model_policy.go`
- **(a)** High/Medium/Low → opus/sonnet/haiku 티어(`model_policy.go:13-26`), 에이전트별 할당.
- **(b)** **중상(개념).** "작업 비용 티어별로 싼/비싼 모델 배정"은 과학용에도 유용
  (탐색=haiku, 핵심 추론=opus). 단 *에이전트별 매핑표*는 MoAI 카탈로그 전용 → 재작성.
- **(c)** Tier C. 개념·enum은 재사용, 매핑은 교체.

### RC4. experiment 루프 — `internal/research/*` ("Self-Research System")
- **(a)** `experiment/`(상태기계 Idle→Baseline→Mutating→Evaluating→Scoring→Complete,
  `Experiment{Hypothesis}`, `Decision{keep/discard}`) + `eval/`(EvalEngine) +
  `observe/`(패턴) + `safety/`(frozen/canary/limiter).
- **(b)** **잠재 높음 but 주의.** 가설→변이→평가→채택/기각 *루프 구조*는 과학 실험에
  구조적으로 가장 가깝다(harness 자기진화용으로 만들어졌지만). **단 한계 발견**:
  `eval/engine.go:11` `Evaluate(suite, results map[string]bool)` — **평가 입력이
  boolean 기준 맵**이고 `EvalSettings.TargetScore float64`(types.go:55)로 가중합≥임계.
  즉 experiment 루프조차 *가중 boolean 기준 → 점수 임계*라 **연속·확률 통계가 아님**.
  Q2a의 binary 한계가 여기에도 적용됨.
- **(c)** **Tier C.** 상태기계·safety 레일은 재사용 가치 큼; eval의 boolean-기준 채점은
  통계 평가로 교체 필요. → Q6 부분답: Ralph보다 이쪽이 과학 루프의 더 나은 출발점이나,
  채점 의미는 동일하게 갈아야 함.

## Tier D — SW 특화 (인프라로 재사용 부적합, 폐기/교체)
`internal/lsp`(6322), `internal/spec`(3924, EARS/frontmatter), `internal/mx`(2087, 코드구조
태그), `internal/constitution`(2121, TRUST5 가드), `internal/astgrep`(1536), `internal/merge`,
`internal/github`(PR), `internal/design`(.pen). — sw-assumptions.md 참조. 과학용 재작성/폐기.

---

## 질문별 답

### Q3 — 인프라 독립추출 가능한가? **부분적으로 강하게 yes.**
- **Tier A 8개 패키지(worktree/telemetry/session/sandbox/tmux/git/mcp/+shell)는 internal
  의존성 0 → 패키지째 추출 가능.** 이것이 fork의 가장 확실한 이득.
- Tier B(config/template/statusline)는 leaf 의존이라 소폭 수정 추출.
- **단 "hook dispatcher 그대로 추출" 통념은 틀림**(RC2) — 통합 허브라 16개 의존. 패턴만.

### Q10 — 외부 의존 결합도
- 강결합: **Claude Code 자체**(hook 이벤트 계약, settings.json, statusline, MCP 로딩,
  effortLevel/Adaptive Thinking 등 버전 민감 — coding-standards.md 호환표). GLM/tmux는
  CG 모드 한정(선택적). sandbox는 bubblewrap/docker 외부 바이너리 의존(가용성 체크 있음).
- 과학용 fork도 Claude Code 위에 올리는 한 hook/settings 계약은 그대로 상속 → 이득.

### Q18 — 외부 도구(solver/통계패키지) 통합 표준 패턴? **대체로 ad-hoc + sandbox 프리미티브.**
- **일반화된 tool-runner 추상화는 없다.** `internal/shell`은 셸 *감지/설정* 유틸
  (DetectShell/AddEnvVar/IsWSL, `shell/detect.go`,`config.go`)이지 명령 실행기가 아님.
- 실제 도구 실행은 *ad-hoc* — 예: `internal/loop/go_feedback.go`가 `exec`로 go test 직접
  호출. 언어별 toolchain도 `hook/quality/gate.go`에 하드코딩(Day 2 A5).
- **유일한 일반 실행 프리미티브 = `internal/sandbox`의 `SandboxBackend.Exec`**(RA4). 과학
  harness가 R/Julia/solver를 호출하려면 *이 위에 generalized tool-runner를 새로 얹어야*
  한다(scratch). → Q18은 "표준 패턴 부재, sandbox.Exec가 토대".

---

## Day 4 reusable 종합
- **확실한 자산(Tier A, 그대로)**: worktree, telemetry, session, sandbox, tmux, git, mcp.
  → fork의 핵심 이득은 *이 운영 인프라를 공짜로 얻는 것*.
- **메커니즘 재사용(Tier B)**: config 로더, template 스캐폴딩, statusline.
- **골격 재사용(Tier C)**: loop controller + 인터페이스, hook 패턴, 모델 티어 개념,
  research experiment 상태기계.
- **재작성/폐기(Tier D)**: lsp/spec/mx/constitution/astgrep/github/design.
- **scratch 필수(인프라 부재)**: 통계 계산 엔진, generalized 외부 tool-runner, 연속·확률
  평가 로직 — fork든 scratch든 *새로 만들어야* 함(검증2).

### 미검증/확신 못 함
- Tier A 패키지들의 *코드 품질/테스트 커버리지*(Q9) — fork 유지보수 비용 직결, 아직 미측정.
- `internal/evolution`(1239)·`internal/harness`(6795)의 재사용성 — 아직 표면만.
- sandbox가 macOS/Windows에서 얼마나 동작하는지(bubblewrap=linux, docker=크로스).

---

## [Day 7, 2026-05-26] 검증2 — Tier A vendoring integration 비용 (vs fork 추출)

사용자 검증2: "scratch + Tier A 7개 vendoring" 비용을 fork 추출과 정량 비교.

### transitive 의존 측정 (7개 패키지)
| 패키지 | internal 의존(transitive) | external 의존 |
|--------|--------------------------|---------------|
| worktree | **0** | (stdlib only) |
| telemetry | **0** | (stdlib only) |
| session | **0** | `golang.org/x/sys`(unix/windows 파일락) |
| sandbox | **0** | (stdlib only) |
| tmux | **0** | (stdlib only) |
| git | **0** | (stdlib only) |
| mcp | **0** | (stdlib only) |

→ 7개 모두 internal cross-dep 0(direct+transitive). external은 session의 x/sys 하나(표준 lib).

### vendoring 비용 per 패키지
- 파일 복사 + import path 재작성: `github.com/modu-ai/moai-adk/internal/X` →
  `<new-module>/internal/X`. Go `internal/` 규칙상 모듈 넘어 import 불가하므로 **복사+경로
  재작성 필수** — 단 cross-dep 0이라 패키지별 독립 처리(mechanical, 충돌 없음). **XS-S/패키지.**
- session만 go.mod에 `golang.org/x/sys` 추가(`go get`, trivial).
- **인터페이스 mismatch 없음**(다른 moai 패키지 의존 0이므로).

### fork 추출 vs B′ vendoring 정량 비교
| | fork (A) | B′ vendoring |
|---|---|---|
| Tier A 획득 | 모듈 통째 보유 → **추출 비용 0**(in-place 사용) | 복사+경로재작성+x/sys → **S** |
| 차이 | — | +S (작음) |

→ **사용자 가설 확정**: 인프라 획득 비용은 fork≈B′(둘 다 작음). **B′은 인프라 차원에서
사실상 lite fork.** 두 경로의 진짜 차이는 인프라가 아니라 **나머지 처리 방향**:
- fork = 전체 상속 후 Tier C/D *프루닝* + 두뇌부 *디톡스*(subtractive).
- B′ = 빈 모듈 + Tier A만 *추가* + 두뇌부 *신규*(additive).
- 그런데 디톡스(최소 null=stuck)는 tdd-mismatch Day7 정정대로 XS-S(과거 L 주장은 비관편향).
→ **A와 B′의 기술적 격차는 통념·내 초안보다 더 작다.** 결정은 기술이 아니라 비기술(U-C)
  + 디톡스(subtractive) vs 신규(additive) 선호 + MVP(U-B3)로 넘어간다.
