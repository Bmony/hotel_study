#!/usr/bin/env python3
"""
AI 폴리곤 생성/조정 API 서버
"""

from flask import Flask, request, jsonify, session
from flask_cors import CORS
from ai_polygon_generator import AIPolygonGenerator
from natural_language_adjuster import NaturalLanguageAdjuster
from polygon_strategy_advisor import PolygonStrategyAdvisor
from search_logger import SearchLogger, SearchAnalytics
from quality_monitor import SearchQualityMonitor
from elasticsearch import Elasticsearch
import json
import uuid
import subprocess
import os

app = Flask(__name__)
app.secret_key = 'hotel-search-secret-key-2025'  # 세션용 시크릿 키
CORS(app, supports_credentials=True)  # CORS 허용 (세션 포함)

generator = AIPolygonGenerator()
adjuster = NaturalLanguageAdjuster()
advisor = PolygonStrategyAdvisor()
logger = SearchLogger()
analytics = SearchAnalytics()
quality_monitor = SearchQualityMonitor()
es = Elasticsearch(['http://localhost:9200'])


def get_session_id():
    """세션 ID 가져오기 또는 생성"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']

@app.route('/api/generate-polygon', methods=['POST'])
def generate_polygon():
    """검색어로 동적 폴리곤 생성 + 전략 제안"""
    session_id = get_session_id()
    data = request.json
    query = data.get('query', '')

    if not query:
        return jsonify({'error': '검색어가 필요합니다'}), 400

    try:
        result = generator.generate_dynamic_polygon(query)

        if not result:
            # 실패 로그
            logger.log_polygon_generation(
                session_id=session_id,
                search_query=query,
                polygon_coords_count=0,
                success=False,
                error_message='폴리곤 생성 실패'
            )
            return jsonify({'error': '폴리곤 생성 실패'}), 500

        # 전략 제안 추가
        polygon = result['polygon']
        strategies = advisor.suggest_strategies(polygon, query)
        characteristics = advisor.analyze_area(polygon, query)

        result['strategies'] = strategies
        result['area_characteristics'] = characteristics

        # 성공 로그
        logger.log_polygon_generation(
            session_id=session_id,
            search_query=query,
            polygon_coords_count=len(polygon['coordinates'][0]),
            area_characteristics=characteristics,
            success=True
        )

        return jsonify(result)

    except Exception as e:
        # 에러 로그
        logger.log_polygon_generation(
            session_id=session_id,
            search_query=query,
            polygon_coords_count=0,
            success=False,
            error_message=str(e)
        )
        return jsonify({'error': str(e)}), 500

@app.route('/api/adjust-polygon', methods=['POST'])
def adjust_polygon_route():
    """자연어 명령으로 폴리곤 조정"""
    session_id = get_session_id()
    data = request.json
    polygon = data.get('polygon')
    command = data.get('command', '')

    if not polygon or not command:
        return jsonify({'error': 'polygon과 command가 필요합니다'}), 400

    try:
        # adjust_polygon returns (polygon, selected_hotel_names)
        adjusted, selected_hotel_names = adjuster.adjust_polygon(polygon, command)

        # POI 타입 추출
        poi_type = None
        if '지하철' in command or '역' in command:
            poi_type = 'transit'
        elif '관광' in command or '명소' in command:
            poi_type = 'tourism'
        elif '음식' in command or '식당' in command:
            poi_type = 'restaurant'

        # 성공 로그
        logger.log_polygon_adjustment(
            session_id=session_id,
            adjustment_command=command,
            polygon_coords_count=len(adjusted['coordinates'][0]),
            poi_type=poi_type,
            success=True
        )

        return jsonify({
            'command': command,
            'original': polygon,
            'adjusted': adjusted,
            'selected_hotel_names': selected_hotel_names
        })

    except Exception as e:
        # 에러 로그
        logger.log_polygon_adjustment(
            session_id=session_id,
            adjustment_command=command,
            polygon_coords_count=0,
            success=False,
            error_message=str(e)
        )
        return jsonify({'error': str(e)}), 500

@app.route('/api/search-hotels', methods=['POST'])
def search_hotels():
    """폴리곤 내 호텔 검색"""
    session_id = get_session_id()
    data = request.json
    polygon = data.get('polygon')
    selected_hotel_names = data.get('selected_hotel_names', [])  # POI 기반 조정시 필터링용

    if not polygon:
        return jsonify({'error': 'polygon이 필요합니다'}), 400

    coords = polygon['coordinates'][0]
    points = [{'lat': c[1], 'lon': c[0]} for c in coords]

    try:
        response = es.search(
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
                'size': 500
            }
        )

        hotels = [hit['_source'] for hit in response['hits']['hits']]
        original_count = len(hotels)

        # selected_hotel_names가 있으면 해당 호텔만 필터링
        if selected_hotel_names:
            hotels = [h for h in hotels if h['name'] in selected_hotel_names]

        # POI 타입 추출 (selected_hotel_names가 있으면 POI 기반 검색)
        poi_type = None
        if selected_hotel_names:
            # 세션에서 마지막 조정 명령 정보 가져오기 (간단히 추정)
            poi_type = 'poi_based'

        # 성공 로그 (호텔 정보 포함하여 품질 지표 계산)
        logger.log_hotel_search(
            session_id=session_id,
            hotel_count=original_count,
            selected_hotel_count=len(hotels) if selected_hotel_names else None,
            search_time_ms=response['took'],
            hotels=hotels,  # 호텔 목록 전달
            poi_type=poi_type,
            success=True
        )

        return jsonify({
            'count': len(hotels),
            'hotels': hotels,
            'took': response['took']
        })

    except Exception as e:
        # 에러 로그
        logger.log_hotel_search(
            session_id=session_id,
            hotel_count=0,
            selected_hotel_count=0,
            search_time_ms=0,
            success=False,
            error_message=str(e)
        )
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


@app.route('/api/reindex', methods=['POST'])
def reindex_hotels():
    """호텔 데이터 재인덱싱"""
    try:
        # 인덱싱 스크립트 경로
        indexing_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../indexing'))
        indexer_script = os.path.join(indexing_dir, 'elasticsearch_indexer.py')

        # 재인덱싱 실행
        result = subprocess.run(
            ['python3', indexer_script],
            cwd=indexing_dir,
            capture_output=True,
            text=True,
            timeout=300  # 5분 타임아웃
        )

        if result.returncode == 0:
            return jsonify({
                'status': 'success',
                'message': '재인덱싱 완료',
                'output': result.stdout
            })
        else:
            return jsonify({
                'status': 'error',
                'message': '재인덱싱 실패',
                'error': result.stderr
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({
            'status': 'error',
            'message': '재인덱싱 타임아웃 (5분 초과)'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# ============================================
# 검색 분석 API
# ============================================

@app.route('/api/analytics/popular-searches', methods=['GET'])
def get_popular_searches():
    """인기 검색어 조회"""
    try:
        limit = int(request.args.get('limit', 10))
        days = int(request.args.get('days', 7))

        results = analytics.get_popular_searches(limit=limit, days=days)

        return jsonify({
            'period_days': days,
            'popular_searches': results
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/popular-adjustments', methods=['GET'])
def get_popular_adjustments():
    """인기 조정 명령어 조회"""
    try:
        limit = int(request.args.get('limit', 10))
        days = int(request.args.get('days', 7))

        results = analytics.get_popular_adjustments(limit=limit, days=days)

        return jsonify({
            'period_days': days,
            'popular_adjustments': results
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/failure-rate', methods=['GET'])
def get_failure_rate():
    """검색 실패율 조회"""
    try:
        days = int(request.args.get('days', 7))

        results = analytics.get_failure_rate(days=days)

        return jsonify({
            'period_days': days,
            'failure_stats': results
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/search-statistics', methods=['GET'])
def get_search_statistics():
    """검색 통계 조회"""
    try:
        days = int(request.args.get('days', 7))

        results = analytics.get_search_statistics(days=days)

        return jsonify({
            'period_days': days,
            'statistics': results
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/hourly-trend', methods=['GET'])
def get_hourly_trend():
    """시간대별 검색 추이"""
    try:
        days = int(request.args.get('days', 7))

        results = analytics.get_hourly_search_trend(days=days)

        return jsonify({
            'period_days': days,
            'trend': results
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/dashboard', methods=['GET'])
def get_analytics_dashboard():
    """통합 분석 대시보드 데이터"""
    try:
        days = int(request.args.get('days', 7))

        # 모든 통계 한번에 조회
        dashboard = {
            'period_days': days,
            'popular_searches': analytics.get_popular_searches(limit=5, days=days),
            'popular_adjustments': analytics.get_popular_adjustments(limit=5, days=days),
            'failure_stats': analytics.get_failure_rate(days=days),
            'search_statistics': analytics.get_search_statistics(days=days),
            'hourly_trend': analytics.get_hourly_search_trend(days=days)
        }

        return jsonify(dashboard)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# 검색 품질 모니터링 API
# ============================================

@app.route('/api/quality/current', methods=['GET'])
def get_current_quality():
    """현재 검색 품질 상태"""
    try:
        hours = int(request.args.get('hours', 24))
        stats = quality_monitor.get_search_quality_stats(hours=hours)
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/quality/comparison', methods=['GET'])
def get_quality_comparison():
    """이전 기간 대비 품질 변화"""
    try:
        hours = int(request.args.get('hours', 24))
        comparison = quality_monitor.compare_with_previous_period(current_hours=hours)
        return jsonify(comparison)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/quality/low-quality-searches', methods=['GET'])
def get_low_quality_searches():
    """저품질 검색 결과 목록"""
    try:
        hours = int(request.args.get('hours', 24))
        limit = int(request.args.get('limit', 10))
        searches = quality_monitor.get_low_quality_searches(hours=hours, limit=limit)
        return jsonify({
            'period_hours': hours,
            'low_quality_searches': searches
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/quality/thresholds', methods=['GET', 'PUT'])
def manage_quality_thresholds():
    """품질 임계값 조회/변경"""
    try:
        if request.method == 'GET':
            return jsonify(quality_monitor.thresholds)

        elif request.method == 'PUT':
            new_thresholds = request.json
            quality_monitor.update_thresholds(new_thresholds)
            return jsonify({
                'message': '임계값 업데이트 완료',
                'thresholds': quality_monitor.thresholds
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/quality/dashboard', methods=['GET'])
def get_quality_dashboard():
    """품질 모니터링 통합 대시보드"""
    try:
        hours = int(request.args.get('hours', 24))

        dashboard = {
            'current_quality': quality_monitor.get_search_quality_stats(hours=hours),
            'comparison': quality_monitor.compare_with_previous_period(current_hours=hours),
            'low_quality_searches': quality_monitor.get_low_quality_searches(hours=hours, limit=5),
            'thresholds': quality_monitor.thresholds
        }

        return jsonify(dashboard)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("🚀 AI 폴리곤 API 서버 시작...")
    print("   http://localhost:5001")
    print("   📊 분석 대시보드: http://localhost:5001/api/analytics/dashboard")
    print("   ⭐ 품질 대시보드: http://localhost:5001/api/quality/dashboard")
    app.run(host='0.0.0.0', port=5001, debug=False)
