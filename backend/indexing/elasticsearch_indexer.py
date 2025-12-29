#!/usr/bin/env python3
"""
Elasticsearch 호텔 데이터 인덱서

강화된 호텔 데이터를 Elasticsearch에 벌크 인덱싱
"""

import json
import sys
from elasticsearch import Elasticsearch, helpers
from typing import List, Dict
import os


class HotelIndexer:
    def __init__(self, es_host: str = "http://localhost:9200"):
        """
        Args:
            es_host: Elasticsearch 호스트 URL
        """
        self.es = Elasticsearch([es_host])
        self.index_name = "hotels"

    def create_index_with_mapping(self):
        """
        호텔 인덱스 생성 (매핑 포함)
        """
        # 기존 인덱스 삭제 (재생성을 위해)
        if self.es.indices.exists(index=self.index_name):
            print(f"⚠️  기존 인덱스 '{self.index_name}' 삭제 중...")
            self.es.indices.delete(index=self.index_name)

        # 새 인덱스 매핑
        mapping = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
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
                    "id": {"type": "keyword"},
                    "name": {
                        "type": "text",
                        "analyzer": "korean",
                        "fields": {
                            "keyword": {"type": "keyword"}
                        }
                    },
                    "name_en": {"type": "text"},
                    "category": {"type": "keyword"},
                    "type": {"type": "keyword"},

                    "address": {
                        "properties": {
                            "full": {"type": "text", "analyzer": "korean"},
                            "city": {"type": "keyword"},
                            "district": {"type": "keyword"},
                            "street": {"type": "text", "analyzer": "korean"}
                        }
                    },

                    "location": {"type": "geo_point"},

                    # 검색 메타데이터
                    "keywords": {
                        "type": "text",
                        "analyzer": "korean"
                    },
                    "synonyms": {"type": "text", "analyzer": "korean"},
                    "relatedKeywords": {"type": "text", "analyzer": "korean"},

                    # 랭킹 및 인기도
                    "rankScore": {"type": "integer"},
                    "popularity": {"type": "integer"},
                    "reviewCount": {"type": "integer"},
                    "rating": {"type": "float"},

                    # 주변 정보
                    "nearbyPOI": {
                        "type": "nested",
                        "properties": {
                            "name": {"type": "text", "analyzer": "korean"},
                            "type": {"type": "keyword"},
                            "distance": {"type": "integer"}
                        }
                    },

                    "transitInfo": {
                        "properties": {
                            "subway": {"type": "text", "analyzer": "korean"},
                            "bus": {"type": "text", "analyzer": "korean"}
                        }
                    },

                    # 메타 정보
                    "source": {"type": "keyword"},
                    "lastUpdated": {"type": "date", "format": "yyyy-MM-dd"},
                    "dataQuality": {"type": "keyword"}
                }
            }
        }

        print(f"🔧 인덱스 '{self.index_name}' 생성 중...")
        self.es.indices.create(index=self.index_name, body=mapping)
        print(f"✅ 인덱스 생성 완료!")

    def bulk_index_hotels(self, hotels: List[Dict]) -> Dict:
        """
        호텔 데이터 벌크 인덱싱

        Args:
            hotels: 호텔 데이터 리스트

        Returns:
            인덱싱 결과
        """
        print(f"\n📦 {len(hotels)}개 호텔 벌크 인덱싱 시작...")

        # Elasticsearch 벌크 액션 생성
        actions = []
        for hotel in hotels:
            action = {
                "_index": self.index_name,
                "_id": hotel['id'],
                "_source": hotel
            }
            actions.append(action)

        # 벌크 인덱싱 실행
        success, failed = helpers.bulk(
            self.es,
            actions,
            chunk_size=100,
            request_timeout=30
        )

        # 인덱스 refresh (즉시 검색 가능하도록)
        self.es.indices.refresh(index=self.index_name)

        print(f"✅ 인덱싱 완료!")
        print(f"  - 성공: {success}개")
        print(f"  - 실패: {len(failed)}개")

        if failed:
            print(f"\n⚠️ 실패한 문서:")
            for item in failed[:5]:  # 처음 5개만 출력
                print(f"  - {item}")

        return {
            "success": success,
            "failed": len(failed)
        }

    def verify_index(self):
        """
        인덱스 상태 확인
        """
        print(f"\n🔍 인덱스 '{self.index_name}' 상태 확인...")

        # 문서 개수
        count = self.es.count(index=self.index_name)['count']
        print(f"  - 총 문서 수: {count}개")

        # 샘플 검색
        result = self.es.search(
            index=self.index_name,
            body={
                "query": {"match_all": {}},
                "size": 1,
                "sort": [{"rankScore": {"order": "desc"}}]
            }
        )

        if result['hits']['hits']:
            sample = result['hits']['hits'][0]['_source']
            print(f"  - 샘플 호텔: {sample['name']}")
            print(f"    랭킹: {sample['rankScore']}, POI: {len(sample['nearbyPOI'])}개")

        # 통계
        stats_result = self.es.search(
            index=self.index_name,
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

        avg_rank = stats_result['aggregations']['avg_rank'].get('value')
        avg_rating = stats_result['aggregations']['avg_rating'].get('value')

        print(f"\n📊 통계:")
        if avg_rank is not None:
            print(f"  - 평균 랭킹: {avg_rank:.1f}")
        if avg_rating is not None:
            print(f"  - 평균 평점: {avg_rating:.1f}")
        print(f"  - 카테고리 분포:")
        for bucket in stats_result['aggregations']['categories']['buckets']:
            print(f"    {bucket['key']}: {bucket['doc_count']}개")

    def test_search(self):
        """
        검색 테스트
        """
        print(f"\n🔍 검색 테스트...")

        # 1. 키워드 검색
        result = self.es.search(
            index=self.index_name,
            body={
                "query": {
                    "multi_match": {
                        "query": "강남",
                        "fields": ["name^3", "keywords^2", "address.full"]
                    }
                },
                "size": 3,
                "sort": [{"rankScore": {"order": "desc"}}]
            }
        )

        print(f"\n1️⃣ '강남' 검색 결과 (상위 3개):")
        for hit in result['hits']['hits']:
            hotel = hit['_source']
            print(f"  - {hotel['name']} (랭킹: {hotel['rankScore']}, 평점: {hotel['rating']})")

        # 2. 고득점 호텔
        result = self.es.search(
            index=self.index_name,
            body={
                "query": {
                    "range": {"rankScore": {"gte": 95}}
                },
                "size": 3,
                "sort": [{"rankScore": {"order": "desc"}}]
            }
        )

        print(f"\n2️⃣ 랭킹 95점 이상 호텔 (상위 3개):")
        for hit in result['hits']['hits']:
            hotel = hit['_source']
            print(f"  - {hotel['name']} (랭킹: {hotel['rankScore']}, 지역: {hotel['address']['district']})")

        # 3. 지하철역 근처 호텔
        result = self.es.search(
            index=self.index_name,
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
                },
                "size": 3,
                "sort": [{"rankScore": {"order": "desc"}}]
            }
        )

        print(f"\n3️⃣ 지하철역 300m 이내 호텔 (상위 3개):")
        for hit in result['hits']['hits']:
            hotel = hit['_source']
            subway_pois = [p for p in hotel['nearbyPOI'] if p['type'] == '지하철' and p['distance'] < 300]
            subway_names = [p['name'] for p in subway_pois[:2]]
            print(f"  - {hotel['name']} (근처 역: {', '.join(subway_names)})")


