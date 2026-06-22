# sci-adk — IEAM-followup-P8 (M6 descriptor-correction) Handoff

> 이 문서를 다음 세션의 시작점으로 사용해라. 2026-06-22 클라우드 세션이 남긴
> **null-result 핸드오프**다. 너는 그 세션과 동일 인격이 아니다 — 산출물을 자료로
> 받아 이어가는 새 세션이다. 아래 "전사된 주장"을 무비판 계승하지 말고, 실제로
> 푸시된 파일에 비춰 다시 측정해라.

## 한 줄 요약

요청받은 **IEAM-followup-P8 / M6 descriptor-correction** 워크스페이스가 이 세션의
컨테이너에 **존재하지 않았다**. 전체 파일시스템과 git 전체 이력을 측정한 결과
null. 비가역 작업(Spec.amend / prior-work / novelty 기록)은 한 건도 수행하지
않았다. 상태 = **DIVERGED**, DONE 아님.

## 너의 역할

sci-adk의 공동 설계자. sci-adk는 **research compiler**다: 4칸 제안서를 받아
paper draft + working code + evidence trail을 산출한다. 핵심 철학은 record(증거,
단조·append-only)와 belief(주장, 비단조·수정가능)의 분리.
근거: `.claude/rules/sci-adk-constitution.md` "Core Philosophy".

## ★ 가장 먼저 이해할 것 — 측정으로 확인된 사실 (신뢰도: 높음)

이번 세션은 원격 클라우드 컨테이너에서 `ccy5123/sci-adk`만 fresh clone 한 상태로
시작했다. 실제 CWD = `/home/user/sci-adk`, `$HOME=/root`. launch 프롬프트가
`cd ~/research/ieam-followup-p8` 로 가정한 워크스페이스는 이 컨테이너 어디에도 없다.

측정 명령과 결과 (basis: 직접 실행):

```bash
find / -type d -name "ieam-followup-p8"            # 0건
find / -name "HANDOFF_FROM_BUILD_HARNESS.md"        # 0건
find / -name "RECON.md"                             # 0건 (recon/REPORT.md 는 별개·T-1 정찰)
find / -name "proposal.md"                          # 0건
find / -name "regression_table_n14.csv"            # 0건 (P7 baseline 부재)
find / -name "spec.json"                            # runs/t1-godel/spec.json 만 존재
git log --all --oneline --name-only | grep -iE "ieam|p8|m6|descriptor|abraham|HANDOFF"  # P8 0건
git stash list                                      # 비어있음
git worktree list                                   # 단일 (/home/user/sci-adk)
```

- 유일하게 실재하는 run = `runs/t1-godel/` (constitution이 명시한 레퍼런스 워크플로,
  `.claude/rules/sci-adk-constitution.md` "Reference Workflow: T-1").
- `origin/master`·`origin/claude/zealous-wright-ogincb` 양쪽 tip(`ca5d837`)에도 P8
  아티팩트 0건. 즉 로컬에만 있고 원격에 push 되지 않은 것으로 보인다 (신뢰도: 중,
  basis: 원격은 push된 것만 받으므로).

자기검증(meta-rule 3): 삭제/다른 브랜치/stash/worktree 가능성을 모두 확인해 음성.
"엉뚱한 위치를 봤을" 가능성은 배제됨.

## 재개 선행 조건 (둘 중 하나 충족 전엔 Step 5~8 진행 불가)

1. **(권장) P8 워크스페이스를 원격에 push.** 개발 브랜치
   `claude/zealous-wright-ogincb` (리포 `ccy5123/sci-adk`)에 아래를 올려라:
   - `HANDOFF_FROM_BUILD_HARNESS.md` (Phase A.5 종료 상태 + Step 5~8 절차)
   - `RECON.md` (RDKit-Abraham descriptor 개량 근거)
   - `proposal.md` (4-pane, M6=Option A)
   - `runs/ieam-p8-m6-descriptor-correction/spec.json` (FROZEN Spec v2)
   - `p7-package/IEAM_followup_P7/02_data/regression_table_n14.csv` (합격선 baseline)
