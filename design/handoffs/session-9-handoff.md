# sci-adk — Session 9 Handoff (다음 세션 시작 프롬프트)

> 이 문서를 다음 세션의 시작점으로 사용해라. session 8(G-A 키스톤 A3 해소 + G-E 적용)
> 이후, **G-D D1(표면 freeze)을 마감**하고 **G-B(방법론 논문)를 JOSS로 확정·작성**하고
> **v0.2.0을 공개 릴리스**한 세션이 남긴 것이다. 너는 그 세션과 동일 인격이 아니다 —
> 산출물을 자료로 받아 이어가는 새 세션이다. 이전 판단을 무비판 계승하지 말고 필요하면
> 의심해라(특히 JOSS 일정·1.0 타이밍).

## 너의 역할

sci-adk의 공동 설계자. sci-adk는 **domain-general rigor / verification ADK**다 —
referee/scorekeeper. 핵심 철학은 record(증거, 단조·append-only)와 belief(주장,
비단조·수정가능)의 분리. **agents propose; the engine judges by frozen criteria.
No self-certification. 판정 경로는 결정적·규칙기반.** (`sci-adk verify` = 유일 판정)

## ★ 가장 먼저 이해할 것

- **G-D·G-B가 JOSS 제출이라는 한 점으로 수렴했다.** 출시(1.0)와 논문(JOSS)은 분리된 게
  아니라 **JOSS accept 시점에 합류**한다(거기서 v1.0.0 태그 + Zenodo DOI를 동시에 낸다).
- **G-B 논문 = sci-adk *도구* 논문(JOSS), NOT 도메인 연구 논문.** venue=JOSS는 **무료(APC 0)**
  하드 제약 때문(SoftwareX $1560 / Patterns 탈락). 사용자의 T-1/T-2 등 수학→화학 연구는
  **별도 도메인 저널**(J. Math. Chem. 등) 논문이며 JOSS 논문의 blocker가 **아니다**.
  단일 출처: 메모리 [[project_research-roadmap-and-joss]].
- **JOSS 2026 정책 = 제출 전 ≥6개월 public 이력 + 릴리스/issue/PR 증거 필요.** repo
  `ccy5123/sci-adk`는 **2026-06-01 생성/공개** → 제출 가능 **≈ 2026-12-01**. 그래서 지금은
  **v1.0.0을 박지 않고 v0.2.0만** 릴리스해 "open-development 증거"를 쌓는 중. **1.0.0은
  제출 임박(~12월), 표면이 실사용 검증된 뒤**에 박는다. (이전 "태그는 accept 때만"은 부정확
  → 릴리스는 창 동안, Zenodo만 accept 때로 정정됨.)
- **표면(1.0 계약)은 이미 고정됐다(D1 DONE).** CLI 17 verb/83 플래그 + 큐레이션 29심볼
  Python API. 퍼블리싱 계층 포함. 단일 출처: `design/surface-freeze-analysis.md`.

## 현재 위치

- 브랜치 **`master`**, HEAD **`ae1ce30`**(이 핸드오프 커밋은 그 다음). **origin 동기**(push됨).
- **태그 `v0.2.0` + GitHub 릴리스 라이브**: https://github.com/ccy5123/sci-adk/releases/tag/v0.2.0
- 전체 테스트 **1369 passed**(`python3 -m pytest -q`, ~17s). 마지막 코드 변경=`84480ac`(D1);
  이후 커밋은 문서/릴리스 전용이라 스위트 불변.
- 이번 세션 6커밋: `ffcffb5`(D1 분석) `84480ac`(D1 마감 API) `af8e3eb`(JOSS draft)
  `d575fae`(draft 마감) `656dc8a`(G-B B1 갱신) `ae1ce30`(0.2.0 cut).

## 상태 확인 (시작 시 먼저 실행)

```bash
# dev repo는 WSL ~/sci-adk. Windows Bash 도구는 wsl.exe bash -lc 'cd ~/sci-adk && ...'로 감싸라.
wsl.exe bash -lc 'cd ~/sci-adk && git log --oneline -3 && git tag -l && python3 -m pytest -q 2>&1 | tail -2'
# 기대: HEAD=핸드오프 커밋(ae1ce30 위), 태그 v0.2.0, 1369 passed
wsl.exe bash -lc 'cd ~/sci-adk && grep -nE "^version" pyproject.toml && git rev-list --count origin/master..master'
# 기대: version 0.2.0, ahead 0 (또는 핸드오프 미push 시 1)
```

## Session 8 이후 진행 (session 9 산출물)

