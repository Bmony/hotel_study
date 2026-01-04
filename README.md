# 호텔 검색 시스템 - 데이터 파이프라인 완벽 가이드

> 🎯 **목적**: OpenStreetMap 데이터를 활용한 서울 호텔 검색 시스템 구축
> 📅 **최종 업데이트**: 2025-01-04
> 🏗️ **아키텍처**: OSM → 데이터 강화 → Elasticsearch 인덱싱

---

## 🚀 빠른 시작

### 새 컴퓨터에서 처음 설정하기
[📘 SETUP_GUIDE.md](./SETUP_GUIDE.md) - 처음부터 설치하는 완전한 가이드

```bash
# 자동 설치 스크립트
./quick_start.sh
```

### 이미 설정된 환경에서 실행
```bash
# Elasticsearch 실행
cd docker && docker-compose up -d

# 로컬 웹 페이지 열기
./run_local.sh
```

---

## 📚 목차

1. [전체 시스템 개요](#1-전체-시스템-개요)
2. [데이터 출처 및 수집](#2-데이터-출처-및-수집)
3. [데이터 파이프라인 상세](#3-데이터-파이프라인-상세)
4. [실행 방법](#4-실행-방법)
5. [데이터 영향도 분석](#5-데이터-영향도-분석)
6. [트러블슈팅](#6-트러블슈팅)
7. [고급 운영](#7-고급-운영)

---

## 1. 전체 시스템 개요

### 1.1 시스템 구성도

```
┌─────────────────────────────────────────────────────────────┐
│                    데이터 파이프라인                          │
└─────────────────────────────────────────────────────────────┘

Step 1: 데이터 수집
┌──────────────────────────────────┐
│  OpenStreetMap (Overpass API)   │  ← 무료 공개 지도 데이터
│  - 서울 지역 호텔/게스트하우스    │
│  - tourism=hotel/hostel/motel   │
│  - 위치(위경도), 이름, 주소      │
└──────────────────────────────────┘
         ↓
    data/raw/seoul_hotels.json (356KB, ~200개 호텔)

Step 2: 데이터 전처리 및 강화
┌──────────────────────────────────┐
│  HotelDataEnricher              │
│  (hotel_data_enricher.py)       │
│  ────────────────────────────── │
│  ① OSM 기본 정보 추출            │
│  ② 주변 POI 수집 (Overpass API) │
│     - 관광지, 지하철역, 음식점    │
│     - 500m 반경 내 검색          │
│  ③ 랭킹 점수 계산 (0-100점)      │
│     - POI 개수: 40점             │
│     - 지하철 접근성: 30점         │
│     - 지역 가중치: 20점           │
│     - 카테고리: 10점             │
│  ④ 검색 키워드 자동 생성          │
│  ⑤ 가상 리뷰/평점 생성           │
└──────────────────────────────────┘
         ↓
    data/processed/enriched_hotels.json (1.5MB)

Step 3: Elasticsearch 인덱싱
┌──────────────────────────────────┐
│  ElasticsearchIndexer           │
│  (elasticsearch_indexer.py)     │
│  ────────────────────────────── │
│  ① hotels 인덱스 생성            │
│  ② 매핑 정의 (geo_point, nested)│
│  ③ 벌크 인덱싱 (100개 chunk)    │
└──────────────────────────────────┘
         ↓
    Elasticsearch (localhost:9200)
    ├─ hotels 인덱스
    ├─ destinations 인덱스 (강남, 명동 등)
    └─ autocomplete 인덱스

Step 4: 자동 재인덱싱 (선택)
┌──────────────────────────────────┐
│  AutoReindexWatcher             │
│  (auto_reindex_watcher.py)      │
│  ────────────────────────────── │
│  enriched_hotels.json 변경 감지  │
│  → 자동으로 재인덱싱 실행         │
└──────────────────────────────────┘
```

### 1.2 핵심 스크립트 역할

| 스크립트 | 경로 | 역할 | 입력 | 출력 |
|---------|------|------|------|------|
| **download_osm_data.sh** | `data/scripts/` | OSM 데이터 다운로드 | Overpass API | `seoul_hotels.json` |
| **hotel_data_enricher.py** | `backend/indexing/` | 데이터 전처리 & 강화 | `seoul_hotels.json` | `enriched_hotels.json` |
| **create_indices.sh** | `backend/indexing/` | Elasticsearch 인덱스 생성 | - | ES 인덱스 3개 |
| **elasticsearch_indexer.py** | `backend/indexing/` | ES 인덱싱 | `enriched_hotels.json` | ES documents |
| **index_hotels.py** (Legacy) | `backend/indexing/` | 구버전 인덱서 | `seoul_hotels.json` | ES documents |
| **auto_reindex_watcher.py** | `backend/indexing/` | 파일 변경 감지 & 재인덱싱 | `enriched_hotels.json` | 자동 재인덱싱 |

---

## 2. 데이터 출처 및 수집

### 2.1 OpenStreetMap (OSM) 데이터

#### 데이터 소스
- **출처**: [OpenStreetMap](https://www.openstreetmap.org/)
- **API**: [Overpass API](https://overpass-api.de/)
- **라이선스**: ODbL (Open Database License) - 무료 사용 가능, 출처 명시 필요
- **업데이트**: 실시간 (커뮤니티 기반 크라우드소싱)

#### 수집 방법

**스크립트**: `data/scripts/download_osm_data.sh`

```bash
#!/bin/bash

echo "📥 OpenStreetMap 데이터 다운로드 중..."

curl -o data/raw/seoul_hotels.json "https://overpass-api.de/api/interpreter" --data-urlencode 'data=
[out:json][timeout:60];
area["ISO3166-2"="KR-11"]->.seoul;
(
  node["tourism"="hotel"](area.seoul);
  node["tourism"="hostel"](area.seoul);
  node["tourism"="motel"](area.seoul);
  node["tourism"="guest_house"](area.seoul);
  way["tourism"="hotel"](area.seoul);
);
out center;
'

echo "✅ 서울 호텔 데이터 다운로드 완료"
```

**수집되는 데이터**:
- **범위**: 서울특별시 전체 (ISO3166-2: KR-11)
- **대상**: `tourism` 태그가 있는 숙박시설
  - `hotel`: 호텔
  - `hostel`: 호스텔
  - `motel`: 모텔
  - `guest_house`: 게스트하우스
- **타입**:
  - `node`: 점 데이터 (건물 위치)
  - `way`: 선/면 데이터 (건물 외곽선) → 중심점으로 변환

**원본 데이터 구조** (`data/raw/seoul_hotels.json`):

```json
{
  "version": 0.6,
  "generator": "Overpass API",
  "elements": [
    {
      "type": "node",
      "id": 368601210,
      "lat": 37.5813359,
      "lon": 126.9865747,
      "tags": {
        "addr:city": "서울특별시",
        "addr:district": "종로구",
        "addr:housenumber": "89",
        "addr:street": "계동길",
        "name": "북촌게스트하우스",
        "name:en": "Bukchon Guest House",
        "tourism": "guest_house"
      }
    }
  ]
}
```

**실행 방법**:
```bash
cd /Users/jeongjinseo/Desktop/개발/hotel_study
bash data/scripts/download_osm_data.sh

# 결과 확인
ls -lh data/raw/seoul_hotels.json
# -rw-r--r--  1 user  staff  356K  seoul_hotels.json
```

**주의사항**:
- Overpass API는 무료이지만 Rate Limit 존재 (초당 2-3 요청)
- 대용량 쿼리 시 타임아웃 가능 (기본 60초)
- 서울 전체 호텔은 약 200개 내외 (2025년 기준)

---

## 3. 데이터 파이프라인 상세

### 3.1 데이터 강화 프로세스

**스크립트**: `backend/indexing/hotel_data_enricher.py`

이 스크립트는 OSM의 기본 데이터를 **검색 최적화된 풍부한 데이터**로 변환합니다.

#### 3.1.1 주변 POI 수집

```python
def fetch_nearby_pois(self, lat: float, lon: float, radius: int = 500):
    """
    Overpass API로 호텔 주변 500m 이내 POI 수집

    수집 대상:
    - 관광지: tourism=attraction|museum|viewpoint
    - 지하철역: railway=station
    - 음식점: amenity=restaurant
    - 편의점: shop=convenience
    """
```

**예시**: 북촌게스트하우스 (종로구 계동길 89)
- **29m**: 왕짱구식당 (음식점)
- **118m**: CU 편의점
- **120m**: 가회민화박물관 (관광지)
- **132m**: 북촌한옥마을 (관광지)

→ 이 정보가 `nearbyPOI` 배열로 저장됨

#### 3.1.2 랭킹 점수 계산 (0-100점)

```python
def calculate_rank_score(self, hotel: Dict, nearby_pois: List[Dict]) -> int:
    """
    호텔 랭킹 점수 산출 공식

    기본점수: 50점

    1. 주변 POI 개수 (최대 40점)
       - POI 1개당 +4점
       - 최대 10개 POI

    2. 지하철역 접근성 (최대 30점)
       - 300m 이내: +30점
       - 500m 이내: +20점
       - 1km 이내: +10점

    3. 지역 가중치 (최대 20점)
       - 강남구: 1.5배 → +20점
       - 중구/종로구: 1.3배 → +12점
       - 마포구/용산구: 1.2배 → +8점
       - 송파구: 1.1배 → +4점

    4. 카테고리 (최대 10점)
       - 호텔: +10점
       - 게스트하우스/호스텔: +5점
       - 모텔: 0점
    """
```

**계산 예시**:
```
북촌게스트하우스 랭킹 계산:
- 기본: 50점
- POI 10개 × 4점 = +40점
- 지하철역 없음 = 0점
- 종로구 1.3배 = +12점
- 게스트하우스 = +5점
─────────────────────
총점: 107점 → 100점 (상한)
```

#### 3.1.3 키워드 자동 생성

```python
def generate_keywords(self, hotel: Dict, nearby_pois: List[Dict]):
    """
    검색 키워드 자동 추출

    생성 규칙:
    1. 호텔명 분리 ("북촌게스트하우스" → ["북촌게스트하우스"])
    2. 지역명 ("종로구" → "종로")
    3. 거리명 ("계동길" → "계동")
    4. 카테고리 ("게스트하우스")
    5. 주변 주요 POI (300m 이내, 상위 3개)
       → "가회민화박물관", "북촌한옥마을", "CU"

    결과: ["북촌게스트하우스", "종로", "계동", "게스트하우스",
          "가회민화박물관", "북촌한옥마을", "CU"]
    """
```

#### 3.1.4 가상 리뷰/평점 생성

```python
# 랭킹 점수 기반 가상 데이터 생성
enriched['reviewCount'] = int(rankScore * 1.5)    # 100점 → 150개 리뷰
enriched['rating'] = 3.5 + (rankScore / 100) * 1.5  # 100점 → 5.0점
enriched['popularity'] = rankScore * 10             # 100점 → 1000
```

**왜 가상 데이터를 생성하나요?**
- OSM은 리뷰/평점 데이터를 제공하지 않음
- 실제 리뷰 API (Google, Naver)는 유료이거나 사용량 제한이 엄격
- 랭킹 기반 추정값으로 검색 정렬 기능 구현 가능

#### 3.1.5 강화된 데이터 구조

**출력 파일**: `data/processed/enriched_hotels.json`

```json
{
  "id": "hotel_368601210",
  "name": "북촌게스트하우스",
  "name_en": "Bukchon Guest House",
  "category": "게스트하우스",
  "type": "숙박",

  "address": {
    "full": "서울특별시 종로구 계동길 89",
    "city": "서울특별시",
    "district": "종로구",
    "street": "계동길 89"
  },

  "location": {
    "type": "Point",
    "coordinates": [126.9865747, 37.5813359]  // [경도, 위도]
  },

  "keywords": ["북촌게스트하우스", "종로", "계동", "게스트하우스", "가회민화박물관"],
  "synonyms": [],
  "relatedKeywords": [],

  "rankScore": 100,           // 랭킹 점수
  "popularity": 1000,         // 인기도
  "reviewCount": 150,         // 가상 리뷰 수
  "rating": 5.0,              // 가상 평점

  "nearbyPOI": [
    {"name": "왕짱구식당", "type": "음식점", "distance": 29},
    {"name": "CU", "type": "편의점", "distance": 118},
    {"name": "가회민화박물관", "type": "관광지", "distance": 120}
  ],

  "transitInfo": {
    "subway": [],  // 1km 이내 지하철역 없음
    "bus": []
  },

  "source": "OSM",
  "lastUpdated": "2025-11-26",
  "dataQuality": "medium"
}
```

#### 3.1.6 증분 저장 모드

```python
def enrich_all_hotels(self, input_file, output_file, limit=None):
    """
    모든 호텔 처리 (증분 저장)

    특징:
    - 처리 중간에 중단되어도 이미 처리된 호텔은 저장됨
    - 재실행 시 이미 처리된 호텔은 건너뜀 (재개 가능)
    - 호텔 1개 처리마다 즉시 파일에 저장
    - Rate Limit 준수 (1.5초 대기)
    """
```

**실행 로그 예시**:
```
[1/200] 처리 중...
  📍 주변 POI 수집: 북촌게스트하우스
  ✅ 북촌게스트하우스 - 랭킹: 100, POI: 10개
  💾 저장 완료 (누적: 1개)

[2/200] 처리 중...
  📍 주변 POI 수집: 강남 호텔
  ✅ 강남 호텔 - 랭킹: 95, POI: 8개
  💾 저장 완료 (누적: 2개)

... (중간에 Ctrl+C로 중단)

# 재실행 시
📂 기존 파일 발견: 150개 호텔 이미 처리됨
📊 총 200개 호텔 중 50개 처리 예정

[151/200] 처리 중...  ← 151번부터 재개
```

#### 3.1.7 실행 방법

```bash
cd /Users/jeongjinseo/Desktop/개발/hotel_study

# 전체 호텔 처리 (약 5-10분 소요)
python3 backend/indexing/hotel_data_enricher.py

# 테스트 (처음 10개만)
python3 -c "
from backend.indexing.hotel_data_enricher import HotelDataEnricher
enricher = HotelDataEnricher()
enricher.enrich_all_hotels(
    'data/raw/seoul_hotels.json',
    'data/processed/enriched_hotels_test.json',
    limit=10
)
"

# 결과 확인
ls -lh data/processed/enriched_hotels.json
# -rw-r--r--  1 user  staff  1.5M  enriched_hotels.json
```

---

### 3.2 Elasticsearch 인덱싱

**스크립트**: `backend/indexing/elasticsearch_indexer.py`

#### 3.2.1 인덱스 매핑 정의

```python
mapping = {
    "settings": {
        "number_of_shards": 1,      # 단일 샤드 (소규模 데이터)
        "number_of_replicas": 0,    # 복제본 없음 (로컬 개발)
        "analysis": {
            "analyzer": {
                "korean": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase"]
                }
            }
        }
    },
    "mappings": {
        "properties": {
            "name": {
                "type": "text",
                "analyzer": "korean",
                "fields": {
                    "keyword": {"type": "keyword"}  # 정렬용
                }
            },
            "location": {
                "type": "geo_point"  # 🌍 지리 검색 가능
            },
            "nearbyPOI": {
                "type": "nested"     # 🔗 중첩 쿼리 가능
            },
            "rankScore": {"type": "integer"},
            "rating": {"type": "float"}
        }
    }
}
```

**주요 필드 타입 설명**:

| 필드 | 타입 | 설명 | 사용 예시 |
|------|------|------|----------|
| `name` | `text` (analyzed) | 한글 형태소 분석 | "강남 호텔" 검색 가능 |
| `name.keyword` | `keyword` (exact) | 정확한 매칭 | 정렬, 집계에 사용 |
| `location` | `geo_point` | 위경도 좌표 | 반경 검색, 거리 정렬 |
| `nearbyPOI` | `nested` | 중첩 객체 배열 | "지하철역 300m 이내" 검색 |
| `rankScore` | `integer` | 정수 | 정렬, 범위 검색 |
| `rating` | `float` | 실수 | 평점 4.5 이상 검색 |

#### 3.2.2 벌크 인덱싱

```python
def bulk_index_hotels(self, hotels: List[Dict]):
    """
    호텔 데이터 벌크 인덱싱

    성능 최적화:
    - chunk_size=100: 100개씩 묶어서 전송
    - request_timeout=30: 타임아웃 30초
    - helpers.bulk: Elasticsearch 공식 벌크 API
    """

    actions = [
        {
            "_index": "hotels",
            "_id": hotel['id'],        # hotel_368601210
            "_source": hotel           # 전체 데이터
        }
        for hotel in hotels
    ]

    success, failed = helpers.bulk(
        self.es,
        actions,
        chunk_size=100,
        request_timeout=30
    )
```

**벌크 인덱싱의 장점**:
- 개별 인덱싱 대비 **10-20배 빠름**
- 네트워크 왕복 횟수 최소화
- Elasticsearch 내부 최적화 활용

#### 3.2.3 인덱스 검증 및 통계

```python
def verify_index(self):
    # 문서 개수
    count = self.es.count(index="hotels")['count']

    # 통계 쿼리
    stats = self.es.search(
        index="hotels",
        body={
            "size": 0,
            "aggs": {
                "avg_rank": {"avg": {"field": "rankScore"}},
                "avg_rating": {"avg": {"field": "rating"}},
                "categories": {
                    "terms": {"field": "category", "size": 10}
                }
            }
        }
    )
```

**출력 예시**:
```
🔍 인덱스 'hotels' 상태 확인...
  - 총 문서 수: 198개
  - 샘플 호텔: 북촌게스트하우스
    랭킹: 100, POI: 10개

📊 통계:
  - 평균 랭킹: 87.3
  - 평균 평점: 4.8
  - 카테고리 분포:
    호텔: 120개
    게스트하우스: 45개
    모텔: 33개
```

#### 3.2.4 검색 테스트

```python
def test_search(self):
    # 1. 키워드 검색
    result = self.es.search(
        index="hotels",
        body={
            "query": {
                "multi_match": {
                    "query": "강남",
                    "fields": ["name^3", "keywords^2", "address.full"]
                }
            },
            "sort": [{"rankScore": {"order": "desc"}}]
        }
    )

    # 2. 지하철역 근처 호텔 (Nested Query)
    result = self.es.search(
        body={
            "query": {
                "nested": {
                    "path": "nearbyPOI",
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"nearbyPOI.type": "지하철"}},
                                {"range": {"nearbyPOI.distance": {"lt": 300}}}
                            ]
                        }
                    }
                }
            }
        }
    )
```

#### 3.2.5 실행 방법

```bash
cd /Users/jeongjinseo/Desktop/개발/hotel_study

# Elasticsearch 실행 확인
curl http://localhost:9200
# {"name":"...", "cluster_name":"...", "version":{...}}

# 인덱싱 실행
python3 backend/indexing/elasticsearch_indexer.py

# 결과:
# 🔧 인덱스 'hotels' 생성 중...
# ✅ 인덱스 생성 완료!
# 📦 198개 호텔 벌크 인덱싱 시작...
# ✅ 인덱싱 완료!
#   - 성공: 198개
#   - 실패: 0개
```

---

### 3.3 자동 재인덱싱 (선택)

**스크립트**: `backend/indexing/auto_reindex_watcher.py`

#### 3.3.1 파일 변경 감지

```python
class AutoReindexWatcher:
    def watch(self):
        """
        enriched_hotels.json 파일 감시

        동작:
        1. 5초마다 파일 수정 시간 체크
        2. 파일이 변경되면 자동으로 elasticsearch_indexer.py 실행
        3. 재인덱싱 완료 후 다시 감시
        """

        while True:
            current_modified = os.path.getmtime(self.watch_file)

            if current_modified != self.last_modified:
                print("📝 파일 변경 감지!")
                self.reindex()  # elasticsearch_indexer.py 실행

            time.sleep(5)
```

#### 3.3.2 사용 시나리오

**시나리오 1**: 데이터 강화 작업 중 실시간 반영

```bash
# Terminal 1: Watcher 실행
python3 backend/indexing/auto_reindex_watcher.py
# 👀 파일 감시 시작: enriched_hotels.json
#    체크 주기: 5초

# Terminal 2: 데이터 강화 (증분 처리)
python3 backend/indexing/hotel_data_enricher.py

# → Watcher가 파일 변경을 감지하고 자동 재인덱싱
# 📝 파일 변경 감지!
# 🔄 재인덱싱 시작: 2025-11-28 15:30:45
# ✅ 재인덱싱 성공!
```

**시나리오 2**: 수동 데이터 수정 후 자동 반영

```bash
# 1. Watcher 실행
python3 backend/indexing/auto_reindex_watcher.py

# 2. 데이터 파일 수동 편집
vi data/processed/enriched_hotels.json
# rankScore를 100 → 95로 변경
# :wq (저장)

# → 5초 이내에 자동 재인덱싱 실행
```

---

## 4. 실행 방법

### 4.1 환경 준비

#### 4.1.1 시스템 요구사항

- **OS**: macOS, Linux, Windows (WSL)
- **Python**: 3.8 이상
- **Docker**: 20.10 이상
- **메모리**: 최소 2GB (Elasticsearch용)
- **디스크**: 최소 5GB

#### 4.1.2 Python 패키지 설치

**필수 패키지**:
```bash
pip3 install elasticsearch==8.11.0
pip3 install geopy==2.4.0
pip3 install requests==2.31.0
```

**requirements.txt** 생성 (선택):
```bash
cat > requirements.txt <<EOF
elasticsearch==8.11.0
geopy==2.4.0
requests==2.31.0
EOF

pip3 install -r requirements.txt
```

#### 4.1.3 Elasticsearch + Kibana 실행

```bash
cd /Users/jeongjinseo/Desktop/개발/hotel_study/docker

# Docker Compose 실행
docker-compose up -d

# 실행 확인
docker ps
# CONTAINER ID   IMAGE                            STATUS
# abc123...      elasticsearch:8.11.0             Up 30 seconds
# def456...      kibana:8.11.0                    Up 30 seconds

# Elasticsearch 헬스 체크 (Ready 될 때까지 대기)
watch -n 2 'curl -s http://localhost:9200/_cluster/health | jq'

# 또는
while true; do
  STATUS=$(curl -s http://localhost:9200/_cluster/health | jq -r '.status')
  echo "Status: $STATUS"
  [ "$STATUS" = "green" ] || [ "$STATUS" = "yellow" ] && break
  sleep 5
done
```

**Kibana 접속** (선택):
- URL: http://localhost:5601
- Dev Tools에서 쿼리 테스트 가능

---

### 4.2 전체 파이프라인 실행

#### 옵션 A: 전체 자동 실행 (추천)

```bash
#!/bin/bash
# 파일명: run_full_pipeline.sh

cd /Users/jeongjinseo/Desktop/개발/hotel_study

echo "🚀 호텔 검색 시스템 전체 파이프라인 실행"
echo "========================================"

# Step 1: Elasticsearch 실행 확인
echo ""
echo "Step 1: Elasticsearch 상태 확인..."
if ! curl -s http://localhost:9200 > /dev/null; then
    echo "❌ Elasticsearch가 실행 중이지 않습니다"
    echo "   docker-compose up -d 를 먼저 실행하세요"
    exit 1
fi
echo "✅ Elasticsearch 실행 중"

# Step 2: OSM 데이터 다운로드
echo ""
echo "Step 2: OSM 데이터 다운로드..."
bash data/scripts/download_osm_data.sh
echo "✅ 다운로드 완료: $(wc -l < data/raw/seoul_hotels.json) lines"

# Step 3: 데이터 강화
echo ""
echo "Step 3: 호텔 데이터 강화 (5-10분 소요)..."
python3 backend/indexing/hotel_data_enricher.py

# Step 4: Elasticsearch 인덱싱
echo ""
echo "Step 4: Elasticsearch 인덱싱..."
python3 backend/indexing/elasticsearch_indexer.py

echo ""
echo "🎉 전체 파이프라인 완료!"
echo ""
echo "📊 결과 확인:"
curl -s http://localhost:9200/hotels/_count | jq
echo ""
echo "🔍 검색 테스트:"
echo "   curl -X GET 'http://localhost:9200/hotels/_search?q=강남&pretty'"
```

**실행**:
```bash
chmod +x run_full_pipeline.sh
./run_full_pipeline.sh
```

#### 옵션 B: 단계별 수동 실행

```bash
cd /Users/jeongjinseo/Desktop/개발/hotel_study

# Step 1: Docker 실행
cd docker && docker-compose up -d && cd ..

# Step 2: OSM 데이터 다운로드
bash data/scripts/download_osm_data.sh

# Step 3: 데이터 강화
python3 backend/indexing/hotel_data_enricher.py

# Step 4: 인덱싱
python3 backend/indexing/elasticsearch_indexer.py

# (선택) Step 5: 자동 재인덱싱 watcher
python3 backend/indexing/auto_reindex_watcher.py
```

---

### 4.3 검색 테스트

#### cURL 명령어

```bash
# 1. 전체 호텔 개수
curl http://localhost:9200/hotels/_count

# 2. 강남 검색
curl -X GET "http://localhost:9200/hotels/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "multi_match": {
        "query": "강남",
        "fields": ["name^3", "keywords^2", "address.full"]
      }
    },
    "size": 5,
    "sort": [{"rankScore": {"order": "desc"}}]
  }'

# 3. 평점 4.5 이상 호텔
curl -X GET "http://localhost:9200/hotels/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "range": {"rating": {"gte": 4.5}}
    },
    "size": 10,
    "sort": [{"rating": {"order": "desc"}}]
  }'

# 4. 지하철역 300m 이내 호텔
curl -X GET "http://localhost:9200/hotels/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "nested": {
        "path": "nearbyPOI",
        "query": {
          "bool": {
            "must": [
              {"term": {"nearbyPOI.type": "지하철"}},
              {"range": {"nearbyPOI.distance": {"lt": 300}}}
            ]
          }
        }
      }
    },
    "size": 5
  }'

# 5. 특정 위치 반경 1km 이내 호텔
curl -X GET "http://localhost:9200/hotels/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "geo_distance": {
        "distance": "1km",
        "location": {
          "lat": 37.5665,
          "lon": 126.9780
        }
      }
    },
    "size": 10,
    "sort": [
      {
        "_geo_distance": {
          "location": {"lat": 37.5665, "lon": 126.9780},
          "order": "asc",
          "unit": "km"
        }
      }
    ]
  }'
```

---

## 5. 데이터 영향도 분석

### 5.1 데이터 변경 시 영향 범위

#### 5.1.1 `rankScore` 변경 시

**변경 위치**: `backend/indexing/hotel_data_enricher.py` → `calculate_rank_score()`

```python
# 예: 지하철 접근성 점수 비중 변경
# 기존
if closest_subway['distance'] < 300:
    score += 30

# 변경
if closest_subway['distance'] < 300:
    score += 40  # 30 → 40으로 증가
```

**영향 범위**:

1. **직접 영향**:
   - `enriched_hotels.json`의 `rankScore` 값 변경
   - `popularity` 값 자동 변경 (= rankScore × 10)
   - `reviewCount` 값 자동 변경 (= rankScore × 1.5)
   - `rating` 값 자동 변경 (= 3.5 + rankScore/100 × 1.5)

2. **검색 결과 영향**:
   - 랭킹순 정렬 시 순서 변경
   - 지하철역 근처 호텔들의 순위 상승
   - 예: 강남역 근처 호텔이 상위권으로 이동

3. **재실행 필요**:
   ```bash
   # 1. 데이터 재강화
   python3 backend/indexing/hotel_data_enricher.py

   # 2. 재인덱싱
   python3 backend/indexing/elasticsearch_indexer.py
   ```

4. **영향 확인**:
   ```bash
   # 변경 전/후 rankScore 분포 비교
   curl -X GET "http://localhost:9200/hotels/_search?pretty" \
     -H 'Content-Type: application/json' \
     -d '{
       "size": 0,
       "aggs": {
         "rank_distribution": {
           "histogram": {
             "field": "rankScore",
             "interval": 10
           }
         }
       }
     }'
   ```

**예상 결과**:
```
Before:
  rankScore 90-100: 15개 호텔
  rankScore 80-90: 30개 호텔

After: (지하철 점수 증가 시)
  rankScore 90-100: 25개 호텔 (+10개)
  rankScore 80-90: 20개 호텔 (-10개)
```

#### 5.1.2 `rating` 공식 변경 시

**변경 위치**: `hotel_data_enricher.py:311`

```python
# 기존
enriched['rating'] = round(3.5 + (enriched['rankScore'] / 100) * 1.5, 1)
# rankScore 100 → rating 5.0
# rankScore 50 → rating 4.25

# 변경 예시 1: 최저 평점 상향
enriched['rating'] = round(4.0 + (enriched['rankScore'] / 100) * 1.0, 1)
# rankScore 100 → rating 5.0
# rankScore 50 → rating 4.5

# 변경 예시 2: 평점 편차 확대
enriched['rating'] = round(3.0 + (enriched['rankScore'] / 100) * 2.0, 1)
# rankScore 100 → rating 5.0
# rankScore 50 → rating 4.0
```

**영향 범위**:

1. **직접 영향**:
   - `enriched_hotels.json`의 `rating` 값 변경
   - Elasticsearch `hotels` 인덱스의 `rating` 필드 변경

2. **검색 결과 영향**:
   - "평점 4.5 이상" 필터 시 결과 개수 변화
   - 평점순 정렬 시 순서 변경

3. **UI/UX 영향**:
   - 별점 표시 변경
   - 필터링 결과 변화

#### 5.1.3 주변 POI 검색 반경 변경 시

**변경 위치**: `hotel_data_enricher.py:46`

```python
# 기존
def fetch_nearby_pois(self, lat: float, lon: float, radius: int = 500):

# 변경
def fetch_nearby_pois(self, lat: float, lon: float, radius: int = 1000):
```

**영향 범위**:

1. **데이터 볼륨 변화**:
   - 500m → 1000m: POI 개수 약 **4배 증가** (면적 ∝ r²)
   - `nearbyPOI` 배열 크기 증가
   - `enriched_hotels.json` 파일 크기 증가 (1.5MB → 4-5MB)

2. **rankScore 변화**:
   - POI 개수 증가 → 랭킹 점수 상승 (최대 +40점)
   - 전체 호텔의 평균 랭킹 상승

3. **처리 시간 증가**:
   - Overpass API 응답 시간 증가
   - 전체 강화 시간 5분 → 15-20분

4. **API Rate Limit 리스크**:
   - Overpass API 부하 증가
   - 타임아웃 발생 가능성 증가

**권장사항**:
- 반경 확대 시 `time.sleep(1.5)` → `time.sleep(2.0)` 조정
- 테스트는 `limit=10`으로 먼저 실행

#### 5.1.4 지역 가중치 변경 시

**변경 위치**: `hotel_data_enricher.py:37-44`

```python
# 기존
self.district_weights = {
    '강남구': 1.5,
    '중구': 1.3,
    '종로구': 1.3,
    '마포구': 1.2,
    '용산구': 1.2,
    '송파구': 1.1,
}

# 변경 예시: 명동(중구) 가중치 증가
self.district_weights = {
    '강남구': 1.5,
    '중구': 1.8,      # 1.3 → 1.8
    '종로구': 1.3,
    '마포구': 1.2,
    '용산구': 1.2,
    '송파구': 1.1,
}
```

**영향 범위**:

1. **직접 영향**:
   - 중구 호텔들의 `rankScore` 증가
   - 중구: 1.3배 → 1.8배 = +20점 → +32점 (최대 +12점 상승)

2. **검색 결과 변화**:
   - "명동" 검색 시 상위권 호텔 순위 재배치
   - 중구 호텔 vs 강남구 호텔 순위 변동

3. **예상 결과**:
   ```
   Before:
   1. 강남 호텔 A (강남구, rankScore: 95)
   2. 명동 호텔 B (중구, rankScore: 88)

   After:
   1. 명동 호텔 B (중구, rankScore: 100)  ← 순위 상승
   2. 강남 호텔 A (강남구, rankScore: 95)
   ```

---

### 5.2 Elasticsearch 매핑 변경 시

#### 5.2.1 새 필드 추가

**시나리오**: `priceRange` 필드 추가

**Step 1**: 데이터 강화 스크립트 수정

```python
# hotel_data_enricher.py

enriched = {
    # ... 기존 필드들 ...
    'priceRange': self._estimate_price_range(enriched),  # 새 필드
}

def _estimate_price_range(self, hotel: Dict) -> str:
    """가격대 추정 (rankScore 기반)"""
    rank = hotel['rankScore']
    if rank >= 90:
        return '고가'
    elif rank >= 70:
        return '중가'
    else:
        return '저가'
```

**Step 2**: Elasticsearch 매핑 수정

```python
# elasticsearch_indexer.py

mapping = {
    "mappings": {
        "properties": {
            # ... 기존 필드들 ...
            "priceRange": {"type": "keyword"}  # 새 필드 추가
        }
    }
}
```

**Step 3**: 재인덱싱

```bash
# 기존 인덱스 삭제 (자동)
python3 backend/indexing/elasticsearch_indexer.py

# 또는 수동 삭제
curl -X DELETE http://localhost:9200/hotels
```

**⚠️ 주의사항**:
- Elasticsearch는 기존 인덱스에 새 매핑을 추가할 수 없음
- 인덱스 재생성 필요 (데이터 손실 위험)
- 운영 환경에서는 Reindex API 사용 권장

---

### 5.3 데이터 의존성 체인

```
OSM 원본 데이터 (seoul_hotels.json)
    ↓
    ├─ 호텔명 변경 → keywords 변경 → 검색 결과 변경
    ├─ 주소 변경 → district 변경 → 지역 가중치 변경 → rankScore 변경
    └─ 위치 변경 → nearbyPOI 변경 → rankScore 변경
        ↓
강화된 데이터 (enriched_hotels.json)
    ↓
    ├─ rankScore 변경 → popularity, reviewCount, rating 변경
    ├─ nearbyPOI 변경 → transitInfo 변경
    └─ keywords 변경 → 검색 결과 변경
        ↓
Elasticsearch 인덱스
    ↓
    ├─ 검색 쿼리 결과
    ├─ 정렬 순서
    └─ 집계 통계
```

---

## 6. 트러블슈팅

### 6.1 Elasticsearch 연결 오류

**증상**:
```
ConnectionError: Connection refused
```

**원인**:
- Elasticsearch가 실행되지 않음
- 포트 9200이 사용 중

**해결책**:
```bash
# 1. Docker 컨테이너 확인
docker ps | grep elasticsearch

# 2. 컨테이너가 없으면 실행
cd docker && docker-compose up -d

# 3. 로그 확인
docker logs elasticsearch

# 4. 헬스 체크
curl http://localhost:9200/_cluster/health
```

---

### 6.2 Overpass API 타임아웃

**증상**:
```
⚠️ Overpass API 오류: 504
❌ POI 수집 오류: Timeout
```

**원인**:
- Overpass API 서버 부하
- 검색 반경이 너무 큼
- 네트워크 문제

**해결책**:

```python
# 1. 타임아웃 증가
query = f"""
[out:json][timeout:60];  # 25 → 60으로 증가
...
"""

# 2. Rate Limit 증가
time.sleep(2.0)  # 1.0 → 2.0으로 증가

# 3. 반경 축소
radius: int = 300  # 500 → 300으로 축소
```

---

### 6.3 메모리 부족 (Elasticsearch)

**증상**:
```
[elasticsearch] Killed
```

**원인**:
- Docker 메모리 제한 초과

**해결책**:

```yaml
# docker/docker-compose.yml

services:
  elasticsearch:
    environment:
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"  # 기본값
      # 메모리 증가
      - "ES_JAVA_OPTS=-Xms1g -Xmx1g"
```

```bash
# Docker 재시작
docker-compose down
docker-compose up -d
```

---

### 6.4 데이터 강화 중단 후 재개

**증상**:
```
[50/200] 처리 중...
^C  # Ctrl+C로 중단
```

**재개 방법**:
```bash
# 그대로 다시 실행 (자동으로 51번부터 재개)
python3 backend/indexing/hotel_data_enricher.py

# 출력:
# 📂 기존 파일 발견: 50개 호텔 이미 처리됨
# 📊 총 200개 호텔 중 150개 처리 예정
# [51/200] 처리 중...
```

---

### 6.5 검색 결과 없음

**증상**:
```bash
curl http://localhost:9200/hotels/_search?q=호텔
# "hits": {"total": {"value": 0}}
```

**원인 및 해결**:

```bash
# 1. 인덱스 존재 확인
curl http://localhost:9200/_cat/indices?v
# health status index   docs.count
# yellow open   hotels  0          ← 문서 0개

# 2. 인덱싱 재실행
python3 backend/indexing/elasticsearch_indexer.py

# 3. 문서 개수 재확인
curl http://localhost:9200/hotels/_count
# {"count": 198}

# 4. 매핑 확인
curl http://localhost:9200/hotels/_mapping?pretty
```

---

## 7. 고급 운영

### 7.1 증분 업데이트 워크플로우

**시나리오**: OSM 데이터 주간 업데이트

```bash
#!/bin/bash
# 파일명: weekly_update.sh

cd /Users/jeongjinseo/Desktop/개발/hotel_study

# 1. 최신 OSM 데이터 다운로드
bash data/scripts/download_osm_data.sh

# 2. 변경 사항 확인
OLD_COUNT=$(jq '.elements | length' data/raw/seoul_hotels.json.bak)
NEW_COUNT=$(jq '.elements | length' data/raw/seoul_hotels.json)

echo "기존: $OLD_COUNT개, 신규: $NEW_COUNT개"

if [ "$OLD_COUNT" == "$NEW_COUNT" ]; then
    echo "변경 사항 없음"
    exit 0
fi

# 3. 백업
cp data/processed/enriched_hotels.json \
   data/processed/enriched_hotels.json.bak.$(date +%Y%m%d)

# 4. 데이터 강화
python3 backend/indexing/hotel_data_enricher.py

# 5. 재인덱싱
python3 backend/indexing/elasticsearch_indexer.py

echo "✅ 업데이트 완료"
```

---

### 7.2 성능 모니터링

```python
# backend/indexing/performance_monitor.py

import time
import json
from elasticsearch import Elasticsearch

def monitor_search_performance():
    es = Elasticsearch(['http://localhost:9200'])

    queries = [
        {"match": {"name": "호텔"}},
        {"range": {"rankScore": {"gte": 90}}},
        {"geo_distance": {"distance": "1km", "location": {"lat": 37.5665, "lon": 126.9780}}}
    ]

    for query in queries:
        start = time.time()
        result = es.search(index="hotels", body={"query": query})
        elapsed = time.time() - start

        print(f"Query: {query}")
        print(f"  Time: {elapsed*1000:.2f}ms")
        print(f"  Hits: {result['hits']['total']['value']}")
        print()

if __name__ == '__main__':
    monitor_search_performance()
```

**실행**:
```bash
python3 backend/indexing/performance_monitor.py

# 출력:
# Query: {'match': {'name': '호텔'}}
#   Time: 12.34ms
#   Hits: 120
#
# Query: {'range': {'rankScore': {'gte': 90}}}
#   Time: 8.56ms
#   Hits: 25
```

---

### 7.3 데이터 품질 검증

```bash
# 스크립트: validate_data.sh

echo "📊 데이터 품질 검증"

# 1. 필수 필드 누락 체크
python3 << 'EOF'
import json

with open('data/processed/enriched_hotels.json') as f:
    hotels = json.load(f)

required_fields = ['id', 'name', 'location', 'rankScore']
missing = []

for hotel in hotels:
    for field in required_fields:
        if field not in hotel or not hotel[field]:
            missing.append(f"{hotel.get('id', 'unknown')}: {field}")

if missing:
    print("❌ 필수 필드 누락:")
    for m in missing[:10]:
        print(f"  - {m}")
else:
    print("✅ 필수 필드 검증 완료")
EOF

# 2. 좌표 범위 체크 (서울 지역)
python3 << 'EOF'
import json

with open('data/processed/enriched_hotels.json') as f:
    hotels = json.load(f)

# 서울 범위: 위도 37.4-37.7, 경도 126.7-127.2
out_of_range = []

for hotel in hotels:
    coords = hotel['location']['coordinates']
    lon, lat = coords[0], coords[1]

    if not (126.7 <= lon <= 127.2 and 37.4 <= lat <= 37.7):
        out_of_range.append(f"{hotel['name']}: ({lat}, {lon})")

if out_of_range:
    print("⚠️ 서울 범위 벗어남:")
    for o in out_of_range[:5]:
        print(f"  - {o}")
else:
    print("✅ 좌표 범위 검증 완료")
EOF
```

---

## 8. 부록

### 8.1 디렉토리 구조

```
hotel_study/
├── README.md                    ← 이 파일
├── docker/
│   └── docker-compose.yml       # Elasticsearch + Kibana
├── data/
│   ├── raw/
│   │   └── seoul_hotels.json    # OSM 원본 (356KB)
│   ├── processed/
│   │   └── enriched_hotels.json # 강화된 데이터 (1.5MB)
│   └── scripts/
│       └── download_osm_data.sh # OSM 다운로드 스크립트
├── backend/
│   └── indexing/
│       ├── hotel_data_enricher.py        # 데이터 강화
│       ├── elasticsearch_indexer.py      # ES 인덱싱
│       ├── auto_reindex_watcher.py       # 자동 재인덱싱
│       ├── index_hotels.py               # Legacy 인덱서
│       └── create_indices.sh             # 인덱스 생성 (Shell)
└── frontend/                    # (프론트엔드 코드)
```

### 8.2 Elasticsearch 인덱스 구조

```
Elasticsearch (localhost:9200)
├── hotels              # 호텔 상세 정보
│   ├── 문서 수: ~200개
│   ├── 샤드: 1
│   └── 크기: ~2MB
├── destinations        # 지역 정보 (강남, 명동 등)
│   ├── 문서 수: 5개
│   └── 크기: ~10KB
└── autocomplete        # 자동완성
    ├── 문서 수: ~205개
    └── 크기: ~50KB
```

### 8.3 API 키 설정 (선택)

**카카오 API 키** (선택사항):

```bash
# 1. 카카오 개발자 계정 생성
# https://developers.kakao.com/

# 2. 애플리케이션 생성 → REST API 키 발급

# 3. 환경 변수 설정
export KAKAO_API_KEY="your_kakao_api_key_here"

# 4. 데이터 강화 실행
python3 backend/indexing/hotel_data_enricher.py

# 카카오 API 사용 시:
# ✅ 카카오 API로 상세 정보 수집
#   - 전화번호
#   - 도로명 주소
#   - 카테고리 정보
```

**참고**: 카카오 API 없이도 기본 기능 동작 (OSM 데이터만 사용)

---

### 8.4 관련 문서

- [Elasticsearch 공식 문서](https://www.elastic.co/guide/en/elasticsearch/reference/8.11/index.html)
- [OpenStreetMap Wiki](https://wiki.openstreetmap.org/wiki/Main_Page)
- [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API)
- [geopy 문서](https://geopy.readthedocs.io/)

---

### 8.5 문의 및 기여

**문제 신고**: GitHub Issues
**작성자**: Hotel Study Team
**라이선스**: MIT

---

**마지막 업데이트**: 2025-11-28
**버전**: 1.0.0
