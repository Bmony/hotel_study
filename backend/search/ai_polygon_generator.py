#!/usr/bin/env python3
"""
AI 기반 동적 폴리곤 생성 시스템
- GPT-4로 검색어 의미론적 확장
- Nominatim API로 실제 경계 가져오기
- Shapely로 폴리곤 병합 및 조정
"""

import json
import os
import time
from typing import List, Dict, Tuple, Optional
from shapely.geometry import shape, Polygon, MultiPolygon, Point
from shapely.ops import unary_union
from geopy.geocoders import Nominatim
import requests

class AIPolygonGenerator:
    def __init__(self, openai_api_key: Optional[str] = None):
        """
        Args:
            openai_api_key: OpenAI API 키 (없으면 환경변수에서)
        """
        self.api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        self.geocoder = Nominatim(user_agent="hotel_search_ai")
        
    def expand_search_query(self, query: str, use_mock: bool = True) -> List[str]:
        """
        검색어를 의미론적으로 확장
        
        예: "잠실" → ["잠실동", "잠실역", "잠실새내", "롯데월드", "석촌호수"]
        
        Args:
            query: 사용자 검색어
            use_mock: True면 GPT 대신 목업 데이터 사용 (비용 절약)
        """
        # 목업 데이터 (GPT-4 비용 절약용)
        if use_mock:
            mock_expansions = {
                "잠실": ["잠실동", "잠실역", "잠실새내역", "롯데월드", "석촌호수"],
                "강남": ["강남역", "신사동", "압구정동", "청담동", "역삼동", "논현동"],
                "명동": ["명동역", "명동성당", "남대문", "을지로입구역"],
                "홍대": ["홍대입구역", "상수역", "합정역", "연남동"],
                "이태원": ["이태원역", "한남동", "녹사평역", "해방촌"]
            }
            
            for key in mock_expansions:
                if key in query:
                    result = [key] + mock_expansions[key]
                    print(f"🤖 Mock 확장: {query} → {result}")
                    return result
            
            # 매칭 안되면 원본만 반환
            return [query]
        
        # 실제 GPT-4 호출 (비용 발생)
        if not self.api_key:
            print("⚠️ OpenAI API 키가 없습니다. Mock 데이터 사용")
            return self.expand_search_query(query, use_mock=True)
        
        try:
            import openai
            openai.api_key = self.api_key
            
            prompt = f"""
서울의 "{query}" 지역을 검색하는 사용자가 있습니다.
이 사용자가 호텔을 찾을 때 관심 있을 만한 주변 지역, 랜드마크, 역을 5-7개 나열하세요.

출력 형식: JSON 배열만 (설명 없이)
예시: ["잠실동", "잠실역", "롯데월드"]

지역:
"""
            
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200
            )
            
            result_text = response.choices[0].message.content.strip()
            result = json.loads(result_text)
            
            print(f"🤖 GPT-4 확장: {query} → {result}")
            return [query] + result
            
        except Exception as e:
            print(f"❌ GPT-4 오류: {e}, Mock 데이터 사용")
            return self.expand_search_query(query, use_mock=True)
    
    def fetch_polygon_from_nominatim(self, place_name: str, city: str = "서울") -> Optional[Dict]:
        """
        Nominatim API로 실제 경계 폴리곤 가져오기
        """
        try:
            # 검색 쿼리
            search_query = f"{place_name}, {city}, South Korea"
            
            # Nominatim API 호출
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': search_query,
                'format': 'json',
                'polygon_geojson': 1,
                'limit': 1
            }
            headers = {'User-Agent': 'hotel_search_ai/1.0'}
            
            response = requests.get(url, params=params, headers=headers)
            time.sleep(1)  # API rate limit 준수
            
            if response.status_code != 200:
                print(f"⚠️ Nominatim API 오류: {response.status_code}")
                return None
            
            results = response.json()
            
            if not results:
                print(f"⚠️ '{place_name}' 검색 결과 없음")
                return None
            
            result = results[0]
            
            if 'geojson' not in result:
                print(f"⚠️ '{place_name}' 폴리곤 데이터 없음")
                return None
            
            print(f"✅ '{place_name}' 폴리곤 획득")
            return result['geojson']
            
        except Exception as e:
            print(f"❌ Nominatim 오류 ({place_name}): {e}")
            return None
    
    def merge_polygons(self, geojson_list: List[Dict]) -> Optional[Dict]:
        """
        여러 폴리곤을 하나로 병합
        """
        try:
            shapes = []
            
            for geojson in geojson_list:
                geom = shape(geojson)
                
                # Point나 LineString을 버퍼로 변환
                if geom.geom_type == 'Point':
                    geom = geom.buffer(0.01)  # 약 1km
                elif geom.geom_type == 'LineString':
                    geom = geom.buffer(0.005)  # 약 500m
                
                shapes.append(geom)
            
            if not shapes:
                return None
            
            # 병합
            merged = unary_union(shapes)
            
            # GeoJSON으로 변환
            if merged.geom_type == 'Polygon':
                coords = [list(merged.exterior.coords)]
            elif merged.geom_type == 'MultiPolygon':
                # 가장 큰 폴리곤만 사용
                largest = max(merged.geoms, key=lambda p: p.area)
                coords = [list(largest.exterior.coords)]
            else:
                return None
            
            return {
                'type': 'Polygon',
                'coordinates': coords
            }
            
        except Exception as e:
            print(f"❌ 폴리곤 병합 오류: {e}")
            return None
    
    def generate_dynamic_polygon(self, search_query: str) -> Dict:
        """
        검색어로부터 동적 폴리곤 생성 (전체 파이프라인)
        
        Returns:
            {
                'query': 원본 검색어,
                'expanded': 확장된 지역 리스트,
                'polygon': 병합된 폴리곤 GeoJSON,
                'metadata': 메타데이터
            }
        """
        print(f"\n🔍 검색어: '{search_query}'")
        
        # 1. 검색어 확장
        expanded_places = self.expand_search_query(search_query)
        
        # 2. 각 지역의 폴리곤 가져오기
        polygons = []
        for place in expanded_places:
            geojson = self.fetch_polygon_from_nominatim(place)
            if geojson:
                polygons.append(geojson)
        
        if not polygons:
            print("❌ 유효한 폴리곤을 찾을 수 없습니다")
            return None
        
        # 3. 폴리곤 병합
        merged_polygon = self.merge_polygons(polygons)
        
        if not merged_polygon:
            print("❌ 폴리곤 병합 실패")
            return None
        
        print(f"✅ 동적 폴리곤 생성 완료: {len(expanded_places)}개 지역 병합")
        
        return {
            'query': search_query,
            'expanded_places': expanded_places,  # UI가 이 키를 사용
            'polygon': merged_polygon,
            'metadata': {
                'source_count': len(polygons),
                'total_places': len(expanded_places)
            }
        }


# 테스트 코드
if __name__ == '__main__':
    generator = AIPolygonGenerator()
    
    # 테스트 쿼리
    test_queries = ["잠실", "강남", "명동"]
    
    for query in test_queries:
        result = generator.generate_dynamic_polygon(query)
        
        if result:
            print(f"\n📊 결과:")
            print(f"  - 원본: {result['query']}")
            print(f"  - 확장: {result['expanded']}")
            print(f"  - 폴리곤: {len(result['polygon']['coordinates'][0])}개 좌표")
            
            # 파일 저장
            filename = f"data/processed/{query}_dynamic_polygon.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"  - 저장: {filename}")
        
        print("\n" + "="*60)
