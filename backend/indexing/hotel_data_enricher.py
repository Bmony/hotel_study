#!/usr/bin/env python3
"""
호텔 데이터 강화 시스템 (무료 API 조합)

데이터 소스:
1. OSM (Overpass API): 기본 정보 + 주변 POI
2. 카카오 API: 한국 상세 정보 (주소, 전화번호 등)
3. 자동 계산: 랭킹, 인기도, 키워드
"""

import json
import time
import requests
from typing import Dict, List, Optional
from geopy.distance import geodesic
import os


class HotelDataEnricher:
    def __init__(self, kakao_api_key: Optional[str] = None):
        """
        Args:
            kakao_api_key: 카카오 REST API 키 (https://developers.kakao.com/)
        """
        self.kakao_api_key = kakao_api_key or os.getenv('KAKAO_API_KEY')

        # 카테고리 매핑
        self.category_mapping = {
            'hotel': '호텔',
            'motel': '모텔',
            'guest_house': '게스트하우스',
            'hostel': '호스텔',
            'apartment': '레지던스'
        }

        # 지역별 인기도 가중치
        self.district_weights = {
            '강남구': 1.5,
            '중구': 1.3,
            '종로구': 1.3,
            '마포구': 1.2,
            '용산구': 1.2,
            '송파구': 1.1,
        }

    def fetch_nearby_pois(self, lat: float, lon: float, radius: int = 500) -> List[Dict]:
        """
        Overpass API로 주변 POI 수집

        Args:
            lat, lon: 호텔 위치
            radius: 검색 반경 (미터)
        """
        try:
            overpass_url = "https://overpass-api.de/api/interpreter"

            # 관광지, 지하철역, 음식점 검색
            query = f"""
[out:json][timeout:25];
(
  node["tourism"~"attraction|museum|viewpoint"](around:{radius},{lat},{lon});
  node["railway"="station"](around:{radius},{lat},{lon});
  node["amenity"="restaurant"](around:{radius},{lat},{lon});
  node["shop"="convenience"](around:{radius},{lat},{lon});
);
out body;
"""

            response = requests.post(overpass_url, data={'data': query})
            time.sleep(1)  # Rate limit

            if response.status_code != 200:
                print(f"⚠️ Overpass API 오류: {response.status_code}")
                return []

            data = response.json()
            elements = data.get('elements', [])

            pois = []
            for elem in elements:
                poi_type = self._categorize_poi(elem.get('tags', {}))
                if poi_type:
                    poi_lat = elem['lat']
                    poi_lon = elem['lon']
                    distance = int(geodesic((lat, lon), (poi_lat, poi_lon)).meters)

                    pois.append({
                        'name': elem.get('tags', {}).get('name', 'Unknown'),
                        'type': poi_type,
                        'distance': distance
                    })

            # 거리순 정렬, 상위 10개
            pois.sort(key=lambda x: x['distance'])
            return pois[:10]

        except Exception as e:
            print(f"❌ POI 수집 오류: {e}")
            return []

    def _categorize_poi(self, tags: Dict) -> Optional[str]:
        """POI 카테고리 분류"""
        if 'tourism' in tags:
            return '관광지'
        elif tags.get('railway') == 'station':
            return '지하철'
        elif tags.get('amenity') == 'restaurant':
            return '음식점'
        elif tags.get('shop') == 'convenience':
            return '편의점'
        return None

    def fetch_kakao_place_info(self, name: str, lat: float, lon: float) -> Optional[Dict]:
        """
        카카오 지도 API로 상세 정보 수집

        무료: 일 30만건
        """
        if not self.kakao_api_key:
            print("⚠️ 카카오 API 키가 없습니다")
            return None

        try:
            url = "https://dapi.kakao.com/v2/local/search/keyword.json"
            headers = {"Authorization": f"KakaoAK {self.kakao_api_key}"}
            params = {
                'query': name,
                'x': lon,
                'y': lat,
                'radius': 100  # 100m 이내
            }

            response = requests.get(url, headers=headers, params=params)
            time.sleep(0.1)  # Rate limit

            if response.status_code != 200:
                return None

            data = response.json()
            documents = data.get('documents', [])

            if not documents:
                return None

            # 가장 가까운 결과
            place = documents[0]

            return {
                'phone': place.get('phone', ''),
                'address_full': place.get('address_name', ''),
                'road_address': place.get('road_address_name', ''),
                'place_url': place.get('place_url', ''),
                'category': place.get('category_name', '')
            }

        except Exception as e:
            print(f"❌ 카카오 API 오류: {e}")
            return None

    def calculate_rank_score(self, hotel: Dict, nearby_pois: List[Dict]) -> int:
        """
        랭킹 점수 계산 (0-100)

        기준:
        - 주변 POI 개수: 40점
        - 지하철역 접근성: 30점
        - 지역 가중치: 20점
        - 카테고리: 10점
        """
        score = 50  # 기본 점수

        # 1. POI 개수 (최대 40점)
        poi_count = len(nearby_pois)
        score += min(poi_count * 4, 40)

        # 2. 지하철역 접근성 (최대 30점)
        subway_pois = [p for p in nearby_pois if p['type'] == '지하철']
        if subway_pois:
            closest_subway = min(subway_pois, key=lambda x: x['distance'])
            if closest_subway['distance'] < 300:
                score += 30
            elif closest_subway['distance'] < 500:
                score += 20
            elif closest_subway['distance'] < 1000:
                score += 10

        # 3. 지역 가중치 (최대 20점)
        district = hotel.get('address', {}).get('district', '')
        weight = self.district_weights.get(district, 1.0)
        score += int((weight - 1.0) * 40)

        # 4. 카테고리 (호텔 > 게스트하우스 > 모텔)
        category = hotel.get('category', '')
        if '호텔' in category:
            score += 10
        elif '게스트하우스' in category or '호스텔' in category:
            score += 5

        return min(max(score, 0), 100)

    def generate_keywords(self, hotel: Dict, nearby_pois: List[Dict]) -> List[str]:
        """검색 키워드 자동 생성"""
        keywords = []

        # 1. 호텔명 분리
        name = hotel.get('name', '')
        keywords.extend(name.split())

        # 2. 지역명
        district = hotel.get('address', {}).get('district', '')
        if district:
            keywords.append(district.replace('구', ''))

        street = hotel.get('address', {}).get('street', '')
        if street:
            # "계동길" → "계동"
            street_name = street.split('길')[0].split('로')[0]
            if street_name:
                keywords.append(street_name)

        # 3. 카테고리
        category = hotel.get('category', '')
        keywords.append(category)

        # 4. 주변 주요 POI (거리 300m 이내)
        close_pois = [p for p in nearby_pois if p['distance'] < 300]
        for poi in close_pois[:3]:  # 상위 3개
            if poi['name'] != 'Unknown':
                keywords.append(poi['name'])

        # 중복 제거
        return list(set([k for k in keywords if k and len(k) > 1]))

    def enrich_hotel_data(self, osm_hotel: Dict) -> Dict:
        """
        호텔 데이터 강화 (메인 함수)

        Args:
            osm_hotel: OSM 원본 데이터

        Returns:
            강화된 호텔 데이터
        """
        try:
            tags = osm_hotel.get('tags', {})
            lat = osm_hotel['lat']
            lon = osm_hotel['lon']

            # 기본 정보 추출
            name = tags.get('name', tags.get('name:ko', 'Unknown'))
            name_en = tags.get('name:en', '')

            # 주소 파싱
            address = {
                'full': f"{tags.get('addr:city', '')} {tags.get('addr:district', '')} {tags.get('addr:street', '')} {tags.get('addr:housenumber', '')}".strip(),
                'city': tags.get('addr:city', '서울특별시'),
                'district': tags.get('addr:district', ''),
                'street': f"{tags.get('addr:street', '')} {tags.get('addr:housenumber', '')}".strip()
            }

            # 카테고리
            tourism_type = tags.get('tourism', 'hotel')
            category = self.category_mapping.get(tourism_type, '숙박시설')

            # 주변 POI 수집
            print(f"  📍 주변 POI 수집: {name}")
            nearby_pois = self.fetch_nearby_pois(lat, lon)

            # 키워드 생성
            enriched = {
                'id': f"hotel_{osm_hotel['id']}",
                'name': name,
                'name_en': name_en,
                'category': category,
                'type': '숙박',

                'address': address,
                'location': {
                    'type': 'Point',
                    'coordinates': [lon, lat]
                },

                'keywords': [],  # 아래서 생성
                'synonyms': [],
                'relatedKeywords': [],

                'rankScore': 0,  # 아래서 계산
                'popularity': 0,
                'reviewCount': 0,
                'rating': 0.0,

                'nearbyPOI': nearby_pois,
                'transitInfo': self._extract_transit_info(nearby_pois),

                'source': 'OSM',
                'lastUpdated': '2025-11-26',
                'dataQuality': 'medium'
            }

            # 키워드 생성
            enriched['keywords'] = self.generate_keywords(enriched, nearby_pois)

            # 랭킹 점수 계산
            enriched['rankScore'] = self.calculate_rank_score(enriched, nearby_pois)

            # 인기도 추정 (랭킹 * 10)
            enriched['popularity'] = enriched['rankScore'] * 10

            # 가상 리뷰/평점 (랭킹 기반)
            enriched['reviewCount'] = int(enriched['rankScore'] * 1.5)
            enriched['rating'] = round(3.5 + (enriched['rankScore'] / 100) * 1.5, 1)

            print(f"  ✅ {name} - 랭킹: {enriched['rankScore']}, POI: {len(nearby_pois)}개")

            return enriched

        except Exception as e:
            print(f"❌ 데이터 강화 오류: {e}")
            return None

    def _extract_transit_info(self, nearby_pois: List[Dict]) -> Dict:
        """교통 정보 추출"""
        transit = {
            'subway': [],
            'bus': []
        }

        subway_pois = [p for p in nearby_pois if p['type'] == '지하철']
        for subway in subway_pois[:3]:
            distance_text = f"도보 {subway['distance'] // 100}분" if subway['distance'] < 1000 else f"{subway['distance'] // 1000}km"
            transit['subway'].append(f"{subway['name']} {distance_text}")

        # 버스는 임의 생성 (실제로는 별도 API 필요)
        if subway_pois:
            transit['bus'] = ['버스 정류장 인근']

        return transit

    def enrich_all_hotels(self, input_file: str, output_file: str, limit: int = None):
        """
        모든 호텔 데이터 강화 (증분 저장)

        Args:
            input_file: OSM 원본 파일
            output_file: 강화된 데이터 저장 파일
            limit: 처리할 호텔 수 제한 (테스트용)
        """
        print("\n" + "="*60)
        print("🚀 호텔 데이터 강화 시작 (증분 저장 모드)")
        print("="*60)

        # OSM 데이터 로드
        with open(input_file, 'r', encoding='utf-8') as f:
            osm_data = json.load(f)

        hotels = osm_data.get('elements', [])

        # 이미 처리된 호텔 ID 확인 (재개 기능)
        processed_ids = set()
        if os.path.exists(output_file):
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    processed_ids = {h['id'] for h in existing_data}
                    print(f"\n📂 기존 파일 발견: {len(processed_ids)}개 호텔 이미 처리됨")
            except:
                print("\n📂 새 파일로 시작")

        if limit:
            hotels = hotels[:limit]

        total_hotels = len(hotels)
        remaining = total_hotels - len(processed_ids)
        print(f"\n📊 총 {total_hotels}개 호텔 중 {remaining}개 처리 예정")

        processed_count = 0

        for i, hotel in enumerate(hotels, 1):
            hotel_id = f"hotel_{hotel['id']}"

            # 이미 처리된 호텔은 건너뛰기
            if hotel_id in processed_ids:
                print(f"[{i}/{total_hotels}] ⏭️  건너뜀 (이미 처리됨)")
                continue

            print(f"\n[{i}/{total_hotels}] 처리 중...")

            try:
                enriched = self.enrich_hotel_data(hotel)
                if enriched:
                    # 즉시 파일에 추가 저장
                    self._append_to_file(output_file, enriched)
                    processed_ids.add(hotel_id)
                    processed_count += 1
                    print(f"  💾 저장 완료 (누적: {len(processed_ids)}개)")

            except Exception as e:
                print(f"  ❌ 처리 실패: {e}")
                continue

            # Rate limit 준수
            time.sleep(1.5)

        print(f"\n✅ 완료! 총 {len(processed_ids)}개 호텔 데이터 저장: {output_file}")
        print(f"  - 이번 세션 처리: {processed_count}개")

        # 통계 출력
        if len(processed_ids) > 0:
            with open(output_file, 'r', encoding='utf-8') as f:
                all_hotels = json.load(f)

            avg_rank = sum(h['rankScore'] for h in all_hotels) / len(all_hotels)
            avg_pois = sum(len(h['nearbyPOI']) for h in all_hotels) / len(all_hotels)

            print(f"\n📈 통계:")
            print(f"  - 평균 랭킹: {avg_rank:.1f}")
            print(f"  - 평균 주변 POI: {avg_pois:.1f}개")

    def _append_to_file(self, output_file: str, new_hotel: Dict):
        """
        파일에 호텔 데이터 추가 (JSON 배열 형식 유지)
        """
        hotels = []

        # 기존 데이터 로드
        if os.path.exists(output_file):
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    hotels = json.load(f)
            except:
                hotels = []

        # 새 데이터 추가
        hotels.append(new_hotel)

        # 다시 저장
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(hotels, f, ensure_ascii=False, indent=2)


# 테스트 코드
if __name__ == '__main__':
    import os

    # 프로젝트 루트 경로
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))

    enricher = HotelDataEnricher()

    # 전체 호텔 처리
    enricher.enrich_all_hotels(
        input_file=os.path.join(project_root, 'data/raw/seoul_hotels.json'),
        output_file=os.path.join(project_root, 'data/processed/enriched_hotels.json'),
        limit=None  # 전체 처리
    )
