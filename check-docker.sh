#!/bin/bash
# Docker 설치 확인 스크립트

echo "🔍 Docker 설치 상태 확인..."
echo ""

# Docker 버전 확인
if command -v docker &> /dev/null; then
    echo "✅ Docker 설치됨"
    docker --version
else
    echo "❌ Docker가 설치되지 않음"
    echo ""
    echo "Docker Desktop for Windows 설치가 필요합니다:"
    echo "1. https://www.docker.com/products/docker-desktop/ 방문"
    echo "2. Docker Desktop Installer.exe 다운로드 및 실행"
    echo "3. 'Use WSL 2 based engine' 옵션 체크"
    echo "4. 설치 후 재시작"
    exit 1
fi

# Docker 데몬 실행 확인
if docker info &> /dev/null; then
    echo "✅ Docker 데몬 실행 중"
else
    echo "❌ Docker 데몬이 실행되지 않음"
    echo "Docker Desktop을 시작하고 다시 시도하세요."
    exit 1
fi

# Docker 그룹 확인
echo ""
echo "🔧 Docker 권한 확인..."
if groups | grep -q docker; then
    echo "✅ 사용자가 docker 그룹에 있음"
else
    echo "⚠️  사용자가 docker 그룹에 없음"
    echo "Docker Desktop을 사용하는 경우 일반적으로 sudo가 필요 없습니다."
    echo "그래도 permission 에러가 발생하면:"
    echo "  sudo usermod -aG docker \$USER"
    echo "  newgrp docker"
    echo "또는 WSL을 재시작하세요."
fi

echo ""
echo "✅ Docker 설치 확인 완료!"