- **G-D D1 마감**: `design/surface-freeze-analysis.md`(신규, 1.0 표면 계약 단일 출처) +
  `src/sci_adk/__init__.py`(빈 파일→큐레이션 29심볼 re-export) + `tests/test_public_api.py`
  (신규 7테스트: `__all__` 고정·별표 import·kernel 모듈 해석·adapter 비노출). 1369 passed.
- **G-B 확정·작성**: venue=JOSS. `paper/paper.md`(844단어, JOSS 7섹션) + `paper/paper.bib`
  (EviBound 2511.05524 / AAR 2602.13855 / AI-Scientist 2408.06292, **arXiv 대조 검증**).
  G-E 정직 scoped(verification 일반성만). 저자=개인연구자(Independent Researcher).
- **v0.2.0 릴리스**: pyproject+CITATION 0.1.0→0.2.0, CHANGELOG [0.2.0], tag+GitHub 릴리스,
  master push(그동안 ahead 15였음 — 세션들 누적 미push 해소).
- 문서 추적: `design/release-readiness.md` D1=[DONE], B1=[DONE]+G-B 재프레이밍.
- 메모리: 신규 [[project_research-roadmap-and-joss]] + MEMORY.md 인덱스 2줄 + surface-freeze.

검증: D1은 verify-don't-assume(seam 불변식·1369 스위트·런타임 import 실증), JOSS 요건/비용은
**WebSearch/WebFetch 측정**(추측 금지), 매 게이트 AskUserQuestion 사용자 확정.

## 다음 세션 작업 (대부분 시간-게이트, ~12월까지)

**즉시 급한 것 없음** — JOSS 제출은 6개월 만기(≈2026-12-01)까지 대기. 그 사이:

1. **open-development 증거 축적** — 가끔 push, public issue/PR(JOSS eligibility 강화).
2. **표면 실사용(dogfood)** — T-1을 sci-adk 파이프라인으로 돌려 §2 표면을 1.0 확정 전 검증.
3. **(선택) T-1 도메인 논문** — *JOSS와 별개*. 이건 사용자의 J. Math. Chem./J. Cheminformatics
   논문이며, `runs/t1-godel/science.md`의 **G1–G4 약과학 지적을 amend-spec으로 해소** 후
   paper-grade화해야 한다. JOSS 논문 blocker 아님.

**~12월 제출 임박 시 (G-D D2 full + D3 + JOSS)**
- v1.0.0 태그(pyproject/CITATION/CHANGELOG 1.0.0) + Zenodo 아카이브(DOI) → JOSS 제출.
- D4(PyPI publish)는 선택·JOSS 무관. 메타데이터는 이미 준비됨.

**G-B 잔여**
- AI disclosure 문구·acknowledgements는 이미 확정(개인연구·펀딩 없음). B5(CITATION↔paper DOI)는
  JOSS accept 시 CrossRef DOI로 마감.

## 알려진 이슈 / 함정

- **6개월 만기일은 *공개 전환일* 기준 [신규]**: created_at=2026-06-01이지만, private로 만들었다가
  나중에 public 전환했다면 그 전환일이 기준. 확정하려면 github.com/settings/security-log의
  `repo.access`("made public") 이벤트 확인.
- **ruff 게이트 불일치 = 해소됨 [session 8에서 이월·이번에 측정]**: CI는 `pytest -m "not
  integration"`만 실행(`.github/workflows/ci.yml`), **ruff 게이트 없음**. `ruff check .`의 202
  에러는 **전부 tests/의 pytest fixture-import 오탐**(F811/F401), src는 클린. **`ruff --fix`
  금지**(fixture import 삭제로 스위트 깨짐). 게이트 둘 거면 `--fix`가 아니라 per-file-ignores.
- **v1.0.0 아직 미태깅, v0.2.0만**: 1.0으로 섣불리 bump하지 마라. 표면 실사용 검증 + 제출 임박
  전까지 1.0 안정성 약속을 박지 않는 게 이번 세션의 결정.
- **2-환경 분리 [HARD]**: 이 repo = 빌드 하네스(MoAI-ADK) + 제품(sci-adk) 공존. 빌드 하네스
  (root `CLAUDE.md`/`.moai/`/`.claude/`) 건드리지 마라.
- **IEAM-P8은 별도 repo**(`~/research/ieam-followup-p8`, NOT on GitHub). 읽기 전용 참조.
- **커밋 메시지는 `-F 파일`로**: 중첩 `wsl bash -lc '...'`는 본문 아포스트로피/괄호에서 깨진다.
  Write로 `\\wsl.localhost\ubuntu\tmp\msg.txt` 작성 → `git commit -F /tmp/msg.txt`. footer =
  `🗿 MoAI <email@mo.ai.kr>`.
