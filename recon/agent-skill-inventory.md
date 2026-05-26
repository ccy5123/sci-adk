# agent-skill-inventory.md — 8 agents + 26 skills 과학용 재분류

> 답하는 질문: **Q4**(재활용/수정/폐기/신규 비율). 분석 기준 repo HEAD (8 agents/26 skills).
> 누적식. Day 4.
>
> **사용자 검토용**: CC 분류와 사용자 분류가 *다른 항목*이 진짜 정보. `★경계`로 표시한
> 항목이 CC가 가장 덜 확신하는 곳 — 우선 검토 권장.

---

## 분류 기준 (명시적 — 이 기준에 동의하는지부터 봐주세요)

| 카테고리 | 판정 규칙 |
|---------|-----------|
| **재활용 (R)** | 과학용에서 *의미·구조 변경 거의 없이* 동작. SW-중립 인프라/오케스트레이션/메타. |
| **수정 (M)** | *역할·골격은 유지*하되 SW 의미(test/coverage/lint/EARS/PR)를 과학 의미로 교체. 변경량 대략 절반 이하. |
| **폐기 (D)** | SW 도메인 전용(web/backend/design/test 등)이라 과학용 불필요. 또는 dev-only. |
| **신규 (N)** | 기존에 없어 *새로 만들어야* 하는 과학 전용 컴포넌트. → 별도 섹션. |

경계 판정 원칙: "역할 자체가 도메인 무관인가?"(→R) vs "역할은 살되 SW 판정/산출물이
박혔나?"(→M) vs "도메인이 SW 그 자체인가?"(→D).

---

## AGENTS (repo `.claude/agents/`)

### MoAI retained (7) + Anthropic 내장 Explore (8 effective)

| Agent | 한 줄 요약 (frontmatter 근거) | CC 분류 | 근거 |
|-------|------------------------------|:------:|------|
| `manager-spec` | SPEC(spec/plan/acceptance) 작성, status:draft 발행 | **M** | 계획서 작성 역할 유지 → pre-registration 작성으로 재해석. EARS/acceptance 의미 교체(sw-assumptions A8). |
| `manager-develop` | run-phase 구현 파일 작성, cycle_type ddd/tdd/autofix | **M** | 구현 오케스트레이션 골격 유지, TDD/DDD 사이클 → 분석/모델링 사이클 교체(tdd-mismatch). 핵심 에이전트. |
| `manager-docs` | sync-phase CHANGELOG/README/docs 동기화 | **M** | 문서 동기화 역할 유지 → 연구노트/결과문서로; CHANGELOG/README 산출물 교체. |
| `manager-git` ★사용자수정 | commit/branch/PR/merge/release | **M** | ~~R~~→**M** (사용자 2026-05-26). "PR=완료" 모델이 과학 provenance(SPEC↔commit↔evidence↔paper section)와 충돌. git 기계는 중립이나 *완료 워크플로우 의미*가 박힘 → 메타데이터 추적 추가 필요. |
| `plan-auditor` | 적대적 plan 감사관 (SPEC 결함 탐지, 사전) | **M** | 적대적 감사 역할은 과학에 *매우* 적합(연구설계 비판/사전등록 검토). 감사 *기준*만 과학으로. |
| `evaluator-active` | 회의적 post-impl 평가자, acceptance 대비 검증, 4차원 점수 | **M** | 회의적 평가자 = 재현성/통계 타당성 검증으로 재해석. 4차원→과학 차원. 가치 높음. |
| `builder-harness` | agent/skill/plugin/hook/MCP 메타 스캐폴딩 생성 | **R** | 메타 빌더는 도메인 무관 → 과학 에이전트도 생성. 생성 *템플릿*만 과학용. |
| `Explore` (내장) | read-only 코드베이스 탐색 | **R** | Anthropic 내장, 도메인 무관. |

### local dev-only (2) — 배포 안 됨

| Agent | 요약 | CC 분류 | 근거 |
|-------|------|:------:|------|
| `github-specialist` | moai-adk 메인테이너용 GitHub 이슈/PR (dev-only) | **D** | 사용자 프로젝트 미배포, moai-adk 자체 개발 전용. |
| `release-update-specialist` | CC 업스트림 변경 추적 (dev-only) | **D** | 동상. |

**Agents 집계 (effective 8, dev-only 제외):** ~~R=3, M=5~~ → **R=2, M=6, D=0** (manager-git
R→M 반영). → **수정 우세 강화.**

