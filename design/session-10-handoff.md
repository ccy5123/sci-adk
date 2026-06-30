# sci-adk — Session 10 Handoff (다음 세션 시작 프롬프트)

> 이 문서를 다음 세션의 시작점으로 사용해라. session 9(G-D D1 표면 freeze + G-B JOSS
> draft + v0.2.0 릴리스) 이후, session 10은 **JOSS 논문을 외부 리뷰 3라운드로 단단하게
> 다듬고**, **레포를 외부채택 가능 상태로 정비**하고, **JOSS 자격(레포 트랙)을 단일 문서로
> 명문화**한 세션이다. 너는 그 세션과 동일 인격이 아니다 — 산출물을 자료로 받아 이어가는
> 새 세션이다. 이전 판단을 무비판 계승하지 말고 필요하면 의심해라.

## 너의 역할

sci-adk의 공동 설계자. sci-adk = **domain-general rigor / verification ADK**(referee, not
player). 핵심: record(증거, 단조·append-only) ≠ belief(주장, 비단조·수정가능). **agents
propose; the engine judges by frozen criteria. No self-certification.** `sci-adk verify` =
유일 판정(결정적·규칙기반·LLM 없음).

## ★ 가장 먼저 이해할 것

- **원고는 더 이상 게이트가 아니다. 게이트는 레포로 넘어갔다.** 외부 리뷰 3라운드로 `paper/paper.md`는
  심사 통과 수준이 됐다. 실제 accept/reject를 가르는 건 이제 **레포의 두 속성**이고, 둘 다 시간/사람
  의존이라 오늘 편집으로 안 풀린다. 단일 출처: **`design/joss-eligibility-plan.md`**.
  - **P0-1**(6개월 공개 이력 ≈ 2026-12-01) = cadence만 분산하면 자동 해소(쉬운 게이트). repo
    `ccy5123/sci-adk` 2026-06-01 PUBLIC. **함정: 커밋의 113/126개가 2026-06 한 달 집중(burst)** —
    7~12월을 비우면 "생성 후 방치"로 읽힌다. 가끔이라도 commit/issue/release로 분산하라.
  - **P0-2**(단독저자 외부사용/커뮤니티 증거) = **진짜 병목.** 현재 public issue 0, 외부 사용자 0.
    위조 불가 — *다른 사람*이 sci-adk를 돌리고 흔적(이슈)을 남겨야 한다. 가장 가치 있는 단일 행동 =
    **외부 사용자 1명 + public issue 흔적.** ~11월까지 0이면 정직한 fallback(연기/공저자/venue 재검토).
- **arXiv → JOSS는 허용된다(검증됨 2026-06-30).** JOSS 정책: preprint(arXiv 등)는 제출 전/중/후
  언제든 가능하며 *previous publication으로 치지 않는다*. 단 **JOSS 논문 자체(750~1750단어 도구 설명)를
  arXiv에 올리는 건 가치가 낮다** — arXiv에 어울리는 건 더 substantial한 methods 글이거나 사용자의
  도메인 논문(T-1 등). 전략적 활용: 더 두꺼운 sci-adk methods 글 또는 도메인 논문을 arXiv에 올리면
  **가시성↑ → 외부 사용자 유입(P0-2에 간접 기여) + 인용 가능 timestamp**. JOSS 요건을 *대체*하진 않고
  *먹여줄* 수 있다. (참고: arXiv 첫 투고는 카테고리별 endorsement가 필요할 수 있음 — 미검증, 확인 요).
- **venue = JOSS [HARD: APC 0].** 도구 논문. 도메인 연구(T-1 수학→화학)는 **별도** 도메인 저널
  (J. Math. Chem. 등)이며 JOSS blocker 아님. 단일 출처 [[project_research-roadmap-and-joss]].
- **표면(1.0 계약)은 session 9에서 freeze됨(D1 DONE).** `design/surface-freeze-analysis.md`.

## 현재 위치

- 브랜치 **`master`**, HEAD **`d1fb401`**(이 핸드오프 커밋은 그 다음). **origin 동기(push됨)**, ahead 0.
- 태그 **`v0.2.0`** + GitHub 릴리스 라이브. 전체 테스트 **1369 passed**. version 0.2.0(pyproject/CITATION).
- 이번 세션 코드/문서 변경은 **paper/ + README + design/ 뿐**(src/test 무변경 → 스위트 불변).
- 이번 세션 2커밋: `d402dbe`(논문 3라운드 리뷰 반영) · `d1fb401`(README 외부채택 + joss-eligibility-plan).

## Session 9 이후 진행 (session 10 산출물)

