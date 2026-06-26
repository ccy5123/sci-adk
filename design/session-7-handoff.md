# sci-adk — Session 7 Handoff (다음 세션 시작 프롬프트)

> 이 문서를 다음 세션의 시작점으로 사용해라. session 6(출판 기능 F1/F2/F3) 이후
> **SPEC-PAPER-GATE-001(논문/패키징을 엔진 게이트 아래로)을 5개 pillar 전부 +
> EC 스윕 + DoD + R1까지 완주**하고, sci-adk가 실사용 가능 상태임을 확인한 세션이
> 남긴 것이다. 너는 그 세션과 동일 인격이 아니다 — 산출물을 자료로 받아 이어가는
> 새 세션이다. 이전 판단을 무비판 계승하지 말고 필요하면 의심해라.

## 너의 역할

sci-adk의 공동 설계자. sci-adk는 **domain-general rigor / verification ADK**다 —
referee/scorekeeper. 핵심 철학은 record(증거, 단조·append-only)와 belief(주장,
비단조·수정가능)의 분리. **agents propose; the engine judges by frozen criteria.
No self-certification. 판정 경로는 결정적·규칙기반.** (`sci-adk verify` = 유일 판정)

## ★ 가장 먼저 이해할 것

- **SPEC-PAPER-GATE-001이 완전히 닫혔다.** 손-입력 숫자(P2), cite-key/섹션순서
  (P3/P4), cross-run merge-render(P5), EC-1..EC-6, 전체 DoD, 그리고 잔여 R1까지 전부
  master에 있다. 단일 출처 SPEC: `.moai/specs/SPEC-PAPER-GATE-001/`, 설계 근거
  `design/paper-writing-enforcement.md`.
- **OD-7(merge-render record/prose 경계)은 사용자 제약으로 확정됐다**: 숫자·표·그림은
  record-추출(게이트)·산문은 자유 + **`main.tex`엔 매크로(`\evval`) 없이 평범한 리터럴**
  — 리뷰어가 보는 소스에 정체불명 단축어가 들어가면 안 된다는 사용자 요구. 판정은
  여전히 **결정적 P2 number-audit**(LLM 판정 아님); emit 값이 풀(`02_data/claims_all.csv`)
  멤버라 by-construction 통과, 손-편집 비-record 값은 FAIL.
- **sci-adk는 실사용 가능**하다(CLI end-to-end smoke 통과). 이번 세션에 stale 바이너리
  문제도 해결했다(아래 "현재 위치").
- 남은 마일스톤급 미검증은 여전히 **G-A(2nd-domain 일반성)** — release-readiness의 키스톤.

## 현재 위치

- 브랜치 **`master`**, HEAD **`6e96103`**. 단일-master 워크플로(feature 브랜치 안 씀).
- 전체 테스트 **1362 passed** (`python3 -m pytest -q`, ~17s).
- **`~/.local/bin/sci-adk` 바이너리 stale 문제는 해결됐다** — 이번 세션에 `pip install
  -e . --force-reinstall --no-deps`로 이 repo를 가리키게 재설치. 이제 PATH 바이너리가
  `package`/`pubreqs`/`pkgreqs`/`verify`/`render`/`run`/`resolve`/`status`/`init-session`
  전부 노출(shebang `/usr/bin/python3`, 이 repo의 editable src). 단 별도 구설치
  `~/research/sci-adk/.venv`는 여전히 존재(무관, 건드리지 마라).

## 상태 확인 (시작 시 먼저 실행)

```bash
# 이 dev repo는 WSL ~/sci-adk 에 있다. Windows 호스트의 Bash 도구는
# wsl.exe bash -lc 'cd ~/sci-adk && ...' 로 감싸라. pytest는 pythonpath=src.
wsl.exe bash -lc 'cd ~/sci-adk && git log --oneline -8 && python3 -m pytest -q 2>&1 | tail -2'
# 기대: HEAD=6e96103, 1362 passed
wsl.exe bash -lc 'sci-adk --help 2>&1 | grep -oE "package|pubreqs|verify" | sort -u'
# 기대: package / pubreqs / verify (바이너리 최신 확인)
```

## Session 6 이후 진행 (session 7 산출물)

session-6-handoff(HEAD `6732bd1`, 1227 tests) 이후 — 전부 SPEC-PAPER-GATE-001:

- `28ed3ff` docs(spec): SPEC-PAPER-GATE-001 P1–P5 (5 pillar 정의)
- `10356c1`→`c3ca867` **M1** (P1 비-공허 mandatory 게이트 + P2 number-audit; MP-5/AC-1/2/5/6)
- `b0c4af2` **P2 stage-ii** — package audit exact-only(`allow_derived=False`) +
  `from_package` 풀 union(`02_data/*.csv` ∪ `06_provenance/run_index.csv`); `a/a=1` 누수 봉쇄
