# sci-adk — Session 8 Handoff (다음 세션 시작 프롬프트)

> 이 문서를 다음 세션의 시작점으로 사용해라. session 7(SPEC-PAPER-GATE-001 완주)
> 이후 **G-A 키스톤(도메인-일반성)을 A3 판정으로 해소**하고, 그 결과를 공개 표면에
> **G-E 정직성 문구로 적용**한 세션이 남긴 것이다. 너는 그 세션과 동일 인격이 아니다 —
> 산출물을 자료로 받아 이어가는 새 세션이다. 이전 판단을 무비판 계승하지 말고 필요하면
> 의심해라(특히 아래 "알려진 이슈"의 ruff 항목).

## 너의 역할

sci-adk의 공동 설계자. sci-adk는 **domain-general rigor / verification ADK**다 —
referee/scorekeeper. 핵심 철학은 record(증거, 단조·append-only)와 belief(주장,
비단조·수정가능)의 분리. **agents propose; the engine judges by frozen criteria.
No self-certification. 판정 경로는 결정적·규칙기반.** (`sci-adk verify` = 유일 판정)

## ★ 가장 먼저 이해할 것

- **G-A 키스톤이 A3 판정으로 해소됐다.** 단일 출처: `design/g-a-a3-decision.md`.
  핵심 = A1을 커널 **인터페이스별로 split**:
  - **A1a — Verifier-seam + record/belief의 2nd-도메인 일반성: DONE.** 증거 =
    **IEAM-P8**(생태독성/DEB-TK, 외부 워크스페이스 `~/research/ieam-followup-p8`)이
    2nd 도메인을 커널의 Verifier(`DecisionEngine`/`sci-adk verify`)+typed store에
    **커널 수정 0**으로 통과(27/27 reproduce, 100 Claim 81/17/2). 이게 공개 주장
    ("domain-general rigor/verification ADK; referee, engine judges")의 핵심.
  - **A1b — 자율 Experiment adapter-registry(`ExperimentFn`/`--capability`) 일반성:
    1.0 주장에서 scope-out.** T-1만 등록; IEAM-P8은 정당한 operational/borrow 경로
    (A5 in-session substrate)를 씀. de-emphasized "player" 절반 — 미광고·비차단.
- **왜 이 판정이 정당한가**: 커널(core/loop/render)은 도메인-free, adapter를 import 안 함
  (`tests/test_kernel_adapter_seam.py`가 AST로 강제). `sci-adk verify`=판정 경로=Verifier
  인터페이스이고, verification ADK의 "일반성"은 곧 그것. IEAM-P8이 adapter registry를
  *우회*했지만 verify 게이트를 *통과*했으므로, sci-adk가 실제로 하는 주장을 입증한다.
- **G-E(정직성) 문구가 적용됐다(structural/conservative 레벨).** 공개 헤드라인
  (README:9, pyproject:8, CITATION:5)은 이제 "domain-general **kernel**(zero domain code)
  +capability-adapter seam"만 주장 — cross-domain-validated *system*이 아님. 2nd-도메인
  검증은 README Remaining에 "separate research, paper in preparation"으로 정직하게 서술.
  비공개 IEAM-P8 증거를 헤드라인 주장으로 올리지 않음(sci-adk 원칙: Claim은 Evidence 인용).
- 남은 릴리스 게이트: **G-B(방법론 논문)·G-D(버전/태그)**. G-C/G-E는 done.

## 현재 위치

- 브랜치 **`master`**, HEAD **`87a9869`**(이 핸드오프 커밋은 그 다음). 단일-master 워크플로.
- 전체 테스트 **1362 passed** (`python3 -m pytest -q`, ~18s).
- 이번 세션 커밋: `87a9869` docs(release): G-A keystone resolved (A3 verdict) + G-E honesty
  wording applied — 6파일(신규 `design/g-a-a3-decision.md` + release-readiness/adoption-roadmap
  /README/pyproject/CITATION). **.py 변경 0**(문서/메타데이터만).

## 상태 확인 (시작 시 먼저 실행)

```bash
# dev repo는 WSL ~/sci-adk. Windows Bash 도구는 wsl.exe bash -lc 'cd ~/sci-adk && ...'로 감싸라.
wsl.exe bash -lc 'cd ~/sci-adk && git log --oneline -4 && python3 -m pytest -q 2>&1 | tail -2'
# 기대: HEAD=핸드오프 커밋(87a9869 위), 1362 passed
wsl.exe bash -lc 'cd ~/sci-adk && grep -nE "domain-general" README.md | head'
# 기대: :9 "domain-general kernel" / :230 구조적 / :238 "verification claim ... evidence-backed"
```

