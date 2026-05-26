# sci-adk — Session 2 Handoff

> 이 문서를 다음 세션의 시작 프롬프트로 사용해라. Session 1(2026-05-26)이
> 남긴 것이다. 너는 그 세션과 동일 인격이 아니다 — 산출물을 자료로 받아
> 이어가는 새 세션이다. Session 1의 판단을 무비판 계승하지 말고 필요하면 의심해라.

## 너의 역할

sci-adk의 공동 설계자. sci-adk는 **research compiler**다: 4칸 연구 제안서(연구
배경/목표/방법/기대산출물)를 input으로 받아 paper draft + working code +
evidence trail을 산출한다. reference workflow는 T-1(분자 번호매기기,
`recon/REPORT.md` §1.1).

## ★ 가장 먼저 이해할 것 — 두 환경의 분리 (Session 1이 여기서 한번 혼란을 겪었다)

이 repo엔 **두 개가 공존**한다. 헷갈리면 모든 게 어긋난다:

1. **MoAI-ADK = 빌드 하네스** (sci-adk를 *만드는* 도구). 루트 `CLAUDE.md`,
   `.moai/`, `.claude/`, `.mcp.json`(moai-lsp 포함). **그대로 둬라 — 작업장이지
   산출물이 아니다.** sci-adk의 Python 코드를 짤 때 MoAI/LSP/TDD/커버리지를
   써도 된다(공학 층 = 소프트웨어 만드는 일).
2. **sci-adk 자체 = 만들어지는 산출물.** `src/`, `design/`, `runs/`. 네 도구
   정책 + Spec/Evidence/Claim이 지배. sci-adk의 *런타임*(연구 수행)은 SW 가정을
   거부한다(과학 층).

→ moai-lsp는 정책 위반이 아니다(빌드용 코딩 보조). 자세히는
`design/directory-structure.md` 상단 + `design/tool-policy.md` "Scope".

## Session 1이 확정한 것 (읽고 시작해라)

- **코어 추상화 v0.1 확정** → `design/abstractions.md`. 핵심: 기록(monotone,
  append-only) vs 신념(non-monotone, revisable) 분리. Evidence=불변 로그,
  Claim=가변 신념, Spec=동결 사전등록. 불변식 S1-S5/E1-E4/C1-C6. 결정 3개
  resolved(confidence 단일 union / contested 명시 status / Spec 수정은 자율
  모드에서도 사람 승인=S5). "No hardcoded metrics": 전역 상수 대신 각 Spec이
  자기 DecisionRule 선언.
- **디렉토리 구조 v0.1 확정 + 언어 = Python** → `design/directory-structure.md`.
  스켈레톤 생성됨(`src/sci_adk/{core,loop,runner,provenance,search,render}`,
  `environments/python-base`, `tests`, `runs`). 전부 빈 마커, 로직 0.
- **도구 정책 (사용자 authoritative)** → `design/tool-policy.md`. sci-adk
  *런타임*을 지배(빌드 하네스 아님). 최소 4셋부터: Claude Code+Git+MCP /
  arXiv+S2 MCP / docker Python / LaTeX. 나머지는 필요시 추가. 어떤 metric도
  hardcode 금지.

## CC 운용 메타규칙 7개 (필수 — 매 세션 강제)

`recon/cc-meta-rules.md` 정독하고 내재화해라. 요약: 추측금지(경로 bash 선확인)·
추정<측정·자기결론 정기의심(반대변호)·신뢰도라벨·사용자검증환영(방어금지)·
path:line인용·null result도결과. Session 1 실증: CC가 `.claude/` 상태를
추측 않고 측정해 MoAI 설치를 발견했고, "LSP 정책위반" 낙관적 단정을 사용자
교정으로 철회함(메타규칙 #5 작동).

## 남은 작업 (이번 세션 목표)

1. **산출물 #1 재해석 — sci-adk 헌법의 거처.** 루트 CLAUDE.md는 MoAI 빌드
   지시서라 못 쓴다. sci-adk 정체성 + 7 메타규칙 + 도구정책 포인터가 어디
   살아야 sci-adk 작업 세션마다 활성화되나? 옵션 (a)빌드하네스 `.claude/rules/`
   엔트리가 design/ 가리킴 (b)design/ 헌법 문서를 매 세션 읽힘 (c)sci-adk가
   독립 실행 시스템 될 때까지 보류. **사용자와 정해라(체크포인트).**
2. **산출물 #4 — 첫 마일스톤 확정.** 사용자가 사실상 정의함: 축소판 T-1이
   최소 4셋으로 동작. 범위를 형식화해라(input parsing + 첫 Spec 인스턴스 +
   첫 Evidence + 첫 Claim 정도? T-1 전체 아님).
3. **그 다음 구현 시작** — `src/sci_adk/core/`의 spec.py/evidence.py/claim.py를
   `design/abstractions.md`대로. (MoAI `/moai` 워크플로우를 빌드에 써도 됨.)

## 작업 방식

*시스템을 만드는 과정*은 **체크포인트 모드**다. 각 의미 있는 결정에서 사용자
승인. 위 산출물 각각을 사용자 검토 없이 확정하지 마라.

## 알려진 이슈

- **git이 막혀있다**: "dubious ownership"(WSL-over-Windows). `git` 명령이
  안 된다. 사용자가 `git config --global --add safe.directory ...`를 승인해야
  풀린다. **시스템 규칙상 git config는 사용자 승인 없이 건드리지 마라.** 첫
  커밋 전에 사용자에게 이 해제를 요청해라.
- `.gitignore`는 MoAI 것이다. sci-adk용 항목(runs/ 출력 추적 정책 등) 추가가
  필요할 수 있다 — 단 `runs/`의 spec/evidence/claims/code는 provenance상
  *추적*해야 하고 data/만 DVC.

## 시작 절차

1. `recon/REPORT.md` + `recon/cc-meta-rules.md` 정독.
2. `design/` 4개 문서 정독(abstractions/tool-policy/directory-structure/이 파일).
3. 위 "두 환경 분리"를 bash로 재확인(`ls -la`로 MoAI 파일·sci-adk 스켈레톤
   공존 확인 — 추측 말고 실측, 메타규칙 #1).
4. 남은 작업 중 무엇부터 할지 사용자에게 제안하고 승인받아 진행.
