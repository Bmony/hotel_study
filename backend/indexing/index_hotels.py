#!/usr/bin/env python3
"""
OpenStreetMap 호텔 데이터를 Elasticsearch에 인덱싱
"""

import json
import re
from elasticsearch import Elasticsearch, helpers

# Elasticsearch 연결
es = Elasticsearch(['http://localhost:9200'])

def load_osm_data(filepath):
    """OSM JSON 데이터 로드"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_hotel_info(element):
    """OSM 요소에서 호텔 정보 추출"""
    tags = element.get('tags', {})
    
    # 위치 정보
    if element['type'] == 'node':
        lat = element.get('lat')
        lon = element.get('lon')
    elif element['type'] == 'way' and 'center' in element:
        lat = element['center'].get('lat')
        lon = element['center'].get('lon')
    else:
        return None
    
    if not lat or not lon:
        return None
    
    # 호텔 정보
    hotel = {
        'id': element['id'],
        'name': tags.get('name', f"Hotel {element['id']}"),
        'address': tags.get('addr:full', tags.get('addr:street', '')),
        'location': {
            'lat': lat,
            'lon': lon
        },
        'city': tags.get('addr:city', '서울'),
        'country': 'KR',
        'facilities': []
    }
    
    # 시설 정보 추출
    if tags.get('internet_access') == 'yes':
        hotel['facilities'].append('wifi')
    if tags.get('wheelchair') == 'yes':
        hotel['facilities'].append('wheelchair_accessible')
    
    # 별점 처리 (숫자만 추출)
    if 'stars' in tags:
        try:
            stars_str = re.sub(r'[^0-9.]', '', tags['stars'])
            if stars_str:
                hotel['rating'] = float(stars_str)
        except:
            pass
    
    return hotel

def index_hotels(osm_data):
    """호텔 데이터를 Elasticsearch에 인덱싱"""
    
    hotels = []
    autocomplete_entries = []
    
    for element in osm_data.get('elements', []):
        hotel = extract_hotel_info(element)
        if hotel:
            hotels.append({
                '_index': 'hotels',
                '_id': hotel['id'],
                '_source': hotel
            })
            
            # 자동완성 데이터 생성
            autocomplete_entries.append({
                '_index': 'autocomplete',
                '_id': f"hotel_{hotel['id']}",
                '_source': {
                    'name': hotel['name'],
                    'suggest': {
                        'input': [hotel['name'], hotel['city']],
                        'weight': 10
                    },
                    'type': 'hotel'
                }
            })
    
    # 벌크 인덱싱
    if hotels:
        success, failed = helpers.bulk(es, hotels, chunk_size=100, request_timeout=30)
        print(f"✅ 호텔 인덱싱: {success}개 성공, {failed}개 실패")
    
    if autocomplete_entries:
        success, failed = helpers.bulk(es, autocomplete_entries, chunk_size=100, request_timeout=30)
        print(f"✅ 자동완성 인덱싱: {success}개 성공, {failed}개 실패")
    
    return len(hotels)

def create_destinations():
    """서울 주요 지역 목적지 생성"""
    
    destinations = [
        {
            "name": "강남",
            "destinationId": 1,
            "type": "district",
            "location": {
                "type": "polygon",
                "coordinates": [[
                    [127.02, 37.49],
                    [127.06, 37.49],
                    [127.06, 37.52],
                    [127.02, 37.52],
                    [127.02, 37.49]
                ]]
            }
        },
        {
            "name": "명동",
            "destinationId": 2,
            "type": "district",
            "location": {
                "type": "polygon",
                "coordinates": [[
                    [126.98, 37.56],
                    [126.99, 37.56],
                    [126.99, 37.57],
                    [126.98, 37.57],
                    [126.98, 37.56]
                ]]
            }
        },
        {
            "name": "홍대",
            "destinationId": 3,
            "type": "district",
            "location": {
                "type": "polygon",
                "coordinates": [[
                    [126.92, 37.55],
                    [126.93, 37.55],
                    [126.93, 37.56],
                    [126.92, 37.56],
                    [126.92, 37.55]
                ]]
            }
        },
        {
            "name": "이태원",
            "destinationId": 4,
            "type": "district",
            "location": {
                "type": "polygon",
                "coordinates": [[
                    [126.99, 37.53],
                    [127.01, 37.53],
                    [127.01, 37.54],
                    [126.99, 37.54],
                    [126.99, 37.53]
                ]]
            }
        },
        {
            "name": "잠실",
            "destinationId": 5,
            "type": "district",
            "location": {
                "type": "polygon",
                "coordinates": [[
                    [127.08, 37.50],
                    [127.10, 37.50],
                    [127.10, 37.52],
                    [127.08, 37.52],
                    [127.08, 37.50]
                ]]
            }
        }
    ]
    
    # 목적지 인덱싱
    for dest in destinations:
        es.index(index='destinations', id=dest['destinationId'], document=dest)
        
        # 자동완성에도 추가
        es.index(index='autocomplete', id=f"dest_{dest['destinationId']}", document={
            'name': dest['name'],
            'suggest': {
                'input': [dest['name']],
                'weight': 20  # 목적지가 호텔보다 높은 우선순위
            },
            'type': 'destination'
        })
    
    print(f"✅ 목적지 인덱싱: {len(destinations)}개 완료")
    return len(destinations)

if __name__ == '__main__':
    print("🚀 호텔 데이터 인덱싱 시작...")
    
    # OSM 데이터 로드
    osm_data = load_osm_data('data/raw/seoul_hotels.json')
    print(f"📊 OSM 데이터 로드: {len(osm_data.get('elements', []))}개 요소")
    
    # 호텔 인덱싱
    hotel_count = index_hotels(osm_data)
    
    # 목적지 생성
    dest_count = create_destinations()
    
    # 결과 확인
    print("\n📈 인덱싱 결과:")
    print(f"  - 호텔: {hotel_count}개")
    print(f"  - 목적지: {dest_count}개")
    print(f"  - 자동완성 항목: {hotel_count + dest_count}개")
    
    # 인덱스 상태 확인
    for index in ['hotels', 'destinations', 'autocomplete']:
        count = es.count(index=index)['count']
        print(f"  - {index}: {count}개 문서")
    
    print("\n🎉 인덱싱 완료!")
