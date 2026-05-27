# sci-adk Session 3: Quick Start

> 1분만 읽고 바로 시작하세요

## 🚀 3단계 시작

### 1. 상태 확인 (30초)

```bash
cd /home/cyjoe/sci-adk

# Core types 작동?
python3 -c "from src.sci_adk.core.spec import Spec; print('✅ OK')"

# Git clean?
git status
```

### 2. 문서 빠르게 읽기 (30초)

- **QUICKSTART.md** - 옵션 3가지 (A: Docker, B: Milestone 2, C: Tests)
- **README.md** - 프로젝트 개요

### 3. 작업 선택

**Option A: Docker 테스트** (추천, 30분)
```bash
cd environments/python-base
docker build -t sci-adk-python-base .
cd ../..
python3 demo_e2e.py
```

**Option B: Milestone 2** (계획, 1시간+)
- Loop controller 또는 Paper rendering

**Option C: Tests 실행** (15분)
```bash
pip install pytest
pytest tests/ -v
```

---

## 📊 현재 상태

✅ Milestone 1 완료
- Core types: 1,360 lines
- Parser: 306 lines
- Docker env: 338 lines
- Loop: 409 lines
- Tests: 2,634 lines
- **Total**: ~5,300 lines

⏸️ 미검증: Docker 실행, pytest

---

## ⚠️ 문제 시

**Docker 없음**: `sudo apt-get install docker.io`
**Import error**: `cd /home/cyjoe/sci-adk` 먼저
**Permission**: `sudo usermod -aG docker $USER`

---

## 📖 상세 정보

- **전체 가이드**: `PROMPT_SESSION3.md`
- **핸드오프**: `design/session-2-handoff.md`

---

**지금 시작하세요!** 🎯

Version: Quick (1-minute read)
Last Updated: 2026-05-27
