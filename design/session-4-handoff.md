# sci-adk — sci-adk-as-moai Pivot Handoff (다음 세션 시작 프롬프트)

> 이 문서를 다음 세션의 시작점으로 사용해라. sci-adk-as-moai 피봇 빌드 세션
> (2026-06-22)이 남긴 것이다. 너는 그 세션과 동일 인격이 아니다 — 산출물을 자료로
> 받아 이어가는 새 세션이다. 이전 판단을 무비판 계승하지 말고 필요하면 의심해라.

## 너의 역할

sci-adk의 공동 설계자. sci-adk는 **domain-general rigor / verification ADK**다 —
referee/scorekeeper. 핵심 철학은 record(증거, 단조·append-only)와 belief(주장,
비단조·수정가능)의 분리. **agents propose; the engine judges by frozen criteria. No
self-certification. 판정 경로는 결정적·규칙기반.**

## ★ 가장 먼저 이해할 것

이번 세션은 sci-adk를 **MoAI-ADK 운영 레이어**로 전환하는 피봇(§10.5 11단계)을
**전부 빌드 완료**했다. rigor 커널(record/belief, frozen criteria, `sci-adk verify`)은
그대로 보존하고, 그 위에 MoAI 스타일의 오케스트레이션(페르소나 + 워커/가드 에이전트 +
Skill + /sci 커맨드)을 얹었다. **단일 출처는 `design/sci-adk-as-moai.md` (AGREED→BUILT,
이제 커밋됨)** — 11개 섹션 + App A(5 fork 전부 CLOSED) + App B(cross-ref).

## 현재 위치

- 브랜치 **`master`**, HEAD **`551287a`**, origin에 push됨. 단일-master 워크플로
  (feature 브랜치 안 씀).
- 전체 테스트 **1024 passed** (`python3 -m pytest -q`).
- 이번 세션 8커밋 (선행 N1 포함):
  - `6e11b42` N1 노벨티 2-kind 마이그레이션 (선행, 미커밋이던 것 정리)
  - `69558a5` CLI verb 분해 (§4.6): init-spec/amend-spec/execute/append-evidence/derive-claim/render + run 래퍼
  - `31fd395` science-orchestrator output-style (researcher + /research 제거)
  - `1a6ef40` 워커 5 + 가드 3 에이전트 정의
  - `7646688` Skill 5 (sci 허브 + foundation-rigor + workflow×3)
  - `46c1752` /sci 커맨드 7 + init-session 풀킷 설치 (_PLAIN_ASSETS 3→23)
  - `a9e6070` t1 Docker executor 수정 (research 워크스페이스에서 동작)
  - `551287a` 문서 (two-env 스코핑 + 운영레이어 README + 설계문서 커밋)

## 상태 확인 (시작 시 먼저 실행)

```bash
# 이 dev repo는 WSL ~/sci-adk 에 있다. Windows 호스트의 Bash 도구는
# wsl.exe bash -lc 'cd ~/sci-adk && ...' 로 감싸라. pytest는 pythonpath=src.
wsl.exe bash -lc 'cd ~/sci-adk && git log --oneline -8 && python3 -m pytest -q 2>&1 | tail -2'
# 기대: HEAD=551287a, 1024 passed
```

## 운영 레이어 구조 (이번 세션 산출물)

연구 워크스페이스에 `sci-adk init-session <dir>` 로 설치되는 키트
(`src/sci_adk/templates/research-workspace/.claude/` 아래 템플릿):

- **science-orchestrator** output-style — 유일 페르소나. 6-stage 사이클
  (clarify→plan→experiment→publish→guards→close, §8). MoAI output-style 구조 재타게팅.
- **워커 5**: manager-prereg(init-spec/amend-spec) · expert-experimentalist(execute/
  append-evidence) · expert-statistician(derive-claim) · expert-writer(render) ·
  expert-literature(prior-work/novelty/contested).
- **가드 3 (자문 전용)**: evaluator-rigor/novelty/validity. 체크리스트는 verify.py/
  validity.py 함수에 DRY-link. **`sci-adk verify`가 유일 판정 (§6.4); 가드는 절대
  판정권 없음.**
- **Skill 5**: `sci`(허브, 인텐트 라우터+verb 스폰) + science-foundation-rigor(지식) +
  science-workflow-{prereg,experiment,publish}.
- **/sci 커맨드 7**: sci.md(루트=자율 파이프라인) + sci/{plan,experiment,publish,
  verify,status,replicate}.md (각 <20 LOC, Skill("sci") 라우팅).

## 남은 작업 (선택 / v2)

- **science-workflow-replicate Skill** + **science-tool-academic-search Skill** +
  **sci-replicate.md 활성화** — 설계가 step 11 선택사항으로 보류함 (replicate는 v2
  워커 `expert-replicator`와 함께; academic-search는 expert-literature가 인라인으로
  커버 중). v2 승격 시 진행.
- **§6.1 spec-digest 경계 가드** — step 2에서 의도적 보류. 워커가 verb 호출 시
  spec_digest 불일치를 CLI가 잡아 자동 거부하는 메커니즘. 현재 미구현 (verb는 현행
  동작만 분해). 워커 통합이 깊어지면 추가.
- **영구 e2e 스모크 테스트 코드화** — step 9는 사용자 선택으로 라이브 사이클만 돌렸다
  (영구 테스트 미작성). kit 설치 + verb 체인을 temp 워크스페이스에서 돌리는 회귀
  테스트를 추가하면 운영레이어 회귀 방어판이 된다.
