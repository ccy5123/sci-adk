# sci-adk — Session 5 Handoff (다음 세션 시작 프롬프트)

> 이 문서를 다음 세션의 시작점으로 사용해라. sci-adk-as-moai 피봇(session 4)이
> 끝난 뒤 rigor 게이트를 강화하고(session 5) 작업 트리·메모리를 정리한 세션이
> 남긴 것이다. 너는 그 세션과 동일 인격이 아니다 — 산출물을 자료로 받아 이어가는
> 새 세션이다. 이전 판단을 무비판 계승하지 말고 필요하면 의심해라.

## 너의 역할

sci-adk의 공동 설계자. sci-adk는 **domain-general rigor / verification ADK**다 —
referee/scorekeeper. 핵심 철학은 record(증거, 단조·append-only)와 belief(주장,
비단조·수정가능)의 분리. **agents propose; the engine judges by frozen criteria.
No self-certification. 판정 경로는 결정적·규칙기반.** (`sci-adk verify` = 유일 판정)

## ★ 가장 먼저 이해할 것

- **피봇(§10.5 11단계)은 session 4에서 전부 빌드 완료**됐다 — rigor 커널 위에 MoAI
  스타일 오케스트레이션(science-orchestrator 페르소나 + 워커/가드 에이전트 + Skill +
  /sci 커맨드)을 얹었다. 단일 출처 `design/sci-adk-as-moai.md` (AGREED→BUILT).
- **session 5는 그 위에 rigor 게이트를 강화**했다: render 재정립, science guards
  G1–G5, §6.1 spec-digest 경계 가드, novelty N2/N3 마크업 렌더+verify 게이트. 전부
  master에 커밋·push, 1142 tests green.
- 남은 건 **전부 선택/v2/검증 성격** — 블로킹 없음. 코어는 실제 연구 사이클 구동 가능.

## 현재 위치

- 브랜치 **`master`**, HEAD **`2fffbb2`**, origin/master 동기화(0/0). 단일-master
  워크플로(feature 브랜치 안 씀).
- 전체 테스트 **1142 passed** (`python3 -m pytest -q`, ~14s).
- `~/.local/bin/sci-adk` = `~/sci-adk/src`의 editable install → 최신 가드 반영됨.

## 상태 확인 (시작 시 먼저 실행)

```bash
# 이 dev repo는 WSL ~/sci-adk 에 있다. Windows 호스트의 Bash 도구는
# wsl.exe bash -lc 'cd ~/sci-adk && ...' 로 감싸라. pytest는 pythonpath=src.
wsl.exe bash -lc 'cd ~/sci-adk && git log --oneline -8 && python3 -m pytest -q 2>&1 | tail -2'
# 기대: HEAD=2fffbb2, 1142 passed
```

## Session 4 이후 진행 (session 5 산출물)

session-4-handoff(HEAD `551287a`, 1024 tests) 이후 6커밋 + 정리:

- `f1312fd` MIT LICENSE (출판 전제조건; © 2026 Chan Young Joe)
- `94dd0ef` **render reframe** — 결정적 record-fidelity spine + 에이전트 내러티브 +
  `\evval`/`\status` fidelity gate + tool-agnostic 논문 (`paper_tool_clean` verify 게이트)
- `4695ff2` **science guards G1–G5** — spec-layer 과학적 엄밀성 게이트
  (analyticity/test-power/falsifiability/mode/cost); strict_science = lenient-primitive
  / strict-entrypoint; `NEGATIVE_CONTROL` Evidence kind
- `1c0b955` G1–G5를 워커 4 페르소나 + foundation-rigor skill에 wiring (A1)
- `1e47416` **§6.1 spec-digest 경계 가드** — frozen-Spec 변조 차단 (`spec_digest` primitive
  + append-evidence/derive-claim `--spec-digest`, lenient-absent)
- `2fffbb2` **novelty N2/N3** — `\novelty{result|method}{hyp}{text}` 마크업 렌더 +
  scoped-render + render-time/verify 게이트 (`paper_novelty_clean`)
- **정리(미커밋)**: 깨진 PUA 디렉토리 2개(`""`,`"2"` — G1–G5 적용 부산물) 삭제;
  `core.filemode=false` 설정으로 WSL filemode-flip 잡음 영구 차단; 자동 메모리 통합
  (MEMORY.md 26.7→3.4KB).

## 다음 세션 작업 (트랙별; 권장 순서 C → A → D)

**Track A — 운영 레이어 v2 마무리** (피봇 deferred)
- `science-workflow-prereg`/`-experiment` SKILL의 **guard-awareness** — G1–G5를 인지하도록
  (A1은 4 personas + foundation-rigor만 wiring; 이 2 skill은 승인 범위 밖이었음)
- `science-workflow-replicate` Skill + `expert-replicator` 워커 + `sci-replicate.md`
  활성화 (현재 v2 stub; 재현 병목 시)
- `science-tool-academic-search` Skill (현재 `expert-literature` 인라인 커버)

**Track B — 렌더/검증 잔여**
- 4c **cross-doc `\ref` 게이트** (main↔SI) — Overleaf compile-order; 현재 plain-text
  'Figure S1' 우회 중
- **G5(claim-cost) 키워드 보강** 결정

**Track C — 코드 위생 (quick wins)**
- **ruff F401** 5개 (`spec.py`/`evidence.py`, auto-fixable, 기존 잡음)
- **paperforge DOI→BibTeX e2e 1회 확인** — 코드 LANDED(`c5014ac`)지만 실제 full-entry
  `references.bib` 생성 미검증