- `c0388e1` **M2** — P3(cite-key shape/disambiguation/unpublished-WARN/per-run cite-resolution)
  + P4(section-order: 선언 FAIL/미선언 WARN, body_word_range gating AC-3); OD-4/5/6 확정
- `c5ea553` **M3 (P5)** — cross-run merge-render: `render/package.py::_results_merge_render`가
  `02_data/claims_all.csv`에서 Claim별 point_statistic+threshold를 **평범한 리터럴**로
  `main.tex` Results에 추출(OD-7 클린 소스), 나머지 섹션은 산문 슬롯. AC-7 3테스트.
- `ab44609` **EC 스윕 + DoD 종료** — EC-3 page-number + EC-5 uncited-defined-key shape
  테스트 추가, EC-4 문서 모순 수정(OD-8 즉시 거부, no-grace), DoD 전 항목 체크
- `6e96103` **R1** — per-run advisory 채널: `VerifyReport.paper_advisory`(passed 미포함),
  `_check_paper_requirements`가 `(problems, warnings)` 반환, OD-5(미발행 인용)+OD-6
  (미선언-순서) WARN을 per-run에 라우팅 + CLI 표면화

검증: 매 단계 전체 스위트 green(1227→1362) + 실제 CLI end-to-end smoke + 생성 `main.tex`
육안 확인. 메모리: [[paper-writing-enforcement-spec]] 갱신.

**추가(비코드)**: sci-adk 실사용성 확인 + 바이너리 재설치; 유사 출시 도구 인터넷 조사
— 동일 출시품 없음. 가장 가까운 건 **논문/개념**(EviBound arXiv 2511.05524 = frozen
contract + 결정적 verify 게이트 + 엔진 판정 + null 처리로 sci-adk와 사상적 쌍둥이;
Claim-Level Auditability/AAR 2602.13855; PreReg Audit Shield = 빈 README). 주류 출시품
(Sakana AI Scientist 등)은 정반대 철학(자율 저자, player). → 방법론 논문 related work 재료.

## 다음 세션 작업 (트랙별; 권장 진입 G-A)

**G-A — 일반성 게이트 (키스톤; release-readiness가 "이거 없이 나머지는 시기상조"라 명시)**
- `design/release-readiness.md` §3 참조. 중심 주장 "domain-general rigor 커널"은 **2번째
  도메인이 커널 수정 0으로 adapter seam에 plug-in 될 때만** 검증된다. 현재 adapter는
  T-1(분자)만(`src/sci_adk/adapter/t1_*.py`), in-repo `runs/`도 전부 T-1.
- **사용자가 G-A 연구를 진행 중**(연구 데이터는 user-gated). 새 연구 없이 지금 가능한
  진입점 = **A3 판정**: IEAM-P8(생태독성, `~/research/ieam-followup-p8`)이 2nd-domain
  게이트를 충족하는가? IEAM-P8은 borrow/operational 경로(in-session 에이전트 실험)였지
  in-repo capability-adapter seam이 아니었다 — 이게 형식 게이트로 카운트되는지 미결.
  충족이면 일반화 거의 종결, 미충족이면 A4(in-repo T-2 adapter 요건) 설계.

**Track E — 연구 런 → 논문 (도구 완비, 사용자 주도)**
- sci-adk가 usable하니 실제 제안서를 `run→execute→derive-claim→resolve→verify→render→
  pubreqs/pkgreqs freeze→package→verify <ws>`로 끝까지 구동 가능. T-1(godel) 또는 T-2.
- 단서(이월): `runs/t1-godel/science.md`의 G1–G4 약과학 지적을 spec amendment로 해소 후 진행.

**Track G-B — 방법론 논문** (G-A에 의존; T-2가 2nd 케이스 스터디)
- Option 4(방법론 + T-1/T-2 케이스). related work에 이번 세션 조사(EviBound/AAR/AI-Scientist
  비판) 활용. G-A 전엔 시기상조.

**잔여(accepted; 합의대로 보류)**
- **R2** — P5 `main.tex` 인라인 figure `\includegraphics`(현재 03_figures 코로케이션+si.tex
  참조). 실제 논문 작성 시 가치. 그림-존재 안전 처리 필요.
- **R3** — per-run number-audit가 `0`/`1`을 self-op로 무조건 derivable 처리. 패키지는
  exact-only라 무영향. **won't-fix 권장**(닫으면 복잡도만 증가).

## 알려진 이슈 / 함정

- **2-환경 분리 [HARD]**: 이 repo = 빌드 하네스(MoAI-ADK) + 제품(sci-adk) 공존. 키트는
  연구 워크스페이스에 `sci-adk init-session`으로 설치, **절대 이 빌드 repo의 `.claude/`에
  설치 금지**. 빌드 하네스(root `CLAUDE.md`/`.moai/`/`.claude/`)는 건드리지 마라.
