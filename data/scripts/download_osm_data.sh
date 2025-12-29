#!/bin/bash

echo "📥 OpenStreetMap 데이터 다운로드 중..."

# 서울 지역 OSM 데이터 다운로드 (Overpass API 사용)
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

# 파일 크기 확인
ls -lh data/raw/seoul_hotels.json