- **WSL 셸 인용 함정**: 중첩 single-quote 안 `for` 루프/변수가 빈 결과를 낸다(이번에 두 번 겪음).
  핵심 검증은 단순 명령으로 재확인.
- **docx 읽기**: `Read`는 .docx 바이너리 거부. zipfile로 word/document.xml 추출(스크립트를
  /tmp에 쓰고 인자로 경로 전달). 한글 파일명은 NFC/NFD 불일치로 `-f` 실패 → glob 우회.
- **CLI 바이너리**: 이 repo editable(`~/.local/bin/sci-adk`). 별도 `~/research/sci-adk/.venv`는 무관.
- **WSL 호출**: python/pytest/git/gh는 `wsl.exe bash -lc 'cd ~/sci-adk && ...'`; 파일 편집은 UNC.
- **worktree 금지**: pytest `pythonpath=src` + editable install이 메인 src를 가리킴.
- **Import 컨벤션**: 단일 루트 `from sci_adk...`; `from src.sci_adk...` 금지.
- **render PURE 불변식**: `render/*.py`는 fs/네트워크/LLM 0.

## 핵심 결정 (보존)

- record/belief 분리, frozen Spec, append-only Evidence, revisable Claim. `sci-adk verify`=유일 판정.
- **G-A/A3 split(session 8)**: A1a(verification 일반성)=DONE(IEAM-P8); A1b(자율 experiment seam)=
  1.0 scope-out. 공개 표면은 domain-general *verification* 커널만 주장(G-E).
- **D1 표면 계약(session 9)**: CLI(17 verb/83 플래그) + 큐레이션 29심볼 Python API(`__init__.py`)
  = 1.0 안정 범위. 퍼블리싱 계층(package/pkgreqs/pubreqs) 포함. 가드 `tests/test_public_api.py`.
- **venue=JOSS(session 9)** [HARD: APC 0]. 도구 논문. 도메인 연구 논문은 별도.
- **0.2.0 now / 1.0.0 near-submission(session 9)**: 1개월된 어린 표면을 5개월 미리 1.0으로 잠그지
  않는다. v0.2.0=JOSS open-development 증거.
- 사용자 = 계산·수리화학+환경 연구자(서울시립대), 10과제 수학→화학 로드맵(T-1=sci-adk의 T-1,
  T-2=p진), 연구 내용은 사용자 공급, 저자 소속=개인연구자([[project_research-roadmap-and-joss]]).
- "확인 후 삭제"류 = 사용자 게이트([[feedback_confirm-before-destructive]]); 도메인-일반 표면
  유지([[feedback_domain-generality]]).

## 참고 문서 / 메모리

- **표면 freeze 단일 출처**: `design/surface-freeze-analysis.md`
- 출시 준비 게이트: `design/release-readiness.md`(G-D D1 DONE·G-B B1 DONE+재프레이밍; G-A/G-C/G-E done)
- G-A/A3: `design/g-a-a3-decision.md`
- JOSS 논문: `paper/paper.md` + `paper/paper.bib` · `CHANGELOG.md`([0.2.0])
- 피봇/커널: `design/sci-adk-as-moai.md` · `design/rigor-shell-architecture.md` · `design/abstractions.md`
- 자동 메모리: `MEMORY.md` 인덱스 + [[project_research-roadmap-and-joss]](신규, JOSS·로드맵·일정).

## 시작 절차

1. 위 "상태 확인" 실행 (HEAD, 태그 v0.2.0, 1369 passed, version 0.2.0).
2. `design/surface-freeze-analysis.md` + `design/release-readiness.md` §4(G-B)/§6(G-D) 정독.
3. 사용자와 방향 결정 — **대부분 ~12월까지 시간-게이트**. 근시일 가능 작업: open-development
   증거 축적(push/issue), T-1 dogfood로 표면 검증, (선택) T-1 도메인 논문(G1–G4 해소 후).
   1.0 태그·Zenodo·JOSS 제출은 제출 임박(~12월)에.

---

Version: 1.0
Source: sci-adk session 9 (2026-06-30) — G-D D1 마감(표면 freeze + 큐레이션 Python API) +
G-B JOSS 논문 draft 작성·확정(venue=JOSS, no-APC) + v0.2.0 공개 릴리스(JOSS open-development
증거); 커밋 `ffcffb5`→`ae1ce30`, 스위트 1369
Status: G-A RESOLVED, G-C/G-E done, **G-D D1 DONE + 0.2.0 released**, **G-B B1 DONE(draft)**;
다음 = ~12월 JOSS 제출(그때 v1.0.0 + Zenodo) + 그 사이 open-development 축적
Last Updated: 2026-06-30
