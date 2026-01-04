# 🚀 새 컴퓨터에서 호텔 검색 시스템 설치 가이드

> 이 가이드는 아무것도 설치되지 않은 새 컴퓨터에서 프로젝트를 처음부터 실행하는 방법입니다.

---

## 📋 목차

1. [시스템 요구사항](#1-시스템-요구사항)
2. [필수 소프트웨어 설치](#2-필수-소프트웨어-설치)
3. [프로젝트 다운로드](#3-프로젝트-다운로드)
4. [환경 설정](#4-환경-설정)
5. [실행하기](#5-실행하기)
6. [문제 해결](#6-문제-해결)

---

## 1. 시스템 요구사항

### 최소 사양
- **OS**: macOS 10.15+, Ubuntu 20.04+, Windows 10+ (WSL2)
- **메모리**: 4GB RAM 이상 (8GB 권장)
- **디스크**: 10GB 여유 공간
- **네트워크**: 인터넷 연결 (초기 설치 시)

### 예상 소요 시간
- **설치**: 20-30분
- **데이터 준비**: 10-15분
- **총 소요 시간**: 약 40분

---

## 2. 필수 소프트웨어 설치

### 2.1 Git 설치

#### macOS
```bash
# Xcode Command Line Tools 설치 (Git 포함)
xcode-select --install

# 확인
git --version
# git version 2.x.x
```

#### Ubuntu/Linux
```bash
sudo apt update
sudo apt install -y git

# 확인
git --version
```

#### Windows
1. [Git for Windows](https://git-scm.com/download/win) 다운로드
2. 설치 후 Git Bash 열기

---

### 2.2 Python 3.8+ 설치

#### macOS
```bash
# Homebrew 설치 (없으면)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python 설치
brew install python@3.11

# 확인
python3 --version
# Python 3.11.x
```

#### Ubuntu/Linux
```bash
sudo apt update
sudo apt install -y python3 python3-pip

# 확인
python3 --version
```

#### Windows (WSL2)
```bash
# WSL2 Ubuntu에서 실행
sudo apt update
sudo apt install -y python3 python3-pip
```

---

### 2.3 Docker 설치

#### macOS
1. [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/) 다운로드
2. 설치 후 Docker Desktop 실행
3. 상단 메뉴바에 Docker 아이콘 확인

```bash
# 확인
docker --version
# Docker version 24.x.x

docker-compose --version
# Docker Compose version v2.x.x
```

#### Ubuntu/Linux
```bash
# Docker 설치
sudo apt update
sudo apt install -y docker.io docker-compose

# 현재 사용자를 docker 그룹에 추가
sudo usermod -aG docker $USER

# 로그아웃 후 다시 로그인 (또는 재부팅)

# 확인
docker --version
```

#### Windows
1. [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) 다운로드
2. WSL2 백엔드 사용 설정
3. 설치 후 재부팅

---

## 3. 프로젝트 다운로드

### 방법 A: Git Clone (권장)

```bash
# 1. 원하는 위치로 이동
cd ~/Desktop  # 또는 원하는 디렉토리

# 2. GitHub에서 클론
git clone https://github.com/Bmony/hotel_study.git

# 3. 프로젝트 디렉토리 이동
cd hotel_study

# 4. 파일 확인
ls -la
# README.md, backend/, frontend/, docker/, data/ 등이 보여야 함
```

### 방법 B: ZIP 다운로드

1. https://github.com/Bmony/hotel_study 접속
2. 우측 상단 **Code** → **Download ZIP** 클릭
3. 압축 해제
4. 터미널에서 압축 해제한 폴더로 이동

```bash
cd ~/Downloads/hotel_study-main  # 압축 해제 위치
```

---

## 4. 환경 설정

### 4.1 Python 패키지 설치

```bash
cd hotel_study  # 프로젝트 루트 디렉토리

# 필수 Python 라이브러리 설치
pip3 install elasticsearch==8.11.0
pip3 install geopy==2.4.0
pip3 install requests==2.31.0
pip3 install Flask==3.0.0
pip3 install Flask-CORS==4.0.0

# 또는 requirements.txt가 있다면
pip3 install -r requirements.txt
```

**설치 확인**:
```bash
python3 -c "import elasticsearch; import geopy; import flask; print('✅ 패키지 설치 완료')"
```

---

### 4.2 Elasticsearch + Kibana 실행

```bash
# docker 디렉토리로 이동
cd docker

# Docker Compose로 Elasticsearch 실행
docker-compose up -d

# 실행 확인 (1-2분 대기 필요)
docker ps
# elasticsearch와 kibana 컨테이너가 보여야 함
```

**헬스 체크** (중요!):
```bash
# Elasticsearch 준비될 때까지 대기 (30초-1분)
while true; do
  STATUS=$(curl -s http://localhost:9200/_cluster/health 2>/dev/null | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
  echo "Elasticsearch 상태: $STATUS"
  if [ "$STATUS" = "green" ] || [ "$STATUS" = "yellow" ]; then
    echo "✅ Elasticsearch 준비 완료!"
    break
  fi
  echo "⏳ 대기 중... (30초 후 재시도)"
  sleep 30
done
```

**성공 확인**:
```bash
curl http://localhost:9200
# {"name":"...","cluster_name":"...","version":{...}} 출력되면 성공
```

---

## 5. 실행하기

### 5.1 데이터 준비 (처음 1회만)

```bash
# 프로젝트 루트로 이동
cd /path/to/hotel_study  # 본인의 프로젝트 경로

# Step 1: OSM 데이터 다운로드 (30초)
bash data/scripts/download_osm_data.sh

# Step 2: 데이터 강화 (5-10분 소요)
python3 backend/indexing/hotel_data_enricher.py

# Step 3: Elasticsearch 인덱싱 (10초)
python3 backend/indexing/elasticsearch_indexer.py

# 완료 확인
curl -s http://localhost:9200/hotels/_count | grep -o '"count":[0-9]*'
# "count":200 정도 나오면 성공 (호텔 개수)
```

**예상 출력**:
```
📥 OpenStreetMap 데이터 다운로드 중...
✅ 서울 호텔 데이터 다운로드 완료

[1/200] 처리 중...
  📍 주변 POI 수집: 북촌게스트하우스
  ✅ 북촌게스트하우스 - 랭킹: 100, POI: 10개
...

🔧 인덱스 'hotels' 생성 중...
✅ 인덱싱 완료! 성공: 198개
```

---

### 5.2 웹 페이지 실행

#### 옵션 A: 간단한 프론트엔드 (서버 불필요)

```bash
cd frontend

# 브라우저에서 파일 열기
open map-search.html  # macOS
# xdg-open map-search.html  # Linux
# start map-search.html  # Windows
```

**브라우저 수동 열기**:
1. Chrome/Safari 실행
2. 메뉴 → 파일 → 파일 열기
3. `hotel_study/frontend/map-search.html` 선택

---

#### 옵션 B: API 서버 + AI 폴리곤 (고급 기능)

**Terminal 1**: API 서버 실행
```bash
cd backend/search
python3 api_server.py

# 출력:
# 🚀 AI 폴리곤 API 서버 시작...
#    http://localhost:5001
```

**Terminal 2**: 프론트엔드 열기
```bash
cd frontend
open ai-polygon-test.html
```

---

## 6. 문제 해결

### 6.1 Docker 오류

**증상**: `Cannot connect to the Docker daemon`

**해결**:
```bash
# macOS: Docker Desktop이 실행 중인지 확인
# 상단 메뉴바에 Docker 아이콘이 있어야 함

# Linux: Docker 서비스 시작
sudo systemctl start docker
sudo systemctl enable docker
```

---

### 6.2 Elasticsearch 연결 안됨

**증상**: `Connection refused [Errno 61]`

**해결**:
```bash
# 1. Docker 컨테이너 상태 확인
docker ps | grep elasticsearch

# 2. 컨테이너가 없으면 재실행
cd docker
docker-compose down
docker-compose up -d

# 3. 로그 확인
docker logs elasticsearch

# 4. 1-2분 대기 후 재시도
curl http://localhost:9200
```

---

### 6.3 Python 모듈 없음

**증상**: `ModuleNotFoundError: No module named 'elasticsearch'`

**해결**:
```bash
# pip가 설치되어 있는지 확인
pip3 --version

# 패키지 재설치
pip3 install --upgrade elasticsearch geopy requests flask flask-cors
```

---

### 6.4 포트 충돌

**증상**: `Port 9200 is already in use`

**해결**:
```bash
# macOS/Linux: 9200 포트 사용 프로세스 확인
lsof -i :9200

# 프로세스 종료 (PID는 위에서 확인)
kill -9 <PID>

# 또는 Docker 포트 변경
# docker/docker-compose.yml 에서 "9200:9200" → "9201:9200"으로 변경
```

---

### 6.5 데이터 강화 중 Overpass API 오류

**증상**: `⚠️ Overpass API 오류: 504`

**해결**:
```bash
# 1. 네트워크 확인
ping overpass-api.de

# 2. 타임아웃 증가 (hotel_data_enricher.py 수정)
# [out:json][timeout:60] → [out:json][timeout:120]

# 3. Rate Limit 대기 시간 증가
# time.sleep(1.5) → time.sleep(3.0)

# 4. 재실행
python3 backend/indexing/hotel_data_enricher.py
```

---

## 7. 체크리스트

설치가 완료되었는지 확인하세요:

```bash
# ✅ Git 설치됨
git --version

# ✅ Python 설치됨
python3 --version

# ✅ Docker 실행 중
docker ps

# ✅ Elasticsearch 응답함
curl http://localhost:9200

# ✅ 호텔 데이터 있음
curl http://localhost:9200/hotels/_count

# ✅ 프론트엔드 파일 있음
ls frontend/map-search.html
```

모두 ✅ 이면 성공입니다!

---

## 8. 빠른 시작 스크립트

전체 과정을 자동화한 스크립트:

```bash
#!/bin/bash
# 파일명: quick_start.sh

set -e  # 에러 시 중단

echo "🚀 호텔 검색 시스템 빠른 시작"

# 1. Docker 확인
if ! docker ps > /dev/null 2>&1; then
    echo "❌ Docker가 실행되지 않았습니다. Docker Desktop을 실행하세요."
    exit 1
fi

# 2. Elasticsearch 실행
cd docker
docker-compose up -d
cd ..

# 3. Elasticsearch 대기
echo "⏳ Elasticsearch 준비 중..."
sleep 30

# 4. 데이터 준비
if [ ! -f "data/raw/seoul_hotels.json" ]; then
    echo "📥 OSM 데이터 다운로드..."
    bash data/scripts/download_osm_data.sh
fi

if [ ! -f "data/processed/enriched_hotels.json" ]; then
    echo "🔧 데이터 강화..."
    python3 backend/indexing/hotel_data_enricher.py
fi

echo "📦 Elasticsearch 인덱싱..."
python3 backend/indexing/elasticsearch_indexer.py

# 5. 프론트엔드 열기
echo "🌐 웹 페이지 열기..."
open frontend/map-search.html

echo "✅ 완료!"
```

**사용법**:
```bash
chmod +x quick_start.sh
./quick_start.sh
```

---

## 9. 다음 단계

설치가 완료되었다면:

1. **검색 테스트**:
   - 브라우저에서 "강남", "명동", "게스트하우스" 검색

2. **GitHub Pages 배포** (선택):
   - https://bmony.github.io/hotel_study/

3. **데이터 업데이트**:
   ```bash
   bash data/scripts/download_osm_data.sh
   python3 backend/indexing/hotel_data_enricher.py
   python3 backend/indexing/elasticsearch_indexer.py
   ```

4. **README.md 참고**:
   - 고급 기능 및 상세 설명

---

## 10. 지원

- **문서**: `README.md` 참고
- **GitHub**: https://github.com/Bmony/hotel_study
- **이슈**: GitHub Issues에 문제 보고

---

**마지막 업데이트**: 2025-01-04
**작성자**: Hotel Study Team