---

## SKILLS (repo `.claude/skills/`, 26)

### Foundation (4)
| Skill | 요약 | 분류 | 근거 |
|-------|------|:----:|------|
| `moai-foundation-cc` | Claude Code 작성 키트(skills/agents/hooks/plugins/MCP) | **R** | CC 작성 지식 도메인 무관 — 과학 harness 구축에도 필요. |
| `moai-foundation-thinking` | 창의 프레임워크 + First Principles + Adaptive Thinking | **R** | 사고 도구 도메인 무관, 과학 추론에 직접 유용. |
| `moai-foundation-core` | TRUST5 + SPEC + delegation + progressive disclosure | **M** | delegation/progressive disclosure 골격 유지; TRUST5/SPEC 의미 교체. |
| `moai-foundation-quality` ★사용자수정 | TRUST5 강제, 린팅, 코드 품질 | **D+N** | ~~M~~→**폐기+신규** (사용자 2026-05-26). "코드 품질"은 과학에서 의미 ≈0. 통계검정/단위검증/재현성검사는 *본질이 다른 함수 집합*. "수정" 라벨은 SW 가정 잔존 위장 → 폐기 후 N(통계 품질)로 신규. |

### Workflow (10)
| Skill | 요약 | 분류 | 근거 |
|-------|------|:----:|------|
| `moai-workflow-worktree` | 병렬 SPEC worktree 격리 | **R** | 병렬 격리 = 파라미터 스윕/다중 가설(reusable RA1). 거의 그대로. |
| `moai-workflow-loop` | Ralph 엔진, LSP/ast-grep 피드백 루프 | **M** | 루프 골격 유지, 피드백을 과학 메트릭으로 교체(reusable RC1, tdd-mismatch). |
| `moai-workflow-spec` | EARS/acceptance/Plan-Run-Sync | **M** | pre-registration 재해석(Q2c). |
| `moai-workflow-project` | 프로젝트 관리/docs gen/JIT docs | **M** | 관리 골격 유지, 산출물 교체. |
| `moai-workflow-gan-loop` ★사용자수정 | Builder-Evaluator GAN, 디자인 품질 4차원 점수 | **D** | ~~M~~→**폐기** (사용자 2026-05-26). GAN loop는 *미적 평가(점수 임계)* 본질. 과학 평가는 통계 검정 — 수정으로 본질 못 바꿈. (CC가 루프 '구조' 재사용성을 과대평가했음.) |
| `moai-workflow-tdd` | RED-GREEN-REFACTOR | **D** | SW test-first 전용. 과학 등가물은 신규(N) hypothesis-driven. |
| `moai-workflow-ddd` | ANALYZE-PRESERVE-IMPROVE (레거시 리팩토링) | **D** | 레거시 코드 전용. |
| `moai-workflow-testing` | DDD 테스팅/characterization/커버리지 | **D** | 테스트 전용. |
| `moai-workflow-ci-loop` | gh pr checks 감시 + 자동수정 | **D** | CI 전용. |
| `moai-workflow-design` | Claude Design 핸드오프/DTCG 토큰 | **D** | 디자인 전용. |

### Domain (8)
| Skill | 요약 | 분류 | 근거 |
|-------|------|:----:|------|
| `moai-domain-research` ★보류해소 | 시장/생태계 리서치(brain Phase 3), 병렬 WebSearch+Context7, 인용·한계 명시 research.md | **M** | **body 확인(SKILL.md:1-55)**: framing은 "market-analysis/competitive landscape"(순수 framing이면 폐기감). 그러나 *메커니즘*(병렬 인용 검색 + Research Limitations 섹션 + 부분실패 허용 + tech-neutral)은 **과학 문헌종합에 1:1 가까움** → 순 변경량으로 **수정**. ※framing만 보면 폐기, 메커니즘 보면 재활용 — 사용자 판단 여지. |
| `moai-domain-ideation` | Lean Canvas, SPEC 분해, Diverge-Converge | **M** | 수정 유지(사용자 동의). **의미 강화 필수**: "ideation" → **"hypothesis generation"**으로 재정의. Diverge-Converge = 가설 generate-and-rank(Q17). Lean Canvas는 폐기. |
| `moai-domain-database` ★사용자수정 | Postgres/Mongo/Redis 스키마/쿼리 | **M** | ~~D~~→**M** (사용자 2026-05-26). 과학 데이터(실험 결과/시뮬레이션 출력/문헌 메타데이터) 저장은 *실재 요구*. OLTP framing → 과학 데이터 영속/버전으로 수정. (CC가 데이터 영속 요구를 과소평가했음.) |
| `moai-domain-backend` | API/DB/microservices | **D** | 백엔드 SW 전용. |
| `moai-domain-frontend` | React/Next/Vue UI | **D** | 프론트 전용. |
| `moai-domain-copywriting` | 브랜드 카피 | **D** | 마케팅 전용. |
| `moai-domain-brand-design` | 브랜드 비주얼 디자인 | **D** | 디자인 전용. |
| `moai-domain-design-handoff` | Claude Design 핸드오프 번들 | **D** | 디자인 전용. |

