#!/usr/bin/env python3
"""
호텔 평점 및 리뷰 개수 랜덤화 스크립트
- rating: 2.0 ~ 5.0 사이 랜덤 (0.5 단위)
- reviewCount: 0 ~ 300 사이 랜덤
"""

import json
import random

# 파일 경로
input_file = 'data/processed/enriched_hotels.json'
output_file = 'data/processed/enriched_hotels.json'

print("🎲 호텔 평점/리뷰 랜덤화 시작...")

# 데이터 로드
with open(input_file, 'r', encoding='utf-8') as f:
    hotels = json.load(f)

print(f"📊 총 {len(hotels)}개 호텔 처리 중...")

# 평점 분포 설정 (현실적인 분포)
rating_weights = {
    5.0: 0.15,   # 15% - 최고 평점
    4.5: 0.25,   # 25% - 매우 좋음
    4.0: 0.30,   # 30% - 좋음
    3.5: 0.20,   # 20% - 보통
    3.0: 0.07,   # 7%  - 약간 낮음
    2.5: 0.02,   # 2%  - 낮음
    2.0: 0.01    # 1%  - 매우 낮음
}

ratings = list(rating_weights.keys())
weights = list(rating_weights.values())

# 각 호텔 데이터 업데이트
for hotel in hotels:
    # 평점: 가중치 기반 랜덤 선택
    hotel['rating'] = random.choices(ratings, weights=weights)[0]

    # 리뷰 개수: 평점이 높을수록 리뷰가 많은 경향
    if hotel['rating'] >= 4.5:
        hotel['reviewCount'] = random.randint(80, 300)
    elif hotel['rating'] >= 4.0:
        hotel['reviewCount'] = random.randint(50, 200)
    elif hotel['rating'] >= 3.5:
        hotel['reviewCount'] = random.randint(20, 150)
    elif hotel['rating'] >= 3.0:
        hotel['reviewCount'] = random.randint(10, 100)
    else:
        hotel['reviewCount'] = random.randint(5, 50)

# 데이터 저장
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(hotels, f, ensure_ascii=False, indent=2)

print(f"✅ {len(hotels)}개 호텔 평점/리뷰 랜덤화 완료!")

# 통계 출력
rating_counts = {}
for hotel in hotels:
    rating = hotel['rating']
    rating_counts[rating] = rating_counts.get(rating, 0) + 1

print("\n📊 평점 분포:")
for rating in sorted(rating_counts.keys(), reverse=True):
    count = rating_counts[rating]
    percentage = (count / len(hotels)) * 100
    print(f"  ⭐ {rating}: {count}개 ({percentage:.1f}%)")

print(f"\n💾 저장 완료: {output_file}")
