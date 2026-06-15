# sci-adk Quick Start Guide

> Next Session Quick Reference

## 1. 첫 번째로 할 것

### 상태 확인 (3분)

```bash
# Core types working? (sci_adk importable after `pip install -e .` or with PYTHONPATH=src)
PYTHONPATH=src python3 -c "from sci_adk.core.spec import Spec; print('✅ OK')"

# Git clean?
git status

# README 확인
cat README.md | head -50
```

## 2. 선택지 (하나 선택)

### A. Docker 테스트 (추천, 30분)
```bash
cd environments/python-base
docker build -t sci-adk-python-base .
cd ../..
python3 demo_e2e.py
ls -la runs/spec-t1-demo/
```

### B. Milestone 2 계획 (1시간+)
- Loop controller 구현
- Convergence detection
- Paper rendering 또는 DecisionRule engine

### C. 테스트 실행 (15분)
```bash
pip install pytest
pytest tests/ -v
```

## 3. 필독 문서

1. **design/session-2-handoff.md** (전체 상황)
2. **README.md** (프로젝트 개요)
3. **design/milestone-1.md** (완료된 것)

## 4. 커맨드 레퍼런스

```bash
# E2E 데모
python3 demo_e2e.py

# 단위 테스트
pytest tests/test_spec.py -v
pytest tests/test_evidence.py -v
pytest tests/test_claim.py -v

# Docker 빌드
docker build -t sci-adk-python-base environments/python-base/

# Git 로그
git log --oneline -10
```

## 5. 문제 발생 시

**Docker 없음**: `sudo apt-get install docker.io`
**Pytest 없음**: `pip install pytest`
**Import error**: `cd /home/cyjoe/sci-adk` 먼저
**Permission denied**: `sudo usermod -aG docker $USER`

## 6. 다음 목표

Milestone 1 완료 → Milestone 2 시작:
- Full loop 구현
- Paper rendering
- DecisionRule engine
- Academic MCP integration

---

**세션 시작**: 이 파일부터 읽을 것
**우선순위**: A → B → C 순서
**도움**: design/session-2-handoff.md 참조