def main():
    """메인 실행 함수"""
    print("\n" + "="*60)
    print("🚀 Elasticsearch 호텔 데이터 인덱싱")
    print("="*60)

    # 프로젝트 루트 경로
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    data_file = os.path.join(project_root, 'data/processed/enriched_hotels.json')

    # 데이터 로드
    print(f"\n📂 데이터 로드: {data_file}")
    with open(data_file, 'r', encoding='utf-8') as f:
        hotels = json.load(f)

    print(f"✅ {len(hotels)}개 호텔 데이터 로드 완료")

    # 인덱서 초기화
    indexer = HotelIndexer()

    # 인덱스 생성
    indexer.create_index_with_mapping()

    # 벌크 인덱싱
    result = indexer.bulk_index_hotels(hotels)

    # 검증
    indexer.verify_index()

    # 검색 테스트
    indexer.test_search()

    print(f"\n✅ 모든 작업 완료!")
    print(f"\n💡 다음 명령어로 검색 테스트:")
    print(f"   curl -X GET 'http://localhost:9200/hotels/_search?pretty' \\")
    print(f"     -H 'Content-Type: application/json' \\")
    print(f"     -d '{{\"query\": {{\"match\": {{\"name\": \"호텔\"}}}}}}'")


if __name__ == '__main__':
    main()
