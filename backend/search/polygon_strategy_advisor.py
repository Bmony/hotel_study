#!/usr/bin/env python3
"""
폴리곤 조정 전략 분석 및 제안 시스템

검색어와 지역 특성을 분석하여 최적의 폴리곤 조정 전략 제안
"""

import json
from typing import Dict, List
from shapely.geometry import shape
from natural_language_adjuster import NaturalLanguageAdjuster


class PolygonStrategyAdvisor:
    def __init__(self):
        self.adjuster = NaturalLanguageAdjuster()

        # 지역별 특성 (사전 지식 기반)
        self.area_knowledge = {
            '잠실': {'type': 'tourism', 'keywords': ['관광', '가족', '테마파크']},
            '강남': {'type': 'business', 'keywords': ['비즈니스', '쇼핑', '맛집']},
            '명동': {'type': 'shopping', 'keywords': ['쇼핑', '관광', '외국인']},
            '홍대': {'type': 'entertainment', 'keywords': ['문화', '예술', '클럽']},
            '이태원': {'type': 'multicultural', 'keywords': ['다국적', '음식', '나이트']},
            '여의도': {'type': 'business', 'keywords': ['금융', '비즈니스', '컨벤션']},
            '인사동': {'type': 'cultural', 'keywords': ['전통', '문화', '관광']},
        }

    def analyze_area(self, polygon_geojson: Dict, query: str = "") -> Dict:
        """
        폴리곤 영역의 특성 분석

        Returns:
            {
                'tourism_density': 'high' | 'medium' | 'low',
                'transit_access': 'excellent' | 'good' | 'fair',
                'restaurant_density': 'high' | 'medium' | 'low',
                'estimated_hotels': int
            }
        """
        try:
            # POI 데이터 수집
            tourism_pois = self.adjuster.fetch_pois(polygon_geojson, 'tourism')
            transit_pois = self.adjuster.fetch_pois(polygon_geojson, 'transit')
            restaurant_pois = self.adjuster.fetch_pois(polygon_geojson, 'restaurant')

            # 폴리곤 면적 계산 (대략적)
            poly = shape(polygon_geojson)
            area_km2 = poly.area * 111 * 111  # 대략적 변환

            # 밀도 계산 (개/km²)
            def categorize_density(count, area):
                if area == 0:
                    return 'unknown'
                density = count / area
                if density > 50:
                    return 'high'
                elif density > 20:
                    return 'medium'
                else:
                    return 'low'

            tourism_density = categorize_density(len(tourism_pois), area_km2)
            restaurant_density = categorize_density(len(restaurant_pois), area_km2)

            # 교통 접근성
            transit_count = len(transit_pois)
            if transit_count >= 5:
                transit_access = 'excellent'
            elif transit_count >= 2:
                transit_access = 'good'
            else:
                transit_access = 'fair'

            # 호텔 수 추정 (실제 검색 대신 근사값)
            estimated_hotels = int(area_km2 * 30)  # km² 당 평균 30개 가정

            print(f"📊 지역 분석 완료:")
            print(f"  - 관광지: {len(tourism_pois)}개 ({tourism_density})")
            print(f"  - 지하철역: {len(transit_pois)}개 ({transit_access})")
            print(f"  - 음식점: {len(restaurant_pois)}개 ({restaurant_density})")
            print(f"  - 예상 호텔: {estimated_hotels}개")

            return {
                'tourism_density': tourism_density,
                'tourism_count': len(tourism_pois),
                'transit_access': transit_access,
                'transit_count': len(transit_pois),
                'restaurant_density': restaurant_density,
                'restaurant_count': len(restaurant_pois),
                'estimated_hotels': estimated_hotels,
                'area_km2': round(area_km2, 2)
            }

        except Exception as e:
            print(f"❌ 지역 분석 오류: {e}")
            return {
                'tourism_density': 'unknown',
                'transit_access': 'unknown',
                'restaurant_density': 'unknown',
                'estimated_hotels': 0
            }

    def suggest_strategies(self, polygon_geojson: Dict, query: str = "") -> List[Dict]:
        """
        폴리곤 조정 전략 제안

        Returns:
            [
                {
                    'command': '명령어',
                    'reason': '이유',
                    'expected_impact': '예상 효과',
                    'priority': 'high' | 'medium' | 'low'
                }
            ]
        """
        try:
            # 지역 특성 분석
            characteristics = self.analyze_area(polygon_geojson, query)

            strategies = []

            # 전략 1: 관광지 기반
            if characteristics['tourism_density'] == 'high':
                strategies.append({
                    'command': '관광지 기준으로 변경',
                    'reason': f"{characteristics['tourism_count']}개 관광지 밀집 지역",
                    'expected_impact': '관광 목적 고객 타겟팅 강화 (+15~20% 전환율)',
                    'priority': 'high',
                    'type': 'expand'
                })

                strategies.append({
                    'command': '관광지 구역만',
                    'reason': '관광지 중심 영역으로 정밀 타겟팅',
                    'expected_impact': '노이즈 제거로 관련도 높은 호텔만 표시 (+10% 클릭률)',
                    'priority': 'medium',
                    'type': 'shrink'
                })

            # 전략 2: 교통 접근성 기반
            if characteristics['transit_access'] in ['excellent', 'good']:
                strategies.append({
                    'command': '지하철역 기준으로 변경',
                    'reason': f"{characteristics['transit_count']}개 역 인근의 우수한 접근성",
                    'expected_impact': '대중교통 이용 고객 편의성 향상 (+12% 예약률)',
                    'priority': 'high' if characteristics['transit_access'] == 'excellent' else 'medium',
                    'type': 'expand'
                })

                if characteristics['transit_count'] >= 3:
                    strategies.append({
                        'command': '역세권만',
                        'reason': '지하철 접근성 우선 지역으로 축소',
                        'expected_impact': '교통 편의성 강조로 만족도 증가',
                        'priority': 'medium',
                        'type': 'shrink'
                    })

            # 전략 3: 음식점 밀집 지역
            if characteristics['restaurant_density'] == 'high':
                strategies.append({
                    'command': '음식점 기준으로 변경',
                    'reason': f"{characteristics['restaurant_count']}개 음식점이 있는 맛집 지역",
                    'expected_impact': '식도락 관심 고객 타겟팅 (+8% 만족도)',
                    'priority': 'medium',
                    'type': 'expand'
                })

            # 전략 4: 확장 전략 (폴리곤이 작은 경우)
            if characteristics['area_km2'] < 2:
                strategies.append({
                    'command': '500m 확장',
                    'reason': f"현재 범위({characteristics['area_km2']}km²)가 좁아 주변 호텔 누락 가능",
                    'expected_impact': '검색 결과 +30~40% 증가, 선택지 확대',
                    'priority': 'high',
                    'type': 'expand'
                })
            elif characteristics['area_km2'] < 5:
                strategies.append({
                    'command': '300m 확장',
                    'reason': '적당한 범위 확대로 선택지 증가',
                    'expected_impact': '검색 결과 +15~20% 증가',
                    'priority': 'medium',
                    'type': 'expand'
                })

            # 전략 5: 축소 전략 (폴리곤이 너무 큰 경우)
            if characteristics['area_km2'] > 10:
                strategies.append({
                    'command': '500m 축소',
                    'reason': f"현재 범위({characteristics['area_km2']}km²)가 넓어 관련성 낮은 호텔 포함",
                    'expected_impact': '정밀 타겟팅으로 관련도 +25% 향상',
                    'priority': 'medium',
                    'type': 'shrink'
                })

            # 전략 6: 검색어 기반 맞춤 전략
            query_lower = query.lower()
            area_type = None

            for area_name, info in self.area_knowledge.items():
                if area_name in query:
                    area_type = info['type']
                    break

            if area_type == 'tourism':
                # 이미 관광지 전략이 있으면 우선순위만 상향
                for s in strategies:
                    if '관광지' in s['command']:
                        s['priority'] = 'high'
            elif area_type == 'business':
                strategies.append({
                    'command': '지하철역 기준으로 변경',
                    'reason': '비즈니스 지역: 교통 접근성이 핵심',
                    'expected_impact': '비즈니스 여행객 편의성 극대화',
                    'priority': 'high',
                    'type': 'expand'
                })

            # 우선순위별 정렬
            priority_order = {'high': 0, 'medium': 1, 'low': 2}
            strategies.sort(key=lambda x: priority_order.get(x['priority'], 3))

            # 상위 5개만 반환
            strategies = strategies[:5]

            print(f"\n💡 전략 제안 완료: {len(strategies)}개")
            for i, s in enumerate(strategies, 1):
                print(f"  {i}. [{s['priority'].upper()}] {s['command']}")
                print(f"     → {s['reason']}")

            return strategies

        except Exception as e:
            print(f"❌ 전략 제안 오류: {e}")
            return []

    def estimate_impact(self, original_polygon: Dict, adjusted_polygon: Dict,
                       command: str, characteristics: Dict) -> Dict:
        """
        폴리곤 조정의 예상 영향도 계산

        Returns:
            {
                'area_change_percent': float,  # 면적 변화율
                'hotel_count_change': str,     # 예상 호텔 수 변화
                'conversion_impact': str       # 전환율 영향
            }
        """
        try:
            orig_poly = shape(original_polygon)
            adj_poly = shape(adjusted_polygon)

            orig_area = orig_poly.area
            adj_area = adj_poly.area

            area_change = ((adj_area - orig_area) / orig_area) * 100

            # 호텔 수 변화 추정
            if area_change > 20:
                hotel_change = f"+{int(area_change)}% 증가"
            elif area_change < -20:
                hotel_change = f"{int(area_change)}% 감소"
            else:
                hotel_change = "거의 변화 없음"

            # 전환율 영향 추정
            if '관광지' in command and characteristics.get('tourism_density') == 'high':
                conversion_impact = "+15~20% 개선"
            elif '지하철' in command or '역' in command:
                conversion_impact = "+10~15% 개선"
            elif '확장' in command:
                conversion_impact = "선택지 증가로 만족도 향상"
            elif '축소' in command or '구역만' in command:
                conversion_impact = "정밀 타겟팅으로 관련도 향상"
            else:
                conversion_impact = "약간의 개선 예상"

            return {
                'area_change_percent': round(area_change, 1),
                'hotel_count_change': hotel_change,
                'conversion_impact': conversion_impact
            }

        except Exception as e:
            print(f"❌ 영향도 계산 오류: {e}")
            return {
                'area_change_percent': 0,
                'hotel_count_change': '알 수 없음',
                'conversion_impact': '알 수 없음'
            }


# 테스트 코드
if __name__ == '__main__':
    advisor = PolygonStrategyAdvisor()

    # 잠실 폴리곤 로드
    with open('data/processed/잠실_dynamic_polygon.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    polygon = data['polygon']
    query = data['query']

    print("\n" + "="*60)
    print("🎯 폴리곤 전략 분석 시스템 테스트")
    print("="*60)
    print(f"\n검색어: {query}")

    # 지역 특성 분석
    print("\n1️⃣ 지역 특성 분석")
    print("-" * 60)
    characteristics = advisor.analyze_area(polygon, query)

    # 전략 제안
    print("\n2️⃣ 최적화 전략 제안")
    print("-" * 60)
    strategies = advisor.suggest_strategies(polygon, query)

    # 전략 상세 출력
    print("\n3️⃣ 전략 상세")
    print("-" * 60)
    for i, strategy in enumerate(strategies, 1):
        print(f"\n전략 {i}: {strategy['command']}")
        print(f"  우선순위: {strategy['priority'].upper()}")
        print(f"  이유: {strategy['reason']}")
        print(f"  예상 효과: {strategy['expected_impact']}")
        print(f"  유형: {strategy['type']} (확장/축소)")

    print("\n✅ 전략 분석 완료!")