**Track D — 일반성 게이트 (마일스톤급, 임팩트 최대)**
- **2nd-domain generalization** — A3 capability seam에 **다른 도메인이 커널 수정 0으로
  plug-in** 되는지 검증. "domain-general rigor ADK" 정체성의 핵심 미검증 지점
  (지금까지 T-1 분자만). adoption-roadmap의 generalization gate.

**Track E — 출판 경로** (사용자 주도, 비블로킹)
- T-1 스케일업(랜덤 큰 분자셋) + T-2(p-adic similarity, empirical) → 사용자가 연구
  완료 후 제공 → `init-spec→append-evidence→derive-claim→render→verify` → **Paper B
  방법론 논문 + arXiv 우선**. JORS/SoftwareX 지금 가능, JOSS ~2026-12.

## 알려진 이슈 / 함정

- **2-환경 분리 [HARD]**: 이 repo = 빌드 하네스(MoAI-ADK) + 제품(sci-adk) 공존. 키트는
  연구 워크스페이스 `.claude/`에 설치(`sci-adk init-session`), **절대 이 빌드 repo의
  `.claude/`에 설치 금지** (D3 마커 가드가 차단). 빌드 하네스(root `CLAUDE.md`/`.moai/`/
  `.claude/`)는 원칙적으로 건드리지 마라.
- **빌드 하네스 working-tree 잡음 (sci-adk 작업과 무관, 미커밋 유지)**: `.moai/config/
  sections/llm.yaml` 편집, 미추적 `.moai/reports/session-*.md`, `runs/*` 연구 산출물.
  피봇/feature 커밋에서 의도적으로 제외하라. `core.filemode=false`라 `.claude/hooks/
  moai/*.sh` 모드 플립은 이제 status에 안 뜬다.
- **WSL 호출**: 모든 python/pytest/git은 `wsl.exe bash -lc 'cd ~/sci-adk && ...'`.
  파일 편집은 UNC 경로 `\\wsl.localhost\ubuntu\home\cyjoe\sci-adk\...`.
- **worktree 금지**: 이 프로젝트는 implementation 에이전트도 worktree를 쓰지 않는다
  (pytest `pythonpath=src` + WSL `cd ~/sci-adk` 고정 — worktree면 격리가 깨진다).
  메인 트리에서 foreground로.
- **Import 컨벤션**: 단일 루트 `from sci_adk...`. 절대 `from src.sci_adk...` 금지.
- **커밋 메시지는 `-F 파일`로**: 중첩 `bash -lc '...'` heredoc은 본문의 리터럴 `'`
  (예: "MoAI's")에서 잘린다. Write로 메시지 파일을 쓰고 `git commit -F <file>`.
- **연구 산출물은 사용자의 라이브 작업**: `runs/t1-godel/*`, `runs/t1-demo/`, PDF,
  checkpoints, `~/research/*` — 명시적 지시 없이 건드리지 마라.

## 핵심 결정 (보존)

- record/belief 분리, frozen Spec, append-only Evidence, revisable Claim.
- `sci-adk verify` = 유일 판정 권한 (LLM은 pass/fail 결정 안 함 — adoption-roadmap CUT).
- 가드(evaluator-{rigor,novelty,validity})는 **자문 전용** (§6.4); verify가 sole verdict.
- 도메인 코드는 capability adapter(`sci_adk.adapter`, F4 seam)에만 — 커널/일반 CLI/
  base-image는 도메인 0 ([[feedback_domain-generality]]).
- "확인 후 삭제"류 지시 = 사용자의 게이트; 같은 턴 자가확인+삭제 금지
  ([[feedback_confirm-before-destructive]]).

## 참고 문서 / 메모리

- **단일 출처**: `design/sci-adk-as-moai.md` (피봇 아키텍처, BUILT)
- rigor 커널: `design/rigor-shell-architecture.md` · `design/abstractions.md`
- 과학 게이트: `design/science-guards.md` · `design/evidence-validity.md` ·
  `design/render-architecture-reframe.md` · `design/literature-acquisition.md` v0.6
- 채택 로드맵: `design/adoption-roadmap.md` (LLM-as-verdict 영구 CUT)
- 출판: `design/` 외 `~/research/publication-plan.md` (사용자 영역, WSL)
- 자동 메모리: `MEMORY.md` 인덱스 + `project_*`/`feedback_*` 토픽 파일 (새 세션 자동 로드)

## 시작 절차

1. 위 "상태 확인" 실행 (HEAD=2fffbb2, 1142 passed 확인)
2. 이 문서 "다음 세션 작업" 트랙 A–E 정독 + `design/sci-adk-as-moai.md` §11(non-goals)
3. 사용자와 다음 방향 결정 — 권장 진입 C(quick wins) → A(운영 완성) → D(일반성 검증);
   Track E는 사용자 연구 진행 의존
4. 결정된 작업 진행 (체크포인트 모드: 매 게이트 사용자 승인 + verify-don't-assume)

---

Version: 1.0
Source: sci-adk session 5 (2026-06-25) — rigor-gate hardening + worktree/memory cleanup
Status: 피봇 + rigor 게이트(render/G1–G5/spec-digest/novelty) 빌드 완료; v2·검증 backlog만 남음
Last Updated: 2026-06-25
