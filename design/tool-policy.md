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

---

## 추가 도구 기록 (Addendum)

> 위 본문(2026-05-26 사용자 진술)은 verbatim 보존한다. 본 섹션은 그 이후
> "추가 시 규칙"(4단계)에 따라 도입된 도구를 시간순으로 기록한다.

### paperforge — DOI → Open Access PDF 취득 (2026-06-16, 사용자 승인됨)

`ccy5123/paperforge` (private). DOI 목록을 받아 OA 폴백 체인(arXiv → Unpaywall
→ OpenAlex → Europe PMC → Semantic Scholar)으로 full-text PDF를 내려받고,
`%PDF-` 매직바이트로 검증한 뒤 재개가능 `manifest.csv` + 메타데이터 sidecar를
남긴다.

추가 시 규칙(4단계) 검토:

1. **왜 필요한가**: 학술 *검색*(arXiv/S2/CrossRef MCP)이 찾은 DOI를 실제
   full-text OA PDF로 *취득*해 sci-adk가 읽게 한다. 검색=메타데이터,
   paperforge=취득(acquisition). 둘은 별개 단계다.
2. **배제 목록으로 대체 가능?** 불가. LSP/ast-grep/Conventional Commits/Coverage
   는 모두 무관(SW 워크플로우 도구).
3. **허용 도구로 대체 가능?** 부분만. arXiv/S2/CrossRef MCP는 메타데이터 검색·
   DOI 해석이지, OA 폴백 다운로드 + PDF 검증 + 재개가능 manifest가 아니다.
   paperforge가 그 갭(Unpaywall/OpenAlex/Europe PMC OA 발견 + PDF 취득)을 메운다.
4. **사용자 승인**: 받음 (2026-06-16).

도입에 따른 시스템 표면 증가(보수성 원칙 명시):

- **신규 외부 서비스**: Unpaywall, OpenAlex, Europe PMC (read-only OA 발견 API).
  arXiv·Semantic Scholar·CrossRef는 이미 허용 목록에 있음.
- **신규 외부 작용**: 네트워크 PDF 다운로드(읽기성 취득).

통합 방식:

- 형태: 서브프로세스/CLI 어댑터 — `src/sci_adk/search/paperforge_adapter.py`가
  `paperforge` CLI를 호출(runner/docker_executor 패턴). 두 파이썬 환경 격리 +
  provenance(핀 SHA·명령·버전) 기록.
- 핀: `ccy5123/paperforge @ 2cec69b5c9e3cdd518463a24f67cf713ff3f0d9e`
  (pyproject.toml `[project.optional-dependencies].tools`,
  `pip install -e ".[tools]"`). 이 핀부터 `paperforge.bibtex` (DOI→BibTeX) 포함.
- 출력: `runs/<proposal>/` 하위에 취득물 저장(연구 루프 배선 시).

**Discovery front-end (신규 도구 아님)**: paperforge에 넘길 DOI는 Claude의 native
`web_search`(이미 허용 목록)로 찾는다 — 연구자가 선행연구를 훑듯 on-demand로.
discovery(주제→주요 논문→DOI)는 코드 모듈이 아니라 에이전트 행위이고, paperforge가
그 DOI를 취득한다. 전체 흐름·진입점은 `design/literature-acquisition.md` 참조.

### Render 결정성 원칙 재정립 — "선을 옮긴다" (2026-06-22, 사용자 승인됨)

본 정책은 "sci-adk의 *완료 기준* = paper draft + 실행 가능한 코드 + 정합성 있는
evidence"이며 render는 결정적(LLM 없는) 단계라는 가정을 깔고 있다. 이 결정성의
*범위*가 재정립됐다(신규 도구 도입 아님 — 기존 render 레이어의 경계 이동):

- **여전히 결정적(양보 불가)**: verdict·측정값·evidence·그림 y값·replay. `sci-adk
  verify`가 record로 belief를 재현하는 근거(adoption-roadmap.md "no LLM in the verdict
  path"). LLM이 이를 생성하면 rigor 게이트가 붕괴한다.
- **에이전트로 이동**: 논문의 *서사·제목·구조*(rigor-shell-architecture.md §2.4에서
  이미 "Writing paper prose"=커널 OUT). 결정적 spine이 이 영역을 침범하던 것을 제자리로
  옮긴 것이며, **자율 `claude -p` 도입이 아니다** — 서사는 인세션 에이전트가 작성해
  입력으로 전달하고(zero-cost), 측정값/판정은 `\evval`/`\status` 마크업으로 엔진이
  record에서 치환한다(fail-loud). "no autonomous LLM call" 배제는 그대로 유효하다.

전체 설계: `design/render-architecture-reframe.md`.

### mcp SDK — Claude Science 커넥터 wire 전송 (2026-07-01, 사용자 승인됨)

- 용례: Claude Science 세션이 sci-adk 기록을 구동하도록, §7 경계 core(`connector.py`)를
  MCP 도구로 노출하는 로컬 stdio 서버(`connector_server.py`, Desktop Extension). 세션이
  `append-evidence`(spec-digest 강제)·`verify`·`status`를 호출한다.
- 배제 도구 대조: LSP/ast-grep/coverage와 무관 — 판정 경로에 개입하지 않는다. FUS-1은
  Stop-hook `sci-adk verify`가 구조적으로 보장하며, 이 의존성은 그것을 우회하지 않는다.
- 허용 도구 대조: MCP는 이미 허용 목록(통합 표준). 기존 도구로 대체 불가 — stdio MCP
  프로토콜 구현체가 필요하다(hand-roll보다 표준 SDK가 surface·재현 면에서 우위, 사용자 결정).
- 형태·격리: optional extra `[project.optional-dependencies].connector`
  (`pip install -e ".[connector]"`), lazy import — base 설치는 의존성 무영향이고 경계
  core(`connector.py`)는 의존성 0. 콘솔 진입점 `sci-adk-connector`.
- 전체 설계: `design/fusion-claude-science.md` §6/§7/§12.
