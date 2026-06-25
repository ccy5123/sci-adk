# sci-adk — Session 6 Handoff (다음 세션 시작 프롬프트)

> 이 문서를 다음 세션의 시작점으로 사용해라. session 5(rigor 게이트 강화) 이후
> Track A/B/C backlog를 닫고, 출판 단계 기능(F1/F2/F3)을 AGREED→BUILT로 완성한
> 세션이 남긴 것이다. 너는 그 세션과 동일 인격이 아니다 — 산출물을 자료로 받아
> 이어가는 새 세션이다. 이전 판단을 무비판 계승하지 말고 필요하면 의심해라.

## 너의 역할

sci-adk의 공동 설계자. sci-adk는 **domain-general rigor / verification ADK**다 —
referee/scorekeeper. 핵심 철학은 record(증거, 단조·append-only)와 belief(주장,
비단조·수정가능)의 분리. **agents propose; the engine judges by frozen criteria.
No self-certification. 판정 경로는 결정적·규칙기반.** (`sci-adk verify` = 유일 판정)

## ★ 가장 먼저 이해할 것

- **출판 단계 기능 F1/F2/F3이 전부 빌드 완료**됐다 — 단일 출처
  `design/paper-publishing-requirements.md` (AGREED 2026-06-25 → BUILT). rigor 커널
  (record/belief)을 건드리지 않고 render contract를 확장한다. 빌드 순서 F2→F3→F1.
- 게이트 원칙 보존: **LLM은 판정 경로에 없다** — 게이트되는 모든 요건은 `sci-adk
  verify`에 접힌 결정적 체커다. advisory·max_pages는 surface만, 게이트 안 함. 코드
  리스팅은 SI에만(도구-불가지론 `draft.tex` 불변).
- session 5가 남긴 Track A/B/C backlog는 이 세션 시작 전(또는 초반)에 이미 닫혔다
  (아래 "진행" 참조). 남은 마일스톤급 미검증은 **Track D(2nd-domain 일반성)**.

## 현재 위치

- 브랜치 **`master`**, HEAD **`6732bd1`**. 단일-master 워크플로(feature 브랜치 안 씀).
- 전체 테스트 **1227 passed** (`python3 -m pytest -q`, ~14s).
- `~/sci-adk/src`의 editable install이 최신 코드 반영(`python3 -m`·pytest·`from
  sci_adk.cli import main` 경로). **단, `~/.local/bin/sci-adk` 바이너리는 구버전이라
  `pubreqs` 동사를 못 본다** — 바이너리로도 쓰려면 `pip install -e . --force-reinstall`.

## 상태 확인 (시작 시 먼저 실행)

```bash
# 이 dev repo는 WSL ~/sci-adk 에 있다. Windows 호스트의 Bash 도구는
# wsl.exe bash -lc 'cd ~/sci-adk && ...' 로 감싸라. pytest는 pythonpath=src.
wsl.exe bash -lc 'cd ~/sci-adk && git log --oneline -8 && python3 -m pytest -q 2>&1 | tail -2'
# 기대: HEAD=6732bd1, 1227 passed
```

## Session 5 이후 진행 (session 6 산출물)

session-5-handoff(HEAD `2fffbb2`/`0c9e5af`, 1142 tests) 이후:

**먼저 닫힌 session-5 backlog (Track A/B/C):**
- `00d340d` ruff F401 5개 제거 (Track C)
- `4adbc3b` G1–G5 guard-awareness를 prereg/experiment Skill에 wiring (Track A)
- `913591e` **cross-doc S-ref 게이트** (main↔SI) + G5 키워드 보강 (Track B 4c/G5)
- `b61f4f6` `expert-replicator` 승격 + `academic-search` Skill 추가 (Track A)

**출판 단계 기능 (이 세션 핵심 산출물):**
- `9429f9d` design: **paper-publishing-requirements.md AGREED** (F1/F2/F3 스펙)
- `3dcb1dc` **F2** — 그림 폰트 정책: pdflatex metric-compatible(newtxmath/helvet),
  figure-bearing 문서만, figure-less는 byte-identical
