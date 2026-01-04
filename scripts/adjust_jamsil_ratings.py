#!/usr/bin/env python3
"""
잠실 영역 호텔 평점/리뷰 조정 (좌표 기반)
- 1개만 5.0점, 리뷰 250개
- 나머지는 전부 3.5점, 리뷰 80개
"""

import json

# 파일 경로
input_file = 'data/processed/enriched_hotels.json'
output_file = 'data/processed/enriched_hotels.json'

print("🎯 잠실 영역 호텔 평점/리뷰 조정 시작...")

# 데이터 로드
with open(input_file, 'r', encoding='utf-8') as f:
    hotels = json.load(f)

# 잠실 영역 좌표 범위 (폴리곤 생성 범위와 동일)
# 경도: 127.06 ~ 127.12
# 위도: 37.50 ~ 37.52
jamsil_hotels = []

for hotel in hotels:
    if hotel.get('location') and hotel['location'].get('coordinates'):
        lon, lat = hotel['location']['coordinates']

        # 잠실 영역 체크
        if 127.06 <= lon <= 127.12 and 37.50 <= lat <= 37.52:
            jamsil_hotels.append(hotel)

print(f"📊 잠실 영역 호텔: {len(jamsil_hotels)}개 발견")

if len(jamsil_hotels) == 0:
    print("❌ 잠실 영역 호텔이 없습니다")
    exit(1)

# 평점/리뷰 조정
# 첫 번째 호텔만 5.0점/250개, 나머지는 3.5점/80개
for i, hotel in enumerate(jamsil_hotels):
    if i == 0:
        hotel['rating'] = 5.0
        hotel['reviewCount'] = 250
        print(f"⭐ {hotel['name']}: 5.0점 (리뷰 250개)")
    else:
        hotel['rating'] = 3.5
        hotel['reviewCount'] = 80
        print(f"   {hotel['name']}: 3.5점 (리뷰 80개)")

# 데이터 저장
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(hotels, f, ensure_ascii=False, indent=2)

print(f"\n✅ 평점/리뷰 조정 완료!")
print(f"💾 저장: {output_file}")
print(f"\n📊 요약:")
print(f"  - 5.0점 (리뷰 250개): 1개 ({jamsil_hotels[0]['name']})")
print(f"  - 3.5점 (리뷰 80개): {len(jamsil_hotels) - 1}개")
