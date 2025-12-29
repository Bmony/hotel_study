#!/usr/bin/env python3
"""
자연어 기반 폴리곤 조정 시스템
- "근처 관광지 포함" → 관광지 중심으로 확장
- "500m 축소" → 폴리곤 크기 줄이기
- "지하철역 중심으로" → 역 위치 가중치
"""

import json
import re
from typing import Dict, List, Tuple
from shapely.geometry import shape, Point, Polygon, MultiPoint
from shapely.ops import unary_union
import requests
import time

class NaturalLanguageAdjuster:
    def __init__(self):
        self.adjustment_patterns = {
            # 호텔 개수 기반 조정 + 기준점
            r'(지하철|역|station)\s*(기준|중심)\s*호텔\s*(\d+)\s*(개|까지|제한)': 'target_count_transit',
            r'(관광지|명소)\s*(기준|중심)\s*호텔\s*(\d+)\s*(개|까지|제한)': 'target_count_tourism',
            r'호텔\s*(\d+)\s*(개|까지|제한|으로)': 'target_count',
            r'(\d+)\s*개\s*(호텔|까지|제한)': 'target_count',

            # 확장/축소
            r'(\d+)m?\s*(확장|넓히기|expand)': 'expand',
            r'(\d+)m?\s*(축소|줄이기|shrink)': 'shrink',

            # 가중치 (확장)
            r'(관광지|tourist|명소)\s*(기준|중심|포함)': 'tourism_weight',
            r'(지하철|역|station)\s*(기준|중심|포함)': 'transit_weight',
            r'(음식점|맛집|restaurant)\s*(기준|중심|포함)': 'restaurant_weight',

            # POI 밀집 구역만 (축소)
            r'(관광지|tourist|명소)\s*(구역만|밀집|집중)': 'tourism_only',
            r'(지하철|역|station)\s*(구역만|밀집|역세권만)': 'transit_only',
            r'(음식점|맛집|restaurant)\s*(구역만|밀집|집중)': 'restaurant_only',

            # 방향
            r'(북|north)\s*방향': 'north',
            r'(남|south)\s*방향': 'south',
            r'(동|east)\s*방향': 'east',
            r'(서|west)\s*방향': 'west',
        }

        # Elasticsearch 연결
        try:
            from elasticsearch import Elasticsearch
            self.es = Elasticsearch(['http://localhost:9200'])
        except:
            self.es = None
            print("⚠️ Elasticsearch 연결 실패 - 호텔 개수 기반 조정 불가")
    
    def parse_command(self, command: str) -> Dict:
        """
        자연어 명령 파싱

        예:
          "500m 확장" → {'action': 'expand', 'value': 500}
          "지하철역 기준 호텔 10개 제한" → {'action': 'target_count_transit', 'value': 10}
        """
        command = command.lower()

        for pattern, action in self.adjustment_patterns.items():
            match = re.search(pattern, command)
            if match:
                result = {'action': action}

                # 숫자 추출 (그룹 순서 고려)
                if match.groups():
                    try:
                        # 마지막 그룹 전에서 숫자 찾기
                        for group in match.groups():
                            if group and group.isdigit():
                                result['value'] = int(group)
                                break
                    except:
                        pass

                print(f"🤖 명령 해석: '{command}' → {result}")
                return result

        print(f"⚠️ 알 수 없는 명령: '{command}'")
        return {'action': 'unknown'}
    
    def fetch_pois(self, polygon_geojson: Dict, poi_type: str) -> List[Dict]:
        """
        폴리곤 내 POI (Point of Interest) 가져오기
        
        Args:
            polygon_geojson: 폴리곤 GeoJSON
            poi_type: 'tourism', 'transit', 'restaurant' 등
        """
        try:
            poly = shape(polygon_geojson)
            bounds = poly.bounds  # (minx, miny, maxx, maxy)
            
            # Overpass API 쿼리
            poi_tags = {
                'tourism': 'tourism',
                'transit': 'railway=station',
                'restaurant': 'amenity=restaurant'
            }
            
            tag = poi_tags.get(poi_type, 'tourism')
            
            overpass_url = "https://overpass-api.de/api/interpreter"
            query = f"""
[out:json][timeout:25];
(
  node[{tag}]({bounds[1]},{bounds[0]},{bounds[3]},{bounds[2]});
  way[{tag}]({bounds[1]},{bounds[0]},{bounds[3]},{bounds[2]});
);
out center;
"""
            
            response = requests.post(overpass_url, data={'data': query})
            time.sleep(1)
            
            if response.status_code != 200:
                print(f"⚠️ Overpass API 오류: {response.status_code}")
                return []
            
            data = response.json()
            elements = data.get('elements', [])
            
            pois = []
            for elem in elements:
                if elem['type'] == 'node':
                    pois.append({
                        'lat': elem['lat'],
                        'lon': elem['lon'],
                        'name': elem.get('tags', {}).get('name', 'Unknown')
                    })
                elif 'center' in elem:
                    pois.append({
                        'lat': elem['center']['lat'],
                        'lon': elem['center']['lon'],
                        'name': elem.get('tags', {}).get('name', 'Unknown')
                    })
            
            print(f"✅ {poi_type} POI {len(pois)}개 발견")
            return pois
            
        except Exception as e:
            print(f"❌ POI 검색 오류: {e}")
            return []
    
    def expand_polygon(self, polygon_geojson: Dict, distance_m: int) -> Dict:
        """
        폴리곤 확장
        
        Args:
            polygon_geojson: 원본 폴리곤
            distance_m: 확장 거리 (미터)
        """
        try:
            poly = shape(polygon_geojson)
            
            # 미터를 경위도로 변환 (대략)
            # 1도 ≈ 111km
            degrees = distance_m / 111000
            
            expanded = poly.buffer(degrees)
            
            coords = [list(expanded.exterior.coords)]
            
            print(f"✅ 폴리곤 {distance_m}m 확장 완료")
            
            return {
                'type': 'Polygon',
                'coordinates': coords
            }
            
        except Exception as e:
            print(f"❌ 폴리곤 확장 오류: {e}")
            return polygon_geojson
    
    def shrink_polygon(self, polygon_geojson: Dict, distance_m: int) -> Dict:
        """
        폴리곤 축소
        """
        return self.expand_polygon(polygon_geojson, -distance_m)
    
    def weight_by_pois(self, polygon_geojson: Dict, poi_type: str) -> Dict:
        """
        POI 위치에 가중치를 두고 폴리곤 조정

        예: 관광지 중심으로 → 관광지가 많은 쪽으로 폴리곤 확장
        """
        try:
            pois = self.fetch_pois(polygon_geojson, poi_type)

            if not pois:
                print("⚠️ POI가 없어 조정하지 않음")
                return polygon_geojson

            poly = shape(polygon_geojson)

            # POI 위치에 작은 버퍼 생성
            poi_buffers = []
            for poi in pois:
                point = Point(poi['lon'], poi['lat'])
                buffered = point.buffer(0.005)  # 약 500m
                poi_buffers.append(buffered)

            # 원본 폴리곤과 POI 버퍼 병합
            combined = unary_union([poly] + poi_buffers)

            if combined.geom_type == 'Polygon':
                coords = [list(combined.exterior.coords)]
            else:
                # MultiPolygon인 경우 가장 큰 것
                largest = max(combined.geoms, key=lambda p: p.area)
                coords = [list(largest.exterior.coords)]

            print(f"✅ {poi_type} 가중치 적용 완료 ({len(pois)}개 POI)")

            return {
                'type': 'Polygon',
                'coordinates': coords
            }

        except Exception as e:
            print(f"❌ POI 가중치 오류: {e}")
            return polygon_geojson

    def shrink_to_poi_area(self, polygon_geojson: Dict, poi_type: str, buffer_m: int = 300) -> Dict:
        """
        POI 밀집 구역만 남기고 나머지 축소

        예: "관광지 구역만" → 관광지가 없는 영역 제거

        Args:
            polygon_geojson: 원본 폴리곤
            poi_type: 'tourism', 'transit', 'restaurant' 등
            buffer_m: POI 주변 버퍼 크기 (미터)
        """
        try:
            pois = self.fetch_pois(polygon_geojson, poi_type)

            if not pois:
                print("⚠️ POI가 없어 조정하지 않음")
                return polygon_geojson

            if len(pois) < 3:
                print("⚠️ POI가 너무 적어 조정하지 않음 (최소 3개 필요)")
                return polygon_geojson

            poly = shape(polygon_geojson)

            # POI 좌표들로 MultiPoint 생성
            points = [Point(poi['lon'], poi['lat']) for poi in pois]
            multipoint = MultiPoint(points)

            # Convex Hull 생성 (POI를 감싸는 최소 다각형)
            hull = multipoint.convex_hull

            # 버퍼 추가 (너무 타이트하지 않게)
            degrees = buffer_m / 111000
            buffered_hull = hull.buffer(degrees)

            # 원본 폴리곤과 교집합 (원본 범위를 벗어나지 않음)
            result = poly.intersection(buffered_hull)

            if result.is_empty:
                print("⚠️ 교집합이 비어있음, 원본 반환")
                return polygon_geojson

            if result.geom_type == 'Polygon':
                coords = [list(result.exterior.coords)]
            elif result.geom_type == 'MultiPolygon':
                # 가장 큰 폴리곤 선택
                largest = max(result.geoms, key=lambda p: p.area)
                coords = [list(largest.exterior.coords)]
            else:
                print(f"⚠️ 예상치 못한 geometry type: {result.geom_type}")
                return polygon_geojson

            print(f"✅ {poi_type} 밀집 구역으로 축소 완료 ({len(pois)}개 POI, {buffer_m}m 버퍼)")

            return {
                'type': 'Polygon',
                'coordinates': coords
            }

        except Exception as e:
            print(f"❌ POI 밀집 구역 축소 오류: {e}")
            return polygon_geojson
    
    def count_hotels_in_polygon(self, polygon_geojson: Dict) -> int:
        """
        폴리곤 내 호텔 개수 카운트

        Args:
            polygon_geojson: 폴리곤 GeoJSON

        Returns:
            호텔 개수
        """
        if not self.es:
            print("⚠️ Elasticsearch 연결 없음")
            return 0

        try:
            coords = polygon_geojson['coordinates'][0]
            points = [{'lat': c[1], 'lon': c[0]} for c in coords]

            response = self.es.search(
                index='hotels',
                body={
                    'query': {
                        'bool': {
                            'filter': {
                                'geo_polygon': {
                                    'location': {
                                        'points': points
                                    }
                                }
                            }
                        }
                    },
                    'size': 0
                }
            )

            return response['hits']['total']['value']

        except Exception as e:
            print(f"❌ 호텔 개수 조회 오류: {e}")
            return 0

    def get_hotels_in_polygon(self, polygon_geojson: Dict) -> List[Dict]:
        """
        폴리곤 내 호텔 목록 가져오기 (위치 포함)

        Args:
            polygon_geojson: 폴리곤 GeoJSON

        Returns:
            호텔 목록 [{'lat': ..., 'lon': ..., 'name': ...}, ...]
        """
        if not self.es:
            return []

        try:
            coords = polygon_geojson['coordinates'][0]
            points = [{'lat': c[1], 'lon': c[0]} for c in coords]

            response = self.es.search(
                index='hotels',
                body={
                    'query': {
                        'bool': {
                            'filter': {
                                'geo_polygon': {
                                    'location': {
                                        'points': points
                                    }
                                }
                            }
                        }
                    },
                    'size': 1000,  # 충분히 큰 값
                    '_source': ['name', 'location']
                }
            )

            hotels = []
            for hit in response['hits']['hits']:
                loc = hit['_source']['location']
                hotels.append({
                    'lat': loc['coordinates'][1],
                    'lon': loc['coordinates'][0],
                    'name': hit['_source'].get('name', 'Unknown')
                })

            return hotels

        except Exception as e:
            print(f"❌ 호텔 목록 조회 오류: {e}")
            return []

    def adjust_by_target_count_with_poi(self, polygon_geojson: Dict, target_count: int, poi_type: str) -> Tuple[Dict, List[str]]:
        """
        POI 기준으로 호텔 개수 조정

        Args:
            polygon_geojson: 원본 폴리곤
            target_count: 목표 호텔 개수
            poi_type: 'transit' (지하철역) 또는 'tourism' (관광지)

        Returns:
            (조정된 폴리곤 GeoJSON, 선택된 호텔 이름 리스트)
        """
        if not self.es:
            print("⚠️ Elasticsearch 연결 없음 - 조정 불가")
            return polygon_geojson, []

        print(f"\n🎯 목표: {target_count}개 호텔 (기준: {poi_type})")

        # 현재 폴리곤 내 호텔과 POI 가져오기
        hotels = self.get_hotels_in_polygon(polygon_geojson)
        pois = self.fetch_pois(polygon_geojson, poi_type)

        if not pois:
            print(f"⚠️ {poi_type} POI가 없어 중심점 기준으로 전환")
            return self.adjust_by_target_count(polygon_geojson, target_count), []

        current_count = len(hotels)
        print(f"📍 현재: {current_count}개 호텔, {len(pois)}개 {poi_type} POI")

        if current_count <= target_count:
            print("✅ 이미 목표 이하")
            return polygon_geojson, []

        if current_count == 0:
            print("⚠️ 호텔이 없음")
            return polygon_geojson, []

        from geopy.distance import geodesic

        # 각 호텔에 대해 "가장 가까운 POI까지의 거리" 계산
        for hotel in hotels:
            min_distance = float('inf')
            closest_poi_name = None

            for poi in pois:
                distance = geodesic(
                    (hotel['lat'], hotel['lon']),
                    (poi['lat'], poi['lon'])
                ).meters

                if distance < min_distance:
                    min_distance = distance
                    closest_poi_name = poi['name']

            hotel['min_poi_distance'] = min_distance
            hotel['closest_poi'] = closest_poi_name

        # "가장 가까운 POI까지의 거리"가 짧은 순서대로 정렬
        hotels.sort(key=lambda h: h['min_poi_distance'])
        selected_hotels = hotels[:target_count]

        print(f"  ✅ 모든 {poi_type} POI 고려, 가장 가까운 {target_count}개 선택")

        # 선택된 호텔 정보 출력 (상위 3개)
        for i, hotel in enumerate(selected_hotels[:3], 1):
            print(f"     {i}. {hotel['name'][:20]} - {hotel['closest_poi']} ({hotel['min_poi_distance']:.0f}m)")

        # 선택된 호텔들로 새 폴리곤 생성
        if len(selected_hotels) < 1:
            print("  ⚠️ 호텔이 없어 원본 반환")
            return polygon_geojson

        # POI 기준 선택에서는 Convex Hull 대신 각 호텔 주변에 작은 원을 만들어 union
        # 이렇게 하면 선택된 호텔만 포함하고 중간에 낀 다른 호텔은 제외됨
        initial_buffer = 0.0003  # 약 33m - 각 호텔 주변 작은 원
        hotel_circles = []
        for hotel in selected_hotels:
            point = Point(hotel['lon'], hotel['lat'])
            circle = point.buffer(initial_buffer)
            hotel_circles.append(circle)

        # 모든 원을 합치기
        buffered = unary_union(hotel_circles)

        # MultiPolygon인 경우 (호텔들이 너무 멀리 떨어져 있어 원들이 합쳐지지 않음)
        # 각 원의 Convex Hull로 하나의 폴리곤 만들기
        if buffered.geom_type == 'MultiPolygon':
            print(f"  ℹ️ 호텔들이 떨어져 있어 MultiPolygon → Convex Hull로 통합")
            # 모든 점들의 Convex Hull
            all_points = []
            for circle in buffered.geoms:
                all_points.extend(list(circle.exterior.coords))
            hull = MultiPoint(all_points).convex_hull
            buffered = hull.buffer(0.00005)  # 작은 버퍼 추가

        if buffered.geom_type == 'Polygon':
            coords = [list(buffered.exterior.coords)]
        else:
            # 예외 처리
            coords = [[]]

        new_polygon = {'type': 'Polygon', 'coordinates': coords}

        # 검증 및 반복 조정
        final_count = self.count_hotels_in_polygon(new_polygon)
        print(f"  📊 검증: {final_count}개 호텔 포함")

        circle_radius = initial_buffer
        attempts = 0
        max_attempts = 10  # POI 기반은 더 많은 시도 허용

        # 너무 많으면 축소, 너무 적으면 확장
        while final_count != target_count and attempts < max_attempts:
            attempts += 1
            prev_count = final_count

            if final_count > target_count:
                # 축소: 각 호텔 원 반경 줄이기
                circle_radius *= 0.7
                print(f"  ⚙️ 시도 {attempts}: 원 반경 {int(circle_radius*111000)}m로 축소...")
            else:
                # 확장: 각 호텔 원 반경 늘리기
                circle_radius *= 1.3
                print(f"  ⚙️ 시도 {attempts}: 원 반경 {int(circle_radius*111000)}m로 확장...")

            # 새로운 반경으로 원들 재생성
            new_circles = []
            for hotel in selected_hotels:
                point = Point(hotel['lon'], hotel['lat'])
                circle = point.buffer(circle_radius)
                new_circles.append(circle)

            buffered_adjusted = unary_union(new_circles)

            # MultiPolygon인 경우 Convex Hull로 통합
            if buffered_adjusted.geom_type == 'MultiPolygon':
                all_points = []
                for circle in buffered_adjusted.geoms:
                    all_points.extend(list(circle.exterior.coords))
                hull_temp = MultiPoint(all_points).convex_hull
                buffered_adjusted = hull_temp.buffer(circle_radius * 0.1)

            if buffered_adjusted.geom_type == 'Polygon':
                coords = [list(buffered_adjusted.exterior.coords)]
                new_polygon = {'type': 'Polygon', 'coordinates': coords}
                final_count = self.count_hotels_in_polygon(new_polygon)
                print(f"     → {final_count}개 호텔")

                # 목표 달성
                if final_count == target_count:
                    break

                # 목표를 넘어선 경우
                if (prev_count < target_count and final_count > target_count) or \
                   (prev_count > target_count and final_count < target_count):
                    print(f"     ⚠️ 목표 지나침, 더 가까운 값 사용")
                    # 이전 상태가 더 가까우면 복원
                    if abs(prev_count - target_count) < abs(final_count - target_count):
                        circle_radius /= 1.3 if prev_count < target_count else 0.7
                        # 한번 더 적용
                        new_circles = []
                        for hotel in selected_hotels:
                            point = Point(hotel['lon'], hotel['lat'])
                            circle = point.buffer(circle_radius)
                            new_circles.append(circle)
                        buffered_adjusted = unary_union(new_circles)
                        if buffered_adjusted.geom_type == 'MultiPolygon':
                            all_points = []
                            for circle in buffered_adjusted.geoms:
                                all_points.extend(list(circle.exterior.coords))
                            hull_temp = MultiPoint(all_points).convex_hull
                            buffered_adjusted = hull_temp.buffer(circle_radius * 0.1)
                        if buffered_adjusted.geom_type == 'Polygon':
                            coords = [list(buffered_adjusted.exterior.coords)]
                            new_polygon = {'type': 'Polygon', 'coordinates': coords}
                            final_count = self.count_hotels_in_polygon(new_polygon)
                    break

                # 변화가 없으면 중단
                if final_count == prev_count:
                    print(f"     ⚠️ 더 이상 개선 불가")
                    break

        print(f"\n✅ 최종: {final_count}개 호텔 (목표 {target_count}개, 차이 {abs(final_count - target_count)}개)")

        # 선택된 호텔 이름 리스트 반환
        selected_hotel_names = [h['name'] for h in selected_hotels]
        print(f"🎯 필터링용 호텔 목록: {len(selected_hotel_names)}개")

        return new_polygon, selected_hotel_names

    def adjust_by_target_count(self, polygon_geojson: Dict, target_count: int) -> Dict:
        """
        목표 호텔 개수에 맞춰 폴리곤 조정

        **개선된 방법**: 실제 호텔 위치를 기반으로 정확히 N개만 포함하는 폴리곤 생성

        Args:
            polygon_geojson: 원본 폴리곤
            target_count: 목표 호텔 개수

        Returns:
            조정된 폴리곤 GeoJSON
        """
        if not self.es:
            print("⚠️ Elasticsearch 연결 없음 - 조정 불가")
            return polygon_geojson

        print(f"\n🎯 목표: {target_count}개 호텔")

        # 현재 폴리곤 내 모든 호텔 가져오기
        hotels = self.get_hotels_in_polygon(polygon_geojson)
        current_count = len(hotels)
        print(f"📍 현재: {current_count}개 호텔")

        if current_count == target_count:
            print("✅ 이미 목표 개수와 일치!")
            return polygon_geojson

        if current_count == 0:
            print("⚠️ 호텔이 없음")
            return polygon_geojson

        # 방법 1: 축소 - 중심점 기준 가까운 N개 선택
        if current_count > target_count:
            print(f"📐 축소 모드: {current_count}개 → {target_count}개")

            # 폴리곤 중심점 계산
            poly = shape(polygon_geojson)
            centroid = poly.centroid
            center_lat, center_lon = centroid.y, centroid.x

            # 중심점으로부터 거리 계산
            from geopy.distance import geodesic
            for hotel in hotels:
                hotel['distance'] = geodesic(
                    (center_lat, center_lon),
                    (hotel['lat'], hotel['lon'])
                ).meters

            # 거리순 정렬 후 상위 N개 선택
            hotels.sort(key=lambda h: h['distance'])
            selected_hotels = hotels[:target_count]

            print(f"  ✅ 중심점 기준 가까운 {target_count}개 선택")

            # 선택된 호텔들로 새 폴리곤 생성
            if len(selected_hotels) < 3:
                print("  ⚠️ 호텔이 너무 적어 원본 반환")
                return polygon_geojson

            points = [Point(h['lon'], h['lat']) for h in selected_hotels]
            multipoint = MultiPoint(points)

            # Convex Hull + 약간의 버퍼
            hull = multipoint.convex_hull
            buffered = hull.buffer(0.002)  # 약 200m 버퍼

            if buffered.geom_type == 'Polygon':
                coords = [list(buffered.exterior.coords)]
            else:
                coords = [list(buffered.exterior.coords)] if hasattr(buffered, 'exterior') else [[]]

            new_polygon = {
                'type': 'Polygon',
                'coordinates': coords
            }

            # 검증 및 반복 조정
            final_count = self.count_hotels_in_polygon(new_polygon)
            print(f"  📊 검증: {final_count}개 호텔 포함")

            # 목표보다 많으면 버퍼를 점진적으로 줄이기
            buffer_size = 0.002
            attempts = 0
            max_attempts = 5

            while final_count > target_count and attempts < max_attempts:
                attempts += 1
                buffer_size *= 0.5  # 버퍼 절반으로 축소

                print(f"  ⚙️ 시도 {attempts}: 버퍼 {int(buffer_size*111000)}m로 축소...")

                buffered_adjusted = hull.buffer(buffer_size)
                if buffered_adjusted.geom_type == 'Polygon':
                    coords = [list(buffered_adjusted.exterior.coords)]
                    new_polygon = {'type': 'Polygon', 'coordinates': coords}
                    final_count = self.count_hotels_in_polygon(new_polygon)
                    print(f"     → {final_count}개 호텔")

                    # 목표 이하로 떨어지면 이전 버퍼로 복귀
                    if final_count < target_count:
                        print(f"     ⚠️ 너무 줄었음, 이전 버퍼 사용")
                        buffer_size *= 2  # 다시 복구
                        buffered_adjusted = hull.buffer(buffer_size)
                        if buffered_adjusted.geom_type == 'Polygon':
                            coords = [list(buffered_adjusted.exterior.coords)]
                            new_polygon = {'type': 'Polygon', 'coordinates': coords}
                            final_count = self.count_hotels_in_polygon(new_polygon)
                        break

            print(f"\n✅ 최종: {final_count}개 호텔 (목표 {target_count}개, 차이 {abs(final_count - target_count)}개)")
            return new_polygon

        # 방법 2: 확장 - 기존 이진 탐색 방식 유지
        else:
            print(f"📏 확장 모드: {current_count}개 → {target_count}개")

            min_distance = 0
            count_ratio = target_count / max(current_count, 1)

            if count_ratio > 10:
                max_distance = 10000
            elif count_ratio > 5:
                max_distance = 5000
            elif count_ratio > 2:
                max_distance = 3000
            else:
                max_distance = 2000

            best_polygon = polygon_geojson
            best_diff = abs(current_count - target_count)

            print(f"  최대 탐색 범위: {max_distance}m")

            for iteration in range(15):
                mid_distance = (min_distance + max_distance) // 2
                if mid_distance == 0:
                    break

                test_polygon = self.expand_polygon(polygon_geojson, mid_distance)
                test_count = self.count_hotels_in_polygon(test_polygon)
                diff = abs(test_count - target_count)

                print(f"  시도 {iteration + 1}: +{mid_distance}m → {test_count}개 (차이: {diff}개)")

                if diff < best_diff:
                    best_diff = diff
                    best_polygon = test_polygon

                if test_count == target_count:
                    print(f"  ✅ 정확히 {target_count}개 달성!")
                    return test_polygon

                if test_count < target_count:
                    min_distance = mid_distance
                else:
                    max_distance = mid_distance

                if max_distance - min_distance < 10:
                    break

            final_count = self.count_hotels_in_polygon(best_polygon)
            print(f"\n✅ 최종: {final_count}개 호텔 (목표 {target_count}개, 차이 {abs(final_count - target_count)}개)")
            return best_polygon

    def adjust_polygon(self, polygon_geojson: Dict, command: str) -> Tuple[Dict, List[str]]:
        """
        자연어 명령으로 폴리곤 조정 (메인 함수)

        Args:
            polygon_geojson: 원본 폴리곤
            command: 자연어 명령

        Returns:
            (조정된 폴리곤 GeoJSON, 선택된 호텔 이름 리스트 - POI 기반 조정만 해당)
        """
        parsed = self.parse_command(command)
        action = parsed.get('action')

        if action == 'expand':
            distance = parsed.get('value', 500)
            return self.expand_polygon(polygon_geojson, distance), []

        elif action == 'shrink':
            distance = parsed.get('value', 500)
            return self.shrink_polygon(polygon_geojson, distance), []

        elif action == 'tourism_weight':
            return self.weight_by_pois(polygon_geojson, 'tourism'), []

        elif action == 'transit_weight':
            return self.weight_by_pois(polygon_geojson, 'transit'), []

        elif action == 'restaurant_weight':
            return self.weight_by_pois(polygon_geojson, 'restaurant'), []

        elif action == 'tourism_only':
            return self.shrink_to_poi_area(polygon_geojson, 'tourism'), []

        elif action == 'transit_only':
            return self.shrink_to_poi_area(polygon_geojson, 'transit'), []

        elif action == 'restaurant_only':
            return self.shrink_to_poi_area(polygon_geojson, 'restaurant'), []

        elif action == 'target_count':
            target = parsed.get('value', 100)
            return self.adjust_by_target_count(polygon_geojson, target), []

        elif action == 'target_count_transit':
            target = parsed.get('value', 100)
            return self.adjust_by_target_count_with_poi(polygon_geojson, target, 'transit')

        elif action == 'target_count_tourism':
            target = parsed.get('value', 100)
            return self.adjust_by_target_count_with_poi(polygon_geojson, target, 'tourism')

        else:
            print("⚠️ 조정 없이 원본 반환")
            return polygon_geojson, []


# 테스트 코드
if __name__ == '__main__':
    adjuster = NaturalLanguageAdjuster()
    
    # 잠실 동적 폴리곤 로드
    with open('data/processed/잠실_dynamic_polygon.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    original_polygon = data['polygon']
    
    print("\n" + "="*60)
    print("🧪 테스트: 자연어 폴리곤 조정")
    print("="*60)
    
    # 테스트 명령들
    test_commands = [
        "500m 확장",
        "300m 축소",
        "관광지 기준으로 변경"
    ]
    
    for command in test_commands:
        print(f"\n📝 명령: '{command}'")
        adjusted = adjuster.adjust_polygon(original_polygon, command)
        
        orig_coords = len(original_polygon['coordinates'][0])
        adj_coords = len(adjusted['coordinates'][0])
        
        print(f"  - 원본: {orig_coords}개 좌표")
        print(f"  - 조정: {adj_coords}개 좌표")
        print(f"  - 변화: {adj_coords - orig_coords:+d}개")
        
        # 저장
        filename = f"data/processed/잠실_{command.replace(' ', '_')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({'command': command, 'polygon': adjusted}, f, ensure_ascii=False, indent=2)
        print(f"  - 저장: {filename}")
    
    print("\n✅ 모든 테스트 완료!")