- `1c2fc0d` **F3** — 재현 번들: `render/reproduction.py`(PURE) SI 코드 리스팅 +
  `paper/code/` 코로케이션 + `paper/reproduce.py` 드라이버(compiler). 실 t1-godel
  `code_ref`는 bare 커밋 → POINTER(fail-open, OF-4)
- `0ff48bc` **F1-core** — `core/pubreqs.py` frozen 모델 + `pubreqs_digest` +
  `render/pubreqs_checks.py`(F2-이연 PURE font/DPI 체커, stdlib만) +
  `loop/verify.py` `paper_requirements_clean` 우산 HARD 게이트(pubreqs.json 부재 →
  공허-통과, 하위호환) + `sci-adk pubreqs freeze <run> [--defaults]` CLI 동사
- `6732bd1` **F1-templates** — `/sci publish` 허브 elicitation(오케스트레이터 전용
  AskUserQuestion) + `science-workflow-publish` + `expert-writer` 배선

검증: 전체 독립 재실행 + 실제 CLI end-to-end(`pubreqs freeze --defaults`→`verify`가
정직하게 실패/공허-통과 확인). 메모리 기록: [[project_publishing-features]].

## 다음 세션 작업 (트랙별; 권장 진입 E → D)

**Track E — 출판 경로 (가장 유망; 이제 도구 완비)** (사용자 주도, 비블로킹)
- 출판 단계 기능이 완성됐으니 **T-1(godel) 연구 런을 논문까지 구동** 가능:
  `/sci plan→experiment→publish`(이제 publishing-requirements elicitation 포함)→`verify`.
- **단서**: working tree에 미커밋 t1-godel 연구 런 흔적이 있다 — `runs/t1-godel/
  spec.json`(06-25 `referent`/`non_circularity` 등 G1–G5 필드로 재초기화),
  `science.md`(G1–G4 약과학 지적 기록), `runs/t1-demo/`. 누군가 t1-godel을 재-init하고
  과학 가드를 돌리던 중. **이 갈래를 이으려면 `science.md`의 G1–G4 지적을 spec
  amendment로 해소**(epistemic_kind 재분류 / discriminating_cases / NEGATIVE_CONTROL
  계획 / mode=confirmatory)한 뒤 진행. → Paper B 방법론 논문 + arXiv 우선.

**Track D — 일반성 게이트 (마일스톤급, 임팩트 최대; 미검증 유지)**
- **2nd-domain generalization** — A3 capability seam에 다른 도메인이 커널 수정 0으로
  plug-in 되는지 검증. "domain-general rigor ADK" 정체성의 핵심 미검증 지점(지금까지
  T-1 분자만). `design/adoption-roadmap.md`의 generalization gate.

**Track C — 잔여 quick win**
- **paperforge DOI→BibTeX e2e 1회 확인** — 코드 LANDED지만 실제 full-entry
  `references.bib` 생성 미검증 (session-5에서 이월).

**Track F — 출판 기능 후속(선택)**
- 현재 `pubreqs` CLI는 `freeze`만. design §1.2의 full elicitation 흐름은 `/sci publish`
  허브(오케스트레이터)가 AskUserQuestion으로 구동 — 별도 CLI 불필요(설계대로).
- xelatex/fontspec 리터럴 폰트 트랙(OF-2)은 OUT of scope — venue가 실제 Arial/Times
  파일을 요구할 때만 재론.

## 알려진 이슈 / 함정

- **2-환경 분리 [HARD]**: 이 repo = 빌드 하네스(MoAI-ADK) + 제품(sci-adk) 공존. 키트는
  연구 워크스페이스 `.claude/`에 설치(`sci-adk init-session`), **절대 이 빌드 repo의
  `.claude/`에 설치 금지**. 빌드 하네스(root `CLAUDE.md`/`.moai/`/`.claude/`)는 건드리지 마라.
- **빌드 하네스 working-tree 잡음 (sci-adk 작업과 무관, 미커밋 유지)**: `.moai/config/
  sections/llm.yaml`(44→21줄 축소), 미추적 `.moai/reports/session-*.md`, `runs/*` 연구
  산출물. F 커밋에서 의도적으로 제외했다. **이 중 `runs/t1-godel/*`·`runs/t1-demo/`·
  `science.md`는 Track E 연구 런의 라이브 산출물일 수 있으니 사용자 확인 없이 폐기 금지.**
