# sci-adk Tool Policy

> Status: AUTHORITATIVE (user-given, 2026-05-26). Verbatim record of the policy
> the user stated in session 1. Preserved in the user's wording.

## Scope (read this first)

This policy governs **sci-adk's research runtime** — the tools sci-adk uses to
*do research* (the science layer). It does **NOT** govern the **build
environment** used to *construct* sci-adk.

- **Build environment = MoAI-ADK** (root `CLAUDE.md`, `.moai/`, `.claude/`,
  `moai-lsp`). Used to write sci-adk's own source code. Software-engineering
  tools (LSP, TDD/DDD, coverage) are legitimate here — building a compiler is
  software engineering. This policy does not constrain it.
- **sci-adk runtime = governed by this policy** + the Spec/Evidence/Claim
  abstractions. The "excluded tools" below are excluded from *sci-adk's research
  workflow*, not from the build harness.

So `moai-lsp` in `.mcp.json` is a build-time coding aid, not a policy violation.

---

## 허용된 도구

**LLM 백엔드**
- Claude Code (primary)
- GLM via z.ai (fallback, 사용자가 명시적으로 토글하거나 rate limit 시)

**통합 표준**
- MCP (Model Context Protocol)

**Provenance (가설→시도→결과 추적)**
- Git (코드·문서 버전 관리)
- DVC (Data Version Control, 데이터·모델·시뮬레이션 결과)

**격리 실행 환경**
- docker (도메인별 환경 이미지화)
- 도메인 이미지 내부에: Python (NumPy/SciPy/SymPy/JAX/NetworkX/RDKit 등),
  SageMath, Lean 4 + Mathlib, LaTeX 등 — 도메인 따라 선택

**세션·병렬화**
- tmux (병렬 worktree)
- Claude subagent (작업 위임)

**외부 정보 접근**
- Claude native web_search, web_fetch
- Context7 (라이브러리 문서)

**학술 검색·인용 (MCP servers)**
- arXiv MCP
- Semantic Scholar MCP
- PubMed MCP (생의학 도메인 시)
- OpenReview MCP (ML/CS top venue 시)
- CrossRef MCP (DOI 해석)

**논문 작성**
- LaTeX, BibTeX, pandoc

## 명시적으로 배제하는 도구

다음은 MoAI-ADK가 사용하지만 본 프로젝트(sci-adk 런타임)가 *의도적으로
배제*한다 — 모두 *SW 개발 워크플로우 가정*을 끌어오기 때문이다:

- **LSP servers** — 코드의 "문법/타입 정합성 = 작업 완료" 가정. 본 시스템의
  완료 기준은 paper draft + 실행 가능한 코드 + 정합성 있는 evidence
- **ast-grep** — 구조적 코드 패턴 검색. SW 리팩토링 도구
- **Conventional Commits** — PR 자동화 규약. 본 시스템의 "완료"는 PR merge가
  아님
- **Coverage thresholds** (예: 85%) — 코드 테스트 커버리지. 본 시스템의 검증
  metric은 증명 정합성·재현성·통계 검정

위 4개에 대한 *과학용 대체 metric*은 추후 결정 (Spec/Evidence/Claim 자료형
설계 단계에서). 일단은 *어떤 metric도 hardcode하지 마라*.
(→ 대체 메커니즘은 design/abstractions.md "No hardcoded metrics" 참조:
각 Spec이 자기 DecisionRule을 선언한다.)

## 추가 시 규칙

새 도구가 필요하다고 판단되면:
1. *왜 필요한가* 구체 사례 한 줄
2. 위 배제 목록의 도구로 대체 가능한지 검토
3. 다른 *허용된* 도구로 대체 가능한지 검토
4. 위 둘 다 부정이면 사용자 승인 요청

도구 추가는 시스템 표면적 증가 = 디버깅·재현성 부담 증가. 보수적으로.

## 도구 도입 우선순위

첫 마일스톤에서 *전부 통합*하지 마라. 최소 셋부터:
1. Claude Code + Git + MCP — 시스템 코어
2. arXiv MCP + Semantic Scholar MCP — 학술 검색
3. docker (Python 기본 이미지) — 첫 코드 실행
4. LaTeX — 첫 paper draft

위 4개로 T-1의 *축소판*이 돌아가는 게 첫 마일스톤. 나머지 도구(Lean, SageMath,
DVC, tmux 등)는 *필요해진 시점에* 추가.