- **README stale 테스트 카운트** — README가 여러 곳에서 "764"라고 함 (실제 1024).
  이번엔 스코프상 미수정. 사소한 정리.

## 알려진 이슈 / 함정

- **2-환경 분리 [HARD]**: 이 repo는 **빌드 하네스(MoAI-ADK)** + **제품(sci-adk)** 공존.
  키트는 연구 워크스페이스의 `.claude/`에 설치되지 — **절대 이 빌드 repo의 `.claude/`
  에 설치하지 마라** (D3 마커 가드가 self-install 차단). 빌드 repo의 root `CLAUDE.md` /
  `.moai/` / `.claude/`는 원칙적으로 건드리지 마라 (이번 §9.3 문서 패치는 사용자
  승인하에 `.claude/rules/sci-adk-constitution.md`만 예외 편집).
- **WSL 호출**: 모든 python/pytest/git은 `wsl.exe bash -lc 'cd ~/sci-adk && ...'`.
  파일 편집은 UNC 경로 `\\wsl.localhost\ubuntu\home\cyjoe\sci-adk\...`.
- **worktree 금지**: 이 프로젝트는 implementation 에이전트도 worktree를 쓰지 않는다
  (pytest pythonpath=src + WSL 경로 고정 `cd ~/sci-adk` 때문 — worktree면 테스트가
  메인 트리를 돌아 격리가 깨진다). 메인 트리에서 foreground로.
- **Import 컨벤션**: 단일 루트 `from sci_adk...`. 절대 `from src.sci_adk...` 금지.
- **커밋 메시지는 `-F 파일`로**: 중첩 `bash -lc '...'` heredoc은 본문의 리터럴 `'`
  (예: "MoAI's")에서 잘린다. Write 툴로 메시지 파일을 쓰고 `git commit -F <file>`.
- **작업 트리의 선행 잡음 (이번 세션과 무관, 미커밋 유지)**: `.claude/hooks/moai/*.sh`
  + `check-docker.sh` 모드 플립(0644→0755, 내용 0), `.moai/config/sections/llm.yaml`
  편집, 미추적 `.moai/reports/session-*.md` + `runs/*`. 빌드 하네스/환경 잡음이니
  피봇 커밋에서 의도적으로 제외했다. 따로 처리하라.
- **t1 Docker 수정 이력**: t1 컨테이너 스크립트는 이제 `inspect.getsource(t1_encoding)`
  로 self-contained (워크스페이스 src/ 의존 제거). 커널 DockerExecutor는 도메인-일반
  유지 (변경 안 함). 도메인 코드는 adapter에만.

## 이번 세션의 핵심 결정

- **분해 전략**: compile()을 스테이지 함수로 추출, run=인프로세스 체인, verb=얇은
  래퍼. evidence 정렬 불변식을 sorted-by-filename로 통일 (run==verb체인 by
  construction; checkpoint_loop iter1-vs-iter2 잠재버그도 해소).
- **페르소나**: MoAI output-style 구조를 sci-adk로 재타게팅 (사용자 선택).
- **/research + researcher 동시 제거** (사용자 선택; 클린 브레이크, 외부 사용자 0).
- **init-session 설치**: Option A (명시적 _PLAIN_ASSETS 목록 + lock-test); 풀 업그레이드.
- **step 9**: 전체 라이브 LLM 사이클 on t1-demo (사용자 선택). 라이브 사이클이 선행
  Docker 버그를 노출 → 수정.
- **게이트 2회 적중**: (1) evaluator-active가 멀티-evidence 논문 재정렬 회귀 발견
  (테스트 1024개가 못 잡음). (2) 라이브 사이클이 t1-Docker 버그 노출. → verify-don't-
  assume를 유지하라.

## 참고 문서 / 메모리

- **단일 출처**: `design/sci-adk-as-moai.md` (AGREED→BUILT, 11섹션 + App A/B)
- rigor 커널: `design/rigor-shell-architecture.md` · `design/abstractions.md`
- 노벨티 2-kind: `design/literature-acquisition.md` v0.6
- 채택 로드맵: `design/adoption-roadmap.md` (LLM-as-verdict는 영구 CUT)
- 자동 메모리: `sci-adk-as-moai-pivot`, `research-adk-productization`, `sci-adk-usable`,
  `import-convention`, `feedback_domain-generality` (새 세션에 자동 로드됨)

## 시작 절차

1. 위 "상태 확인" 실행 (HEAD=551287a, 1024 passed 확인)
2. `design/sci-adk-as-moai.md` §10.5(빌드 시퀀스) + §11(non-goals) 정독
3. 사용자와 다음 방향 결정: (a) 선택 v2 항목(replicate/academic-search/spec-digest
   가드) 중 무엇을, (b) e2e 스모크 테스트 코드화, (c) 실제 연구 사이클을 위해
   `sci-adk init-session`으로 워크스페이스 만들고 /sci 구동, 중 택일
4. 결정된 작업 진행 (체크포인트 모드: 매 게이트 사용자 승인 + verify-don't-assume)

---

Version: 1.0
Source: sci-adk-as-moai pivot build session (2026-06-22) completion
Status: Pivot §10.5 steps 1-11 COMPLETE — ready for v2 follow-ups or real research use
Last Updated: 2026-06-22