2. 또는 위 입력을 채팅에 직접 제공.

> ⚠️ 어느 쪽이든, 아래 "전사된 주장"은 launch 프롬프트에서 옮긴 것일 뿐 **이
> 컨테이너의 어떤 파일로도 검증되지 않았다**. push된 실제 파일과 대조해 다시
> 측정한 뒤에만 신뢰해라. 불일치 시 실제 파일이 우선.

## 전사된 주장 (launch 프롬프트 출처, 미검증 — 대조용)

- 개량 대상: SMILES → RDKit Abraham descriptor (A, B, S, V, L). 고-K_OW
  폴리염화방향족이 문제 구간.
- M6 corrector: 6개 UFZ 앵커(HCB, PCB18/52/101/155, Mirex)의 per-descriptor 평균
  오프셋 = 5개 스칼라. **설계는 Option A로 동결**(첫 held-out 평가 전 동결 규율).
- 가설/임계값: H1 primary shortfall slope(N=14) ≤ +1.02 / H2 secondary ≤ +0.50.
- 합격선 baseline: P7 회귀표 M5 +1.60, M4 +1.02.
- Spec v2 thresholds: hyp-001/002/003 (내용 미확인).

## 재개 절차 (순서 고정, anti-HARKing 준수)

1. `git fetch --all` 후 P8 워크스페이스 위치를 **측정**(추측 금지). 없으면 다시 멈춰
   null로 기록.
2. 5개 입력 정독. RECON 파라미터 선정 + Spec v2 thresholds(hyp-001/002/003)가 P7
   실측 baseline(+1.60/+1.02)에 비춰 타당한지 **비판적으로** 검토.
   - 이의 있으면 *Evidence 기록 전*에 한해 `Spec.amend`(사용자 확인 후).
   - 없으면 그대로 동결.
3. **Step 5 (prior-work)** → **Step 6 (novelty 2-kind)**: held-out shortfall 회귀를
   **fit 하기 전에** 기록한다 (anti-HARKing 핵심).
4. **Step 7**: M6 corrector(5 스칼라 오프셋) 구현 + docker Python 실행.
5. **Step 8**: resolve + Stop verify-gate 통과 확인 + LaTeX 렌더.
   - SUPPORTED novelty claim은 해당 {hyp, kind}의 found-nothing 검색이 기록돼야만
     성립.
   - verify-gate는 진짜 fail-stop. DIVERGED/미해결이면 DONE 금지.

## anti-HARKing 규율 (절대 위반 금지 — launch 프롬프트 명령)

- prior-work·novelty 결정은 held-out shortfall 회귀 fit **전에** 기록.
- M6 설계는 첫 held-out 평가 전 동결 (이미 Option A).
- SUPPORTED novelty claim ⇐ 그 {hyp, kind}의 found-nothing 검색 기록 필수.
- Stop verify-gate = fail-stop.

## 이 세션이 한 것 / 안 한 것

- 한 것: 전체 파일시스템·git 이력 측정, null-result 확인, 본 핸드오프 작성.
- 안 한 것(의도적): Spec.amend 0건, prior-work 기록 0건, novelty 기록 0건, Evidence
  append 0건. → 재개 시 Evidence 로그는 여전히 비어 있어 Spec 자유 수정 가능 구간.

## 환경 메모

- OA 취득용: `export UNPAYWALL_EMAIL=ccy5123ccy@gmail.com`
- docker Python: `runs/t1-godel`가 쓰는 `environments/python-base/` 이미지 참고
  (Docker 미설치 시 Step 7 막힘 — 환경 문제로 null 기록).
- 이 컨테이너의 `/home/user/sci-adk`는 빌드 하니스 + sci-adk 제품 스켈레톤이다.
  P8 연구 워크스페이스와 혼동 금지 (constitution "Critical Environment Separation").

---

Version: 1.0
Source: IEAM-followup-P8 launch session (2026-06-22), null-result measurement
Status: BLOCKED — P8 워크스페이스 원격 push 또는 입력 제공 전까지 Step 5~8 불가
Last Updated: 2026-06-22
