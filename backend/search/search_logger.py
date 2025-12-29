#!/usr/bin/env python3
"""
검색 로그 수집 및 분석 시스템
"""

from elasticsearch import Elasticsearch
from datetime import datetime
from typing import Dict, Optional, List
import uuid


class SearchLogger:
    def __init__(self, es_host: str = "http://localhost:9200"):
        """
        Args:
            es_host: Elasticsearch 호스트 URL
        """
        self.es = Elasticsearch([es_host])
        self.index_name = "search_logs"
        self._ensure_index()

    def _ensure_index(self):
        """검색 로그 인덱스 생성 (존재하지 않을 경우)"""
        if not self.es.indices.exists(index=self.index_name):
            mapping = {
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0
                },
                "mappings": {
                    "properties": {
                        "session_id": {"type": "keyword"},
                        "timestamp": {"type": "date"},
                        "event_type": {"type": "keyword"},  # search, adjust, result

                        # 검색 정보
                        "search_query": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                        "adjustment_command": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},

                        # 결과 정보
                        "hotel_count": {"type": "integer"},
                        "selected_hotel_count": {"type": "integer"},
                        "polygon_coords_count": {"type": "integer"},

                        # 성능 정보
                        "search_time_ms": {"type": "integer"},
                        "success": {"type": "boolean"},
                        "error_message": {"type": "text"},

                        # POI 정보
                        "poi_type": {"type": "keyword"},  # transit, tourism, restaurant
                        "area_characteristics": {
                            "properties": {
                                "tourism_count": {"type": "integer"},
                                "transit_count": {"type": "integer"},
                                "restaurant_count": {"type": "integer"},
                                "area_km2": {"type": "float"}
                            }
                        },

                        # 사용자 행동
                        "user_action": {"type": "keyword"},  # polygon_generate, polygon_adjust, hotel_search
                        "strategy_used": {"type": "keyword"}
                    }
                }
            }
            self.es.indices.create(index=self.index_name, body=mapping)
            print(f"✅ 검색 로그 인덱스 '{self.index_name}' 생성 완료")

    def log_polygon_generation(
        self,
        session_id: str,
        search_query: str,
        polygon_coords_count: int,
        area_characteristics: Optional[Dict] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """폴리곤 생성 로그"""
        doc = {
            "session_id": session_id,
            "timestamp": datetime.utcnow(),
            "event_type": "polygon_generate",
            "user_action": "polygon_generate",
            "search_query": search_query,
            "polygon_coords_count": polygon_coords_count,
            "area_characteristics": area_characteristics,
            "success": success,
            "error_message": error_message
        }
        self.es.index(index=self.index_name, body=doc)

    def log_polygon_adjustment(
        self,
        session_id: str,
        adjustment_command: str,
        polygon_coords_count: int,
        poi_type: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """폴리곤 조정 로그"""
        doc = {
            "session_id": session_id,
            "timestamp": datetime.utcnow(),
            "event_type": "polygon_adjust",
            "user_action": "polygon_adjust",
            "adjustment_command": adjustment_command,
            "polygon_coords_count": polygon_coords_count,
            "poi_type": poi_type,
            "success": success,
            "error_message": error_message
        }
        self.es.index(index=self.index_name, body=doc)

    def log_hotel_search(
        self,
        session_id: str,
        hotel_count: int,
        selected_hotel_count: Optional[int],
        search_time_ms: int,
        hotels: Optional[List[Dict]] = None,  # 호텔 목록 추가
        poi_type: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """호텔 검색 로그 (품질 지표 포함)"""

        # 호텔 품질 지표 계산
        quality_metrics = None
        if hotels and len(hotels) > 0:
            ratings = [h.get('rating', 0) for h in hotels if h.get('rating', 0) > 0]

            if ratings:
                avg_rating = sum(ratings) / len(ratings)
                low_quality_count = sum(1 for r in ratings if r < 3.5)
                high_quality_count = sum(1 for r in ratings if r >= 4.5)

                quality_metrics = {
                    "avg_rating": round(avg_rating, 2),
                    "min_rating": round(min(ratings), 1),
                    "max_rating": round(max(ratings), 1),
                    "low_quality_count": low_quality_count,
                    "low_quality_ratio": round(low_quality_count / len(ratings), 3),
                    "high_quality_count": high_quality_count,
                    "high_quality_ratio": round(high_quality_count / len(ratings), 3),
                    "total_rated_hotels": len(ratings)
                }

        doc = {
            "session_id": session_id,
            "timestamp": datetime.utcnow(),
            "event_type": "hotel_search",
            "user_action": "hotel_search",
            "hotel_count": hotel_count,
            "selected_hotel_count": selected_hotel_count if selected_hotel_count else hotel_count,
            "search_time_ms": search_time_ms,
            "poi_type": poi_type,
            "quality_metrics": quality_metrics,  # 품질 지표 추가
            "success": success,
            "error_message": error_message
        }
        self.es.index(index=self.index_name, body=doc)


class SearchAnalytics:
    def __init__(self, es_host: str = "http://localhost:9200"):
        """
        Args:
            es_host: Elasticsearch 호스트 URL
        """
        self.es = Elasticsearch([es_host])
        self.index_name = "search_logs"

    def get_popular_searches(self, limit: int = 10, days: int = 7) -> List[Dict]:
        """
        인기 검색어 조회

        Args:
            limit: 결과 개수
            days: 조회 기간 (일)

        Returns:
            인기 검색어 리스트
        """
        query = {
            "size": 0,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"event_type": "polygon_generate"}},
                        {"range": {"timestamp": {"gte": f"now-{days}d"}}}
                    ]
                }
            },
            "aggs": {
                "popular_queries": {
                    "terms": {
                        "field": "search_query.keyword",
                        "size": limit,
                        "order": {"_count": "desc"}
                    }
                }
            }
        }

        result = self.es.search(index=self.index_name, body=query)
        buckets = result['aggregations']['popular_queries']['buckets']

        return [
            {
                "query": bucket['key'],
                "count": bucket['doc_count']
            }
            for bucket in buckets
        ]

    def get_popular_adjustments(self, limit: int = 10, days: int = 7) -> List[Dict]:
        """
        인기 조정 명령어 조회

        Args:
            limit: 결과 개수
            days: 조회 기간 (일)

        Returns:
            인기 조정 명령 리스트
        """
        query = {
            "size": 0,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"event_type": "polygon_adjust"}},
                        {"range": {"timestamp": {"gte": f"now-{days}d"}}}
                    ]
                }
            },
            "aggs": {
                "popular_adjustments": {
                    "terms": {
                        "field": "adjustment_command.keyword",
                        "size": limit,
                        "order": {"_count": "desc"}
                    }
                }
            }
        }

        result = self.es.search(index=self.index_name, body=query)
        buckets = result['aggregations']['popular_adjustments']['buckets']

        return [
            {
                "command": bucket['key'],
                "count": bucket['doc_count']
            }
            for bucket in buckets
        ]

    def get_failure_rate(self, days: int = 7) -> Dict:
        """
        검색 실패율 조회

        Args:
            days: 조회 기간 (일)

        Returns:
            실패율 통계
        """
        query = {
            "size": 0,
            "query": {
                "range": {"timestamp": {"gte": f"now-{days}d"}}
            },
            "aggs": {
                "total": {"value_count": {"field": "session_id"}},
                "success": {
                    "filter": {"term": {"success": True}},
                    "aggs": {
                        "count": {"value_count": {"field": "session_id"}}
                    }
                },
                "failed": {
                    "filter": {"term": {"success": False}},
                    "aggs": {
                        "count": {"value_count": {"field": "session_id"}}
                    }
                },
                "by_event_type": {
                    "terms": {"field": "event_type"},
                    "aggs": {
                        "success_rate": {
                            "filters": {
                                "filters": {
                                    "success": {"term": {"success": True}},
                                    "failed": {"term": {"success": False}}
                                }
                            }
                        }
                    }
                }
            }
        }

        result = self.es.search(index=self.index_name, body=query)
        aggs = result['aggregations']

        total = aggs['total']['value']
        success = aggs['success']['count']['value']
        failed = aggs['failed']['count']['value']

        return {
            "total_requests": total,
            "successful": success,
            "failed": failed,
            "failure_rate": round((failed / total * 100) if total > 0 else 0, 2),
            "success_rate": round((success / total * 100) if total > 0 else 0, 2),
            "by_event_type": {
                bucket['key']: {
                    "total": bucket['doc_count'],
                    "success": bucket['success_rate']['buckets']['success']['doc_count'],
                    "failed": bucket['success_rate']['buckets']['failed']['doc_count']
                }
                for bucket in aggs['by_event_type']['buckets']
            }
        }

    def get_search_statistics(self, days: int = 7) -> Dict:
        """
        검색 통계 조회

        Args:
            days: 조회 기간 (일)

        Returns:
            검색 통계
        """
        query = {
            "size": 0,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"event_type": "hotel_search"}},
                        {"range": {"timestamp": {"gte": f"now-{days}d"}}}
                    ]
                }
            },
            "aggs": {
                "avg_hotel_count": {"avg": {"field": "hotel_count"}},
                "avg_search_time": {"avg": {"field": "search_time_ms"}},
                "total_searches": {"value_count": {"field": "session_id"}},
                "poi_distribution": {
                    "terms": {"field": "poi_type", "missing": "none"}
                }
            }
        }

        result = self.es.search(index=self.index_name, body=query)
        aggs = result['aggregations']

        return {
            "total_searches": aggs['total_searches']['value'],
            "avg_hotel_count": round(aggs['avg_hotel_count']['value'], 1) if aggs['avg_hotel_count']['value'] else 0,
            "avg_search_time_ms": round(aggs['avg_search_time']['value'], 1) if aggs['avg_search_time']['value'] else 0,
            "poi_distribution": {
                bucket['key']: bucket['doc_count']
                for bucket in aggs['poi_distribution']['buckets']
            }
        }

    def get_hourly_search_trend(self, days: int = 7) -> List[Dict]:
        """
        시간대별 검색 추이

        Args:
            days: 조회 기간 (일)

        Returns:
            시간대별 검색량
        """
        query = {
            "size": 0,
            "query": {
                "range": {"timestamp": {"gte": f"now-{days}d"}}
            },
            "aggs": {
                "searches_over_time": {
                    "date_histogram": {
                        "field": "timestamp",
                        "calendar_interval": "hour",
                        "min_doc_count": 0
                    }
                }
            }
        }

        result = self.es.search(index=self.index_name, body=query)
        buckets = result['aggregations']['searches_over_time']['buckets']

        return [
            {
                "timestamp": bucket['key_as_string'],
                "count": bucket['doc_count']
            }
            for bucket in buckets
        ]