- **논문 3라운드 외부 리뷰 반영**(`d402dbe`): 제목 단축; Summary/Statement-of-need가 *구체·테스트가능
  속성*(offline LLM-free 재검증 + 기계강제 kernel/adapter 경계)으로 시작; State of the field에 워크플로/
  provenance build-vs-reuse(Snakemake/DVC/Sumatra/ReproZip) + TMS/PROV/pre-reg 계보 추가; `verify`를
  *internal consistency ≠ validity*(necessary-not-sufficient)로 한정; **freeze/digest 주장 정직 분리**
  (staging order=intra-run 선행 / SHA-256 digest=변조방지 / 둘 다 trusted timestamp도 아니고 run간
  rule-shopping도 못 막음 — pre-registration 한계 상속); T-1을 repo 동봉 verify-green run으로 톤 하향.
  `paper.bib` = 10 refs, 신규 7개 DOI까지 **WebSearch 검증(환각 0; aar 4저자 순서까지 대조)**. ~1246단어.
- **README 외부채택 패스**(`d1fb401`): version/test 동기(0.2.0/1369), "external release deferred"
  자기모순 → "openly developed and free to use" 프레이밍, Support & Contributing 섹션 신설, 저자명
  Chan Young Joe 통일. **Quick Start 정직화**: 동봉 `verify runs/t1-godel`(clean)로 시작.
- **`design/joss-eligibility-plan.md` 신규**: 레포 트랙 단일 출처(P0-1 cadence / P0-2 외부사용 / 정직 fallback).
- **IEAM-P8 게이트-게이밍 진단**(별건, 읽기전용 참조 `~/research/ieam-followup-p8`): 그쪽 `ieam_conformance_check.py`가
  `\section{}` exact-match(`heads==req`)라 `\subsection{Conclusions}`로 우회당함 = Goodhart/자기인증.
  **대조로 sci-adk 자체 IMRaD 처리 측정**: `render/pubreqs_checks.py`는 존재+상대순서(exact 아님) + `\section*`도
  매칭 + frozen pubreqs 계약 + `verify` 내부 → 그 게이밍 유인이 구조적으로 없음(단, 미선언 순서는 WARN뿐).
- **메모리 갱신**: [[research-adk-productization]] "self/lab" SUPERSEDED → 외부화; [[project_research-roadmap-and-joss]]
  세션10 진척; MEMORY.md 인덱스 2줄.