## Session 7 이후 진행 (session 8 산출물)

- A3 판정(`design/g-a-a3-decision.md` 신규) — 측정 기반(커널/adapter seam + IEAM-P8 런 구조
  실측), split verdict(A1a DONE / A1b scope-out), 신뢰도 라벨, devil's-advocate, 함의.
- `design/release-readiness.md` §3 — A1→A1a/A1b split, A3 [TBD]→[DONE], 키스톤/§8/§9 갱신;
  §7 G-E E1/E2 [DONE] + audit "APPLIED".
- `design/adoption-roadmap.md` §A3(d)/§6 — 일반화 게이트 RESOLVED(인터페이스별).
- G-E 문구 적용 — README:9/:238, pyproject:8, CITATION:5(구조적/보수 레벨).
- 자동 메모리 — 신규 [[project_g-a-a3-decision]] + MEMORY.md 인덱스 갱신.

검증: 매 게이트 사용자 승인(체크포인트 모드) + 스위트 green(1362) + 잔존 "domain-general"
전수 확인(헤드라인 과장 0). 판정/honesty 레벨은 AskUserQuestion으로 사용자가 확정.

## 다음 세션 작업 (트랙별)

**G-B — 방법론 논문 (Option 4; 더는 키스톤에 안 막힘)**
- primary case study = T-1; IEAM-P8 = cross-domain **verification** 증거(adapter-seam 케이스
  아님). paper-grade T-2 writeup은 선택(비게이트). related work에 session 7 조사
  (EviBound arXiv 2511.05524 = 사상적 쌍둥이, AAR 2602.13855, AI-Scientist 비판) 활용.
- 단서(이월): `runs/t1-godel/science.md`의 G1–G4 약과학 지적을 spec amendment로 해소 후.

**G-D — 버전/API 안정성 (기계적)**
- D1: CLI/API 표면 freeze(semver 1.0=안정성 약속) — 표면이 최근까지 성장(`package`/`pkgreqs`)
  했으니 freeze 시점 판단 필요. D2: `pyproject.toml` 0.1.0→1.0.0. D3: `v1.0.0` 태그+릴리스
  노트. D4: PyPI publish 결정(TBD). `design/release-readiness.md` §6.

**G-A 잔여(선택, 비차단)**
- A4(in-repo T-2 adapter): A1b를 실제로 입증하려는 경우에만. T-2(p-adic similarity) 연구-gated.
  현 판정에선 scope-out이라 1.0 비차단.