- **`~/.local/bin/sci-adk` 바이너리 stale**: `pubreqs` 동사 미반영. `python3 -m`·pytest·
  editable src는 정상. 바이너리 갱신은 `pip install -e . --force-reinstall`.
- **WSL 호출**: 모든 python/pytest/git은 `wsl.exe bash -lc 'cd ~/sci-adk && ...'`.
  파일 편집은 UNC 경로 `\\wsl.localhost\ubuntu\home\cyjoe\sci-adk\...`.
- **worktree 금지**: implementation 에이전트도 worktree를 쓰지 않는다(pytest
  `pythonpath=src` + editable install이 메인 src를 가리킴 — worktree면 격리/테스트가
  깨진다). 메인 트리에서 foreground로.
- **Import 컨벤션**: 단일 루트 `from sci_adk...`. 절대 `from src.sci_adk...` 금지.
- **커밋 메시지는 `-F 파일`로**: 중첩 `bash -lc '...'` heredoc은 본문에서 잘린다.
  Write로 메시지 파일을 쓰고 `git commit -F <file>` (이 세션도 그렇게 했다).
- **render PURE 불변식**: `render/*.py`(si/paper/figures/reproduction/pubreqs_checks)는
  fs/네트워크/LLM 접근 0. 모든 fs는 compiler가. byte-identical 회귀 불변식 유지.

## 핵심 결정 (보존)

- record/belief 분리, frozen Spec, append-only Evidence, revisable Claim.
- `sci-adk verify` = 유일 판정 권한 (LLM은 pass/fail 결정 안 함 — adoption-roadmap CUT).
- 출판 게이트도 동일: 게이트되는 요건 = 결정적 체커, advisory·max_pages는 비게이트,
  pubreqs.json 부재 시 공허-통과, gate-bearing 필드는 명시적 re-freeze로만 완화
  (anti-moving-the-goalposts).
- 가드(evaluator-{rigor,novelty,validity})는 **자문 전용**; verify가 sole verdict.
- 도메인 코드는 capability adapter에만 — 커널/일반 CLI/출판 표면은 도메인 0
  ([[feedback_domain-generality]]).
- "확인 후 삭제"류 지시 = 사용자의 게이트; 같은 턴 자가확인+삭제 금지
  ([[feedback_confirm-before-destructive]]).

## 참고 문서 / 메모리

- **출판 기능 단일 출처**: `design/paper-publishing-requirements.md` (F1/F2/F3, BUILT)
- 피봇 아키텍처: `design/sci-adk-as-moai.md` (BUILT)
- rigor 커널: `design/rigor-shell-architecture.md` · `design/abstractions.md`
- 과학 게이트: `design/science-guards.md` · `design/evidence-validity.md` ·
  `design/render-architecture-reframe.md` · `design/literature-acquisition.md` v0.6
- 채택 로드맵: `design/adoption-roadmap.md` (LLM-as-verdict 영구 CUT; 일반성 게이트)
- 자동 메모리: `MEMORY.md` 인덱스 + `project_*`/`feedback_*` 토픽 파일 (새 세션 자동 로드).
  이 세션 추가: [[project_publishing-features]].

## 시작 절차

1. 위 "상태 확인" 실행 (HEAD=6732bd1, 1227 passed 확인)
2. 이 문서 "다음 세션 작업" 트랙 + `design/paper-publishing-requirements.md` 정독
3. 사용자와 다음 방향 결정 — 권장 진입 E(t1-godel 연구 런 → 논문, 도구 완비) →
   D(일반성 검증). Track E는 `science.md` G1–G4 지적 해소가 선행.
4. 결정된 작업 진행 (체크포인트 모드: 매 게이트 사용자 승인 + verify-don't-assume).

---

Version: 1.0
Source: sci-adk session 6 (2026-06-25) — publishing features F1/F2/F3 (font policy +
reproduction bundle + pubreqs umbrella gate + /sci publish elicitation) AGREED→BUILT
Status: 출판 단계 기능 빌드 완료; Track E(연구 런→논문) + Track D(일반성) backlog
Last Updated: 2026-06-25