검증 규율: bib 환각검사 + freeze/digest 한계는 **측정/WebSearch**(추측 금지); quickstart "버그"는 테스트를 읽고
**의도된 strict-science 동작**으로 자기정정(CC 메타룰 #3); 매 게이트 AskUserQuestion 사용자 확정.

## 다음 세션 작업 (대부분 사용자/시간 의존)

**사용자(사람)만 할 수 있는 것:**
1. **P0-2 — 외부 사용자 1명 + public issue.** 최우선·최난관. 동료/랩/수리화학 커뮤니티 누군가가 실제로 돌리고
   이슈로 흔적을 남기게. 안 되면 ~11월 fallback 판단.
2. **저자 소속/펀딩 문자 그대로 정확한지 확정**(JOSS 허위 시 펀더 통지) — 미검증 리스크.
3. **6개월 공개일 확정** — private→public 전환 있었으면 github.com/settings/security-log `repo.access` 이벤트.
4. **cadence 유지** — 7~12월 활동 분산(burst 희석).

**~12월 제출 임박 시 (내가 prep 도울 수 있음):**
- v1.0.0 태그(pyproject/CITATION/CHANGELOG 1.0.0) + Zenodo 아카이브(DOI) → JOSS 제출. (G-D D2 full + D3)
- 제출 전 체크리스트: paper HTML 주석 strip, bib DOI 최종 재확인, README/CITATION 일관성.
- D4(PyPI)는 선택·JOSS 무관.

**별건(JOSS blocker 아님):**
- T-1 도메인 논문(J. Math. Chem.) — 사용자 연구 내용 + `runs/t1-godel/science.md` G1–G4 약과학 해소 후.
- IEAM-P8 companion revision(대응레터/CRediT/bib) — 별도 repo.
- IEAM 체커 게이밍-내성 패치 — 별도 repo, 사용자 (c) 진단까지로 보류함.
- (선택) arXiv preprint(두꺼운 methods/도메인 글)로 가시성·외부유입 — 위 ★ 참조.

## 알려진 이슈 / 함정

- **IEAM-P8은 별도 repo·읽기 전용**(`~/research/ieam-followup-p8`, NOT on GitHub). sci-adk 본체와 혼동 금지.
- **`sci-adk run --t1-demo`는 strict 기본값에서 *의도적으로* halt**(bare 데모에 negative control 없음, G3). 버그 아님.
  README Quick Start는 동봉 `verify runs/t1-godel`로 시작하도록 고침. 데모 smoke는 `--no-strict-science`.
- **6개월 만기일 = 공개 전환일 기준.** created_at 2026-06-01이지만 private→public 전환 있었으면 그 날 기준.
- **ruff = 게이트 아님**: 202 에러 전부 tests/ fixture-import 오탐, src 클린. `--fix` 금지.
- **v1.0.0 미태깅(v0.2.0만).** 표면 실사용 검증 + 제출 임박 전까지 1.0 안정성 약속 박지 마라.
- **2-환경 분리 [HARD]**: 이 repo = 빌드 하네스(MoAI-ADK) + 제품(sci-adk) 공존. 빌드 하네스 건드리지 마라.
- **커밋 메시지는 `-F 파일`로**(중첩 인용 깨짐): Write로 `\\wsl.localhost\ubuntu\tmp\msg.txt` → `git commit -F /tmp/msg.txt`.
  footer = `🗿 MoAI <email@mo.ai.kr>`.
- **WSL 호출**: python/pytest/git/gh는 `wsl.exe bash -lc 'cd ~/sci-adk && ...'`; 파일 편집은 UNC. worktree 금지.
- **Import 컨벤션**: 단일 루트 `from sci_adk...`; `from src.sci_adk...` 금지. render PURE 불변식(fs/net/LLM 0).

## 핵심 결정 (보존)

- record/belief 분리, frozen Spec, append-only Evidence, revisable Claim. `sci-adk verify`=유일 판정.
- **외부화(session 10)**: "self/lab, external release deferred" → 외부 공개·사용 가능(JOSS 경로). README 반영.
- **venue=JOSS [HARD: APC 0]**. 도구 논문. 도메인 연구는 별도. **arXiv preprint 허용**(previous publication 아님).
- **0.2.0 now / 1.0.0 near-submission(~12월)**: 어린 표면을 미리 1.0으로 잠그지 않는다.
- **논문 정직 경계(G-E)**: domain-general *verification* 커널만 주장(2nd 도메인=ecotox). 자율 experiment 시스템 아님.
- 사용자 = 계산·수리화학+환경 연구자(서울시립대), 저자 소속=개인연구자([[project_research-roadmap-and-joss]]).
- "확인 후 삭제"류 = 사용자 게이트([[feedback_confirm-before-destructive]]); 도메인-일반 표면([[feedback_domain-generality]]).

## 참고 문서 / 메모리

- **레포 트랙 단일 출처**: `design/joss-eligibility-plan.md`(P0-1/P0-2 + fallback) ← session 10 핵심 신규
- JOSS 논문: `paper/paper.md` + `paper/paper.bib`(10 refs DOI-검증)
- 표면 freeze: `design/surface-freeze-analysis.md` · 출시 게이트: `design/release-readiness.md`
- 피봇/커널: `design/sci-adk-as-moai.md` · `design/rigor-shell-architecture.md` · `design/abstractions.md`
- 자동 메모리: MEMORY.md 인덱스 + [[project_research-roadmap-and-joss]](JOSS·로드맵·session10 진척).

## 시작 절차

1. 상태 확인: `wsl.exe bash -lc 'cd ~/sci-adk && git log --oneline -3 && git tag -l && python3 -m pytest -q 2>&1 | tail -2'`
   (기대: HEAD=핸드오프 커밋, 태그 v0.2.0, 1369 passed).
2. `design/joss-eligibility-plan.md` 정독 — 다음 작업의 99%가 여기 P0-1/P0-2.
3. 사용자와 방향 결정 — **대부분 사용자/시간 의존**(P0-2 외부사용이 최우선). 제출(v1.0.0+Zenodo)은 ~12월.

---

Version: 1.0
Source: sci-adk session 10 (2026-06-30) — 논문 3라운드 외부 리뷰 반영(`d402dbe`) + 레포 외부채택
패스 + `design/joss-eligibility-plan.md` 신규(`d1fb401`) + IEAM-P8 게이트-게이밍 진단(별건) + 메모리 외부화 갱신.
Status: G-A RESOLVED, G-C/G-E done, G-D D1 DONE, **G-B 원고 심사통과 수준**; 게이트는 레포(P0-1 cadence /
**P0-2 외부사용=병목**)로 이동; 제출(v1.0.0+Zenodo) ~12월.
Last Updated: 2026-06-30