- **커밋 메시지는 반드시 `-F 파일`로**: 중첩 `wsl bash -lc '...'` heredoc은 본문의
  아포스트로피/괄호에서 깨진다(이번 세션도 두 번 깨진 뒤 Write로 메시지 파일 작성 →
  `git commit -F /tmp/msg.txt`로 해결). UNC `\\wsl.localhost\ubuntu\tmp\...`로 쓰면 됨.
- **WSL 셸 인용 함정**: `for v in a b c` 같은 루프도 중첩 single-quote 안에서 변수가
  비어 거짓 결과를 낼 수 있다 — 핵심 검증은 단순 명령으로 재확인(이번에 "verb MISSING"
  오판이 이 때문이었음). 측정 결과가 이상하면 하니스부터 의심.
- **CLI 바이너리**: 이제 최신(이 repo editable). 혹시 verb가 안 보이면
  `pip install -e . --force-reinstall --no-deps`.
- **WSL 호출**: 모든 python/pytest/git은 `wsl.exe bash -lc 'cd ~/sci-adk && ...'`.
  파일 편집은 UNC 경로 `\\wsl.localhost\ubuntu\home\cyjoe\sci-adk\...`.
- **worktree 금지**: pytest `pythonpath=src` + editable install이 메인 src를 가리킴 —
  worktree면 격리/테스트가 깨진다. 메인 트리에서 foreground로.
- **Import 컨벤션**: 단일 루트 `from sci_adk...`. 절대 `from src.sci_adk...` 금지.
- **포매터**: 프로젝트 게이트는 `ruff check`(통과). `ruff format`은 HEAD조차 "would
  reformat"이라 **전면 재포맷 금지** — 건드린 부분만.
- **render PURE 불변식**: `render/*.py`는 fs/네트워크/LLM 접근 0. 모든 fs는 compiler가.

## 핵심 결정 (보존)

- record/belief 분리, frozen Spec, append-only Evidence, revisable Claim.
- `sci-adk verify` = 유일 판정 권한 (LLM은 pass/fail 결정 안 함 — adoption-roadmap CUT).
- **OD-7(P5)**: 숫자·표·그림 record-추출(게이트)/산문 자유; `main.tex`는 매크로 없는
  평범한 리터럴(리뷰어-클린 소스); 판정은 결정적 P2(by-construction 풀 멤버십).
- 출판/패키지 게이트도 동일: 게이트 요건=결정적 체커, advisory는 비게이트(이제 per-run도
  `paper_advisory` 채널 보유), 계약 부재 시 거부(OD-1 strict/OD-8 immediate, no-grace).
- 도메인 코드는 capability adapter에만 — 커널/일반 CLI/출판 표면은 도메인 0
  ([[feedback_domain-generality]]).
- "확인 후 삭제"류 지시 = 사용자의 게이트; 같은 턴 자가확인+삭제 금지
  ([[feedback_confirm-before-destructive]]).

## 참고 문서 / 메모리

- **SPEC 단일 출처**: `.moai/specs/SPEC-PAPER-GATE-001/` (spec/acceptance/plan) +
  설계 근거 `design/paper-writing-enforcement.md` (§6a = P5 빌드 내역)
- 출시 준비 게이트: `design/release-readiness.md` (G-A 키스톤 = 일반성)
- 출판 기능: `design/paper-publishing-requirements.md` · 근-제출 패키지
  `design/near-submission-package.md`
- 피봇/커널: `design/sci-adk-as-moai.md` · `design/rigor-shell-architecture.md` ·
  `design/abstractions.md`
- 채택 로드맵: `design/adoption-roadmap.md` (LLM-as-verdict 영구 CUT; 일반성 게이트)
- 자동 메모리: `MEMORY.md` 인덱스 + `project_*`/`feedback_*` 토픽(새 세션 자동 로드).
  이 세션 갱신: [[paper-writing-enforcement-spec]].

## 시작 절차

1. 위 "상태 확인" 실행 (HEAD=6e96103, 1362 passed, 바이너리 verb 노출 확인)
2. `design/release-readiness.md` §3(G-A) + 이 문서 "다음 세션 작업" 정독
3. 사용자와 다음 방향 결정 — 권장: **G-A 키스톤**(A3 판정이 새 연구 없이 가능한 진입).
   사용자가 G-A 연구를 진행 중이라 했으니 그 진척부터 동기화.
4. 결정된 작업 진행 (체크포인트 모드: 매 게이트 사용자 승인 + verify-don't-assume).

---

Version: 1.0
Source: sci-adk session 7 (2026-06-26) — SPEC-PAPER-GATE-001 완주(M1+P2-ii+M2+M3+EC+DoD+R1),
sci-adk 실사용성 확인 + 바이너리 재설치, 유사 출시 도구 조사(동일품 없음)
Status: SPEC-PAPER-GATE-001 COMPLETE; 다음 키스톤 = G-A(2nd-domain 일반성, 사용자 연구 진행 중)
Last Updated: 2026-06-26
