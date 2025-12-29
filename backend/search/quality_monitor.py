#!/usr/bin/env python3
"""
검색 품질 모니터링 시스템 (Rating 기반 전환율)
"""

from elasticsearch import Elasticsearch
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import statistics


class SearchQualityMonitor:
    def __init__(self, es_host: str = "http://localhost:9200"):
        """
        Args:
            es_host: Elasticsearch 호스트 URL
        """
        self.es = Elasticsearch([es_host])
        self.logs_index = "search_logs"
        self.hotels_index = "hotels"

        # 품질 임계값 설정
        self.thresholds = {
            "min_avg_rating": 4.0,           # 평균 rating 최소값
            "max_low_quality_ratio": 0.30,    # 저품질 호텔 최대 비율 (30%)
            "rating_drop_threshold": 0.10,    # 평균 rating 급락 기준 (10%)
            "low_quality_rating": 3.5,        # 저품질 기준
            "high_quality_rating": 4.5        # 우수 기준
        }

    def get_search_quality_stats(self, hours: int = 24) -> Dict:
        """
        최근 N시간 검색 결과 품질 통계

        Args:
            hours: 조회 기간 (시간)

        Returns:
            품질 통계
        """
        # 최근 검색 로그 조회
        query = {
            "size": 1000,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"event_type": "hotel_search"}},
                        {"term": {"success": True}},
                        {"exists": {"field": "quality_metrics"}},  # quality_metrics 있는 것만
                        {"range": {"timestamp": {"gte": f"now-{hours}h"}}}
                    ]
                }
            },
            "sort": [{"timestamp": {"order": "desc"}}]
        }

        result = self.es.search(index=self.logs_index, body=query)
        searches = result['hits']['hits']

        if not searches:
            return {
                "period_hours": hours,
                "total_searches": 0,
                "message": "검색 데이터 없음"
            }

        # 각 검색의 호텔 품질 분석 (로그에서 직접 가져오기)
        quality_data = []

        for search in searches:
            source = search['_source']
            session_id = source['session_id']
            timestamp = source['timestamp']
            hotel_count = source.get('hotel_count', 0)
            quality_metrics = source.get('quality_metrics')

            if not quality_metrics:
                continue

            quality_data.append({
                "timestamp": timestamp,
                "session_id": session_id,
                "avg_rating": quality_metrics['avg_rating'],
                "low_quality_ratio": quality_metrics['low_quality_ratio'],
                "high_quality_ratio": quality_metrics['high_quality_ratio'],
                "hotel_count": hotel_count
            })

        if not quality_data:
            return {
                "period_hours": hours,
                "total_searches": len(searches),
                "message": "품질 데이터 수집 실패"
            }

        # 전체 통계 계산
        avg_ratings = [d['avg_rating'] for d in quality_data]
        low_quality_ratios = [d['low_quality_ratio'] for d in quality_data]
        high_quality_ratios = [d['high_quality_ratio'] for d in quality_data]

        overall_avg_rating = statistics.mean(avg_ratings)
        overall_low_quality_ratio = statistics.mean(low_quality_ratios)
        overall_high_quality_ratio = statistics.mean(high_quality_ratios)

        # 알림 조건 체크
        alerts = []

        if overall_avg_rating < self.thresholds['min_avg_rating']:
            alerts.append({
                "severity": "warning",
                "type": "low_avg_rating",
                "message": f"평균 rating 낮음: {overall_avg_rating:.2f} < {self.thresholds['min_avg_rating']}"
            })

        if overall_low_quality_ratio > self.thresholds['max_low_quality_ratio']:
            alerts.append({
                "severity": "warning",
                "type": "high_low_quality_ratio",
                "message": f"저품질 호텔 비율 높음: {overall_low_quality_ratio*100:.1f}% > {self.thresholds['max_low_quality_ratio']*100:.0f}%"
            })

        return {
            "period_hours": hours,
            "total_searches": len(quality_data),
            "overall": {
                "avg_rating": round(overall_avg_rating, 2),
                "low_quality_ratio": round(overall_low_quality_ratio, 3),
                "high_quality_ratio": round(overall_high_quality_ratio, 3),
                "median_rating": round(statistics.median(avg_ratings), 2)
            },
            "thresholds": self.thresholds,
            "alerts": alerts,
            "status": "healthy" if not alerts else "warning",
            "trend": quality_data[-10:]  # 최근 10개 샘플
        }

    def _get_hotel_quality_sample(self, sample_size: int = 10) -> Optional[Dict]:
        """
        호텔 품질 샘플링 (실제로는 검색 결과 호텔들의 rating을 분석해야 함)

        Args:
            sample_size: 샘플 크기

        Returns:
            품질 통계
        """
        try:
            # 랜덤 샘플링
            query = {
                "size": sample_size,
                "query": {"function_score": {"random_score": {}}}
            }

            result = self.es.search(index=self.hotels_index, body=query)
            hotels = [hit['_source'] for hit in result['hits']['hits']]

            if not hotels:
                return None

            ratings = [h.get('rating', 0) for h in hotels if h.get('rating', 0) > 0]

            if not ratings:
                return None

            avg_rating = statistics.mean(ratings)
            low_quality_count = sum(1 for r in ratings if r < self.thresholds['low_quality_rating'])
            high_quality_count = sum(1 for r in ratings if r >= self.thresholds['high_quality_rating'])

            return {
                "avg_rating": avg_rating,
                "low_quality_ratio": low_quality_count / len(ratings),
                "high_quality_ratio": high_quality_count / len(ratings)
            }

        except Exception as e:
            print(f"샘플링 에러: {e}")
            return None

    def compare_with_previous_period(self, current_hours: int = 24) -> Dict:
        """
        이전 기간 대비 품질 변화 분석

        Args:
            current_hours: 현재 기간 (시간)

        Returns:
            비교 분석 결과
        """
        current = self.get_search_quality_stats(hours=current_hours)
        previous = self.get_search_quality_stats_for_period(
            start_hours_ago=current_hours * 2,
            end_hours_ago=current_hours
        )

        if current.get('total_searches', 0) == 0 or previous.get('total_searches', 0) == 0:
            return {
                "message": "비교 데이터 부족",
                "current": current,
                "previous": previous
            }

        # 변화율 계산
        current_avg = current['overall']['avg_rating']
        previous_avg = previous['overall']['avg_rating']
        rating_change = current_avg - previous_avg
        rating_change_percent = (rating_change / previous_avg) * 100 if previous_avg > 0 else 0

        # 급락 감지
        alerts = current.get('alerts', []).copy()

        if rating_change_percent < -self.thresholds['rating_drop_threshold'] * 100:
            alerts.append({
                "severity": "critical",
                "type": "rating_drop",
                "message": f"평균 rating 급락: {rating_change_percent:.1f}% (전 기간 대비)"
            })

        return {
            "period_hours": current_hours,
            "current": current['overall'],
            "previous": previous['overall'],
            "changes": {
                "rating_change": round(rating_change, 2),
                "rating_change_percent": round(rating_change_percent, 1),
                "low_quality_ratio_change": round(
                    current['overall']['low_quality_ratio'] - previous['overall']['low_quality_ratio'],
                    3
                )
            },
            "alerts": alerts,
            "status": "critical" if any(a['severity'] == 'critical' for a in alerts) else (
                "warning" if alerts else "healthy"
            )
        }

    def get_search_quality_stats_for_period(
        self,
        start_hours_ago: int,
        end_hours_ago: int
    ) -> Dict:
        """
        특정 기간의 검색 품질 통계

        Args:
            start_hours_ago: 시작 시점 (N시간 전)
            end_hours_ago: 종료 시점 (N시간 전)

        Returns:
            품질 통계
        """
        query = {
            "size": 1000,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"event_type": "hotel_search"}},
                        {"term": {"success": True}},
                        {
                            "range": {
                                "timestamp": {
                                    "gte": f"now-{start_hours_ago}h",
                                    "lt": f"now-{end_hours_ago}h"
                                }
                            }
                        }
                    ]
                }
            }
        }

        result = self.es.search(index=self.logs_index, body=query)
        searches = result['hits']['hits']

        if not searches:
            return {"total_searches": 0}

        # 품질 분석 (간단히 샘플링)
        quality_data = []
        for search in searches[:100]:  # 최대 100개 샘플
            hotel_count = search['_source'].get('hotel_count', 0)
            if hotel_count > 0:
                stats = self._get_hotel_quality_sample(hotel_count)
                if stats:
                    quality_data.append(stats)

        if not quality_data:
            return {"total_searches": len(searches)}

        avg_ratings = [d['avg_rating'] for d in quality_data]
        low_quality_ratios = [d['low_quality_ratio'] for d in quality_data]
        high_quality_ratios = [d['high_quality_ratio'] for d in quality_data]

        return {
            "total_searches": len(searches),
            "overall": {
                "avg_rating": round(statistics.mean(avg_ratings), 2),
                "low_quality_ratio": round(statistics.mean(low_quality_ratios), 3),
                "high_quality_ratio": round(statistics.mean(high_quality_ratios), 3)
            }
        }

    def get_low_quality_searches(self, hours: int = 24, limit: int = 10) -> List[Dict]:
        """
        저품질 검색 결과 목록

        Args:
            hours: 조회 기간 (시간)
            limit: 결과 개수

        Returns:
            저품질 검색 목록
        """
        # 실제로는 검색 결과와 호텔 rating을 조인해서 분석
        # 여기서는 간단히 최근 검색 중 샘플링

        query = {
            "size": limit * 5,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"event_type": "hotel_search"}},
                        {"term": {"success": True}},
                        {"range": {"timestamp": {"gte": f"now-{hours}h"}}}
                    ]
                }
            },
            "sort": [{"timestamp": {"order": "desc"}}]
        }

        result = self.es.search(index=self.logs_index, body=query)
        searches = result['hits']['hits']

        low_quality_searches = []

        for search in searches:
            source = search['_source']
            hotel_count = source.get('hotel_count', 0)

            if hotel_count == 0:
                continue

            stats = self._get_hotel_quality_sample(hotel_count)

            if stats and stats['avg_rating'] < self.thresholds['low_quality_rating']:
                low_quality_searches.append({
                    "timestamp": source['timestamp'],
                    "session_id": source['session_id'],
                    "hotel_count": hotel_count,
                    "avg_rating": round(stats['avg_rating'], 2),
                    "low_quality_ratio": round(stats['low_quality_ratio'], 2)
                })

            if len(low_quality_searches) >= limit:
                break

        return low_quality_searches

    def update_thresholds(self, new_thresholds: Dict):
        """
        임계값 업데이트

        Args:
            new_thresholds: 새로운 임계값
        """
        self.thresholds.update(new_thresholds)