### Meta / Orchestrator / Design-system (4)
| Skill | 요약 | 분류 | 근거 |
|-------|------|:----:|------|
| `moai-meta-harness` | 프로젝트별 agent 팀 설계 + 스킬 생성(7-Phase) | **R** | 메타 하네스 생성기 도메인 무관 → 과학 harness 생성. 핵심 재사용. |
| `moai-harness-learner` ★경계 | harness 학습, Tier4 자동개선 제안 | **R** | 자기개선 학습 루프 도메인 무관. ★단 학습 신호가 SW 메트릭이면 M. 코드 확인 필요. |
| `moai` | 통합 오케스트레이터 라우터(서브커맨드 분배) | **M** | 라우터 골격 유지, 서브커맨드 과학용으로. |
| `moai-design-system` | 디자인 시스템/UI/UX 기반 | **D** | 디자인 전용. |

**Skills 집계 (26):** ~~R=5, M=9, D=12~~ → **R=5, M=8, D=13** (사용자 재분류 반영:
quality M→D[+N], database D→M, gan-loop M→D). 합 5+8+13=26.

---

## 신규(N) 필요 — 기존에 없는 과학 전용 컴포넌트 (별도)

reusable.md 검증2 + sw-assumptions 종합으로 도출. *fork든 scratch든 새로 만들어야* 함:
- **N1. 통계 평가 엔진** — p-value/effect size/CI/Bayesian posterior 계산 (현재 0건).
  ※`moai-foundation-quality` 폐기분이 여기로 이동(사용자 2026-05-26): "코드 품질" → "통계
  품질"(검정·재현성·표본 적정성)은 본질이 다른 함수 집합이라 수정이 아닌 신규.
- **N2. 가설 생성·우선순위화 스킬** — generate-and-rank (Q17). ideation의 Diverge-Converge가 씨앗.
- **N3. 실험 설계/사전등록 스킬** — 표본·검정력·정지규칙·탐색/확증 분리 (Q2c 갭).
- **N4. 과학 메트릭 FeedbackGenerator** — 루프 인터페이스 구현체(모델적합도/잔차/예측오차).
- **N5. generalized 외부 tool-runner** — R/Julia/solver/MCMC 호출 (Q18, sandbox.Exec 위에).
- **N6. 문헌 종합 스킬** — domain-research를 과학 문헌(논문/인용)용으로 (M3 수정과 연속).
- **N7. 데이터/provenance 추적** — 실험 run = 데이터+코드+시드 (git+telemetry 위에, A10 대체).

---

## Q4 답 (재활용/수정/폐기/신규 비율)

| 레이어 | 재활용 R | 수정 M | 폐기 D | 신규 N |
|--------|:---:|:---:|:---:|:---:|
| Agents (effective 8) | 2 | 6 | 0 | — |
| Skills (26) | 5 | 8 | 13 | — |
| 신규 컴포넌트 | — | — | — | 7개 (N1-N7) |

> 위 수치는 **사용자 재분류 반영 후** (2026-05-26). 변경 전 CC 초안: Agents R3/M5,
> Skills R5/M9/D12. 변경 방향이 *일관되게 "더 많은 작업"* 쪽임에 주목 → 아래 divergence 표.

**해석:**
- **콘텐츠 레이어(agent/skill)의 fork 이득은 인프라보다 작다.** 스킬의 **절반(12/26)이 폐기**
  (domain/design/test/CI 전용), 그대로 재활용은 소수(R=5, 대부분 메타·사고·worktree).
