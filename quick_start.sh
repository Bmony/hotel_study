#!/bin/bash
# 호텔 검색 시스템 빠른 시작 스크립트
# 새 컴퓨터에서 처음 실행할 때 사용

set -e  # 에러 시 중단

echo "🚀 호텔 검색 시스템 빠른 시작"
echo "================================"
echo ""

# 프로젝트 루트 디렉토리로 이동
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Git 확인
echo "📍 Step 1: 필수 소프트웨어 확인..."
if ! command -v git &> /dev/null; then
    echo "❌ Git이 설치되지 않았습니다."
    echo "   설치: https://git-scm.com/downloads"
    exit 1
fi
echo "✅ Git: $(git --version)"

# 2. Python 확인
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3이 설치되지 않았습니다."
    echo "   macOS: brew install python@3.11"
    echo "   Linux: sudo apt install python3 python3-pip"
    exit 1
fi
echo "✅ Python: $(python3 --version)"

# 3. Docker 확인
if ! command -v docker &> /dev/null; then
    echo "❌ Docker가 설치되지 않았습니다."
    echo "   설치: https://www.docker.com/products/docker-desktop/"
    exit 1
fi
echo "✅ Docker: $(docker --version)"

# 4. Docker 실행 확인
if ! docker ps > /dev/null 2>&1; then
    echo "❌ Docker가 실행되지 않았습니다."
    echo "   macOS: Docker Desktop 실행"
    echo "   Linux: sudo systemctl start docker"
    exit 1
fi
echo "✅ Docker 실행 중"
echo ""

# 5. Python 패키지 설치
echo "📍 Step 2: Python 패키지 설치..."
pip3 install -q elasticsearch==8.11.0 geopy==2.4.0 requests==2.31.0 flask==3.0.0 flask-cors==4.0.0
echo "✅ Python 패키지 설치 완료"
echo ""

# 6. Elasticsearch 실행
echo "📍 Step 3: Elasticsearch 실행..."
cd docker
docker-compose up -d
cd ..
echo "✅ Elasticsearch 시작됨"
echo ""

# 7. Elasticsearch 준비 대기
echo "📍 Step 4: Elasticsearch 준비 대기 (최대 2분)..."
MAX_WAIT=120
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if curl -s http://localhost:9200/_cluster/health > /dev/null 2>&1; then
        STATUS=$(curl -s http://localhost:9200/_cluster/health | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        if [ "$STATUS" = "green" ] || [ "$STATUS" = "yellow" ]; then
            echo "✅ Elasticsearch 준비 완료! (상태: $STATUS)"
            break
        fi
    fi
    echo "   대기 중... ($ELAPSED초 경과)"
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo "❌ Elasticsearch 시작 실패 (타임아웃)"
    echo "   docker logs elasticsearch 로 로그 확인"
    exit 1
fi
echo ""

# 8. 데이터 다운로드
echo "📍 Step 5: OSM 데이터 다운로드..."
if [ ! -f "data/raw/seoul_hotels.json" ]; then
    bash data/scripts/download_osm_data.sh
    echo "✅ 데이터 다운로드 완료"
else
    echo "✅ 데이터 이미 존재 (건너뛰기)"
fi
echo ""

# 9. 데이터 강화
echo "📍 Step 6: 데이터 강화 (5-10분 소요)..."
if [ ! -f "data/processed/enriched_hotels.json" ]; then
    echo "   ⏳ 처리 중... (200개 호텔 처리 예정)"
    python3 backend/indexing/hotel_data_enricher.py
    echo "✅ 데이터 강화 완료"
else
    # 파일 크기 확인
    SIZE=$(wc -c < data/processed/enriched_hotels.json)
    if [ $SIZE -lt 100000 ]; then
        echo "⚠️  enriched_hotels.json 크기가 작습니다. 재생성합니다."
        python3 backend/indexing/hotel_data_enricher.py
    else
        echo "✅ 강화된 데이터 이미 존재 (건너뛰기)"
    fi
fi
echo ""

# 10. Elasticsearch 인덱싱
echo "📍 Step 7: Elasticsearch 인덱싱..."
python3 backend/indexing/elasticsearch_indexer.py
echo "✅ 인덱싱 완료"
echo ""

# 11. 결과 확인
echo "📍 Step 8: 결과 확인..."
COUNT=$(curl -s http://localhost:9200/hotels/_count | grep -o '"count":[0-9]*' | grep -o '[0-9]*')
echo "✅ 인덱싱된 호텔: ${COUNT}개"
echo ""

# 12. 프론트엔드 열기
echo "📍 Step 9: 웹 페이지 열기..."
if [ -f "frontend/map-search.html" ]; then
    open frontend/map-search.html 2>/dev/null || \
    xdg-open frontend/map-search.html 2>/dev/null || \
    echo "   수동으로 열기: file://$(pwd)/frontend/map-search.html"
    echo "✅ 브라우저 열림"
else
    echo "❌ frontend/map-search.html 파일을 찾을 수 없습니다"
fi
echo ""

echo "🎉 설치 및 실행 완료!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📱 접속 방법:"
echo "   브라우저: file://$(pwd)/frontend/map-search.html"
echo ""
echo "🔍 테스트 검색어:"
echo "   - 강남"
echo "   - 명동"
echo "   - 게스트하우스"
echo ""
echo "🌐 GitHub Pages:"
echo "   https://bmony.github.io/hotel_study/"
echo ""
echo "📚 상세 문서:"
echo "   - README.md (전체 시스템 가이드)"
echo "   - SETUP_GUIDE.md (새 컴퓨터 설치 가이드)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
