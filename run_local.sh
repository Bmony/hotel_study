#!/bin/bash

echo "🚀 호텔 검색 시스템 로컬 실행"
echo "================================"

# Step 1: Elasticsearch 상태 확인
echo ""
echo "📍 Step 1: Elasticsearch 확인..."
if ! curl -s http://localhost:9200 > /dev/null; then
    echo "❌ Elasticsearch가 실행되지 않았습니다"
    echo ""
    echo "Docker로 Elasticsearch 실행:"
    echo "  cd docker && docker-compose up -d"
    exit 1
fi
echo "✅ Elasticsearch 실행 중"

# Step 2: 데이터 확인
echo ""
echo "📍 Step 2: 인덱싱된 호텔 데이터 확인..."
COUNT=$(curl -s http://localhost:9200/hotels/_count | grep -o '"count":[0-9]*' | grep -o '[0-9]*')

if [ -z "$COUNT" ] || [ "$COUNT" -eq 0 ]; then
    echo "⚠️  호텔 데이터가 없습니다. 파이프라인을 먼저 실행하세요:"
    echo ""
    echo "  bash data/scripts/download_osm_data.sh"
    echo "  python3 backend/indexing/hotel_data_enricher.py"
    echo "  python3 backend/indexing/elasticsearch_indexer.py"
    exit 1
fi

echo "✅ 호텔 데이터: ${COUNT}개"

# Step 3: 프론트엔드 HTML 파일 열기
echo ""
echo "📍 Step 3: 웹 페이지 열기..."
echo ""

# 사용 가능한 HTML 파일 목록
echo "사용 가능한 페이지:"
echo "  1. map-search.html           - 기본 지도 검색"
echo "  2. map-with-polygons.html    - 폴리곤 + 지도"
echo "  3. search-test.html          - 검색 테스트"
echo "  4. ai-polygon-test.html      - AI 폴리곤 (API 서버 필요)"
echo ""

# 기본 페이지 열기
FRONTEND_DIR="/Users/jeongjinseo/Desktop/개발/hotel_study/frontend"
DEFAULT_PAGE="${FRONTEND_DIR}/map-search.html"

echo "🌐 기본 페이지 열기: map-search.html"
open "$DEFAULT_PAGE"

echo ""
echo "✅ 완료!"
echo ""
echo "📱 접속 방법:"
echo "   - 브라우저가 자동으로 열립니다"
echo "   - 또는 직접 파일 열기:"
echo "     file://${DEFAULT_PAGE}"
echo ""
echo "🔍 테스트 검색어:"
echo "   - 강남"
echo "   - 명동"
echo "   - 게스트하우스"
echo ""