**SPEC-PAPER-GATE-001 잔여(accepted)**
- R2(P5 인라인 figure `\includegraphics`), R3(per-run `0`/`1` self-op — won't-fix 권장).
  [[paper-writing-enforcement-spec]].

## 알려진 이슈 / 함정

- **ruff 게이트 불일치 [신규, 미해결]**: session 7 핸드오프 노트는 "ruff check 통과"라 했으나,
  이번 측정에서 `ruff check .`(설정 파일 없음 → 전체 기본 규칙)는 **HEAD 기준 202 에러**를
  보고한다(src/tests 포함). 이번 세션 .py 변경 0이라 *내 작업 무관·기존 상태*다. CI가 범위/
  규칙을 한정해 돌리거나 그 노트가 낙관적이었을 수 있다. **측정으로 확인하라**: `.github/
  workflows/ci.yml`의 ruff 호출 인자 확인. 실제 게이트가 무엇인지 정하기 전엔 일괄 ruff fix 금지.
- **2-환경 분리 [HARD]**: 이 repo = 빌드 하네스(MoAI-ADK) + 제품(sci-adk) 공존. 빌드 하네스
  (root `CLAUDE.md`/`.moai/`/`.claude/`) 건드리지 마라. 키트는 연구 워크스페이스에
  `sci-adk init-session`으로만 설치.
- **IEAM-P8은 별도 repo**(`~/research/ieam-followup-p8`, NOT on GitHub). 읽기 전용으로 참조
  했다. 거기 쓰려면 사용자 확인 먼저([[feedback_confirm-before-destructive]]).
- **커밋 메시지는 반드시 `-F 파일`로**: 중첩 `wsl bash -lc '...'`는 본문 아포스트로피/괄호에서
  깨진다. Write로 `\\wsl.localhost\ubuntu\tmp\msg.txt` 작성 → `git commit -F /tmp/msg.txt`.
  이번 세션도 이 방식으로 처리(`87a9869`). 커밋 footer = `🗿 MoAI <email@mo.ai.kr>`.
- **WSL 셸 인용 함정**: 중첩 single-quote 안 `for`/`sed`/python `-c`가 비거나 깨질 수 있다 —
  핵심 검증은 단순 명령으로 재확인. 측정이 이상하면 하니스부터 의심(추정<측정).
- **CLI 바이너리**: 이 repo editable(`~/.local/bin/sci-adk`). verb 안 보이면
  `pip install -e . --force-reinstall --no-deps`. 별도 `~/research/sci-adk/.venv`는 무관, 건드리지 마.
- **WSL 호출**: python/pytest/git은 `wsl.exe bash -lc 'cd ~/sci-adk && ...'`; 파일 편집은 UNC
  `\\wsl.localhost\ubuntu\home\cyjoe\sci-adk\...`.
- **worktree 금지**: pytest `pythonpath=src` + editable install이 메인 src를 가리킴.
- **Import 컨벤션**: 단일 루트 `from sci_adk...`; `from src.sci_adk...` 금지.
- **render PURE 불변식**: `render/*.py`는 fs/네트워크/LLM 0.

## 핵심 결정 (보존)

- record/belief 분리, frozen Spec, append-only Evidence, revisable Claim.
- `sci-adk verify` = 유일 판정 권한 (LLM은 pass/fail 결정 안 함 — adoption-roadmap LLM-as-verdict CUT).
- **G-A/A3 split(이번 세션)**: A1a(Verifier/record 일반성)=DONE(IEAM-P8); A1b(자율 experiment
  adapter-seam 일반성)=1.0 scope-out. 일반성 = *verification* 일반성이지 *autonomous-experiment*
  일반성이 아니다. 공개 표면은 그렇게만 주장.
- 커널/adapter seam(F4): 커널(core/loop/render)은 도메인-free, adapter→kernel만 허용
  (AST 강제). 도메인 코드는 capability adapter에만([[feedback_domain-generality]]).
- "확인 후 삭제"류 = 사용자 게이트; 같은 턴 자가확인+삭제 금지([[feedback_confirm-before-destructive]]).

## 참고 문서 / 메모리

- **G-A/A3 단일 출처**: `design/g-a-a3-decision.md`
- 출시 준비 게이트: `design/release-readiness.md` (G-A 해소, G-E 적용 반영; 남은 G-B/G-D)
- 채택 로드맵: `design/adoption-roadmap.md` (§A3/§6 일반화 게이트 RESOLVED)
- 피봇/커널: `design/sci-adk-as-moai.md` · `design/rigor-shell-architecture.md` · `design/abstractions.md`
- SPEC: `.moai/specs/SPEC-PAPER-GATE-001/` + `design/paper-writing-enforcement.md`
- IEAM-P8(외부): `~/research/ieam-followup-p8/` (package/, runs/ieam-p8-*), 메모리 [[ieam-p8-baf-prediction]]
- 자동 메모리: `MEMORY.md` 인덱스 + 신규 [[project_g-a-a3-decision]].

## 시작 절차

1. 위 "상태 확인" 실행 (HEAD=핸드오프 커밋, 1362 passed, README 문구 확인)
2. `design/g-a-a3-decision.md` + `design/release-readiness.md` §3/§7 정독
3. 사용자와 다음 방향 결정 — 권장: **G-B(논문) 또는 G-D(버전/태그)**. ruff 게이트 불일치도
   초반에 짚어 둘 것.
4. 결정된 작업 진행 (체크포인트 모드: 매 게이트 사용자 승인 + verify-don't-assume).

---

Version: 1.0
Source: sci-adk session 8 (2026-06-26) — G-A 키스톤 A3 판정 해소(split: A1a DONE / A1b scope-out,
근거 IEAM-P8) + G-E 정직성 문구 적용(structural 레벨); 커밋 `87a9869`
Status: G-A RESOLVED (verification claim), G-E APPLIED; 다음 = G-B(논문)·G-D(버전/태그)
Last Updated: 2026-06-26