- 다수(M=14)는 *골격은 살되 SW 의미를 갈아야* 함 — 즉 "fork해도 콘텐츠는 대거 손봐야 함".
- **+ 최소 7개 신규 과학 컴포넌트**가 어느 경로든 필요(특히 N1 통계엔진, N5 tool-runner는 큰 작업).
- 종합: **fork의 진짜 이득은 Go 운영 인프라(reusable Tier A) + 루프 골격이고, agent/skill
  카탈로그는 절반 폐기 + 절반 개조 + 신규 7**. → fork vs scratch 견적의 무게중심은
  "운영 인프라를 공짜로 얻는 가치" vs "두뇌부·콘텐츠를 어차피 다시 만드는 비용"의 비교.

---

## CC 분류 vs 사용자 분류 차이 — 진짜 정보 (Q19 메타검증 입력)

사용자 검토(2026-05-26)에서 CC 초안과 갈린 항목과 그 *방향*. **이 차이가 핵심 신호.**

| 항목 | CC 초안 | 사용자 | 방향 | 차이의 의미 |
|------|:------:|:------:|:----:|------------|
| `moai-foundation-quality` | 수정 | 폐기+신규 | **더 큰 작업** | CC는 "품질 골격 재사용"으로 봄. 사용자: 코드품질은 과학 의미 ≈0, **"수정" 라벨이 SW 가정을 위장**. |
| `moai-workflow-gan-loop` | 수정 | 폐기 | **더 큰 작업** | CC는 "반복 품질개선 루프 구조 재사용"으로 봄. 사용자: **평가 본질(미적 점수 vs 통계검정)은 수정으로 못 바꿈**. CC가 *구조* 재사용성 과대평가. |
| `manager-git` | 재활용 | 수정 | **더 큰 작업** | CC는 "git=SW중립 그대로". 사용자: **"PR=완료" 워크플로우 의미가 박힘** — provenance 추적 추가 필요. |
| `moai-domain-database` | 폐기 | 수정 | **작업 존재(과소→실재)** | CC는 "OLTP=SW 폐기". 사용자: **과학 데이터 영속은 실재 요구** — CC가 데이터 요구 과소평가. |
| `moai-domain-research` | 수정 | (보류→) 수정 | 일치(조건부) | framing(시장조사)만 보면 폐기, 메커니즘 보면 재활용. |
| `moai-domain-ideation` | 수정 | 수정 | 일치 | 단 "hypothesis generation"으로 의미강화 명시 요구. |

### 메타 결론 (REPORT Q19로 이관) — **CC의 체계적 낙관 편향 감지**
6개 경계 중 **4개에서 CC가 사용자보다 낙관적**(재사용/수정으로 분류 → 사용자가 폐기/신규/
더-수정으로 상향). 방향이 *한쪽으로 일관*된다는 것이 결정적:
- **편향 패턴 1 — "수정" 라벨의 위장**: SW 본질(코드품질·미적평가)을 "수정 가능"으로 분류해
  SW 가정 잔존을 숨김(quality, gan-loop). → **M으로 분류된 다른 항목들도 재의심 필요.**
- **편향 패턴 2 — 구조 재사용성 과대평가**: 루프/git "골격"이 중립이라 봤으나, *판정·완료
  의미*가 박혀 있음(gan-loop, git). reusable.md "골격 재사용" 주장에도 같은 의심 적용.
- **편향 패턴 3 — 과학 요구 과소평가**: 데이터 영속(database)을 SW로만 봄.
- **함의**: 이 편향은 reusable.md(Tier 등급)·tdd-mismatch.md("3함수+fanout")에도 작용했을
  수 있음. **REPORT의 fork 견적은 CC 추정에 보정계수(낙관 할인)를 적용**하고, Q19 절에서
  이 편향을 명시적으로 다룬다. — 이것이 "정찰 끝에 답이 한쪽으로 기울 때 그게 CC 편향인지
  검증"(Q19)의 첫 구체 증거.

---

### 미검증/확신 못 함 (★경계 항목 = 사용자 검토 1순위)
- `moai-foundation-quality`(M vs D/N), `moai-domain-database`(D vs M),
  `moai-domain-research`/`moai-domain-ideation`(과학적합도가 분류보다 큰 변수),
  `moai-workflow-gan-loop`(M vs D), `moai-harness-learner`(R vs M — 학습신호 SW의존도 미확인),
  `manager-git`(R vs M — PR 중심성).
- 스킬 본문(Level 2)을 다 읽지 않고 frontmatter+description 기반 분류 — 본문에 SW 가정이
  더 박혀 있으면 M→D로 내려갈 수 있음.
