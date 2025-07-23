"""Report generation API routes"""
from flask import Blueprint, request, jsonify, current_app
import logging
from datetime import datetime, timedelta
import asyncio

from core.database import AnalysisResult, get_db_manager

# Create blueprint
reports_bp = Blueprint('reports', __name__)
logger = logging.getLogger(__name__)

@reports_bp.route('/generate', methods=['POST'])
async def generate_report():
    """
    Generate comprehensive report
    
    Request JSON:
    {
        "time_period_hours": 24,
        "report_type": "executive|detailed|technical|investor|risk",
        "news_ids": ["id1", "id2"]  // Optional specific news
    }
    """
    try:
        data = request.get_json()
        time_period_hours = data.get('time_period_hours', 24)
        report_type = data.get('report_type', 'executive')
        news_ids = data.get('news_ids', [])
        
        # Get summary agent
        summary_agent = getattr(current_app, 'summary_agent', None)
        if not summary_agent:
            return jsonify({'error': 'Summary agent not available'}), 503
        
        # Generate report based on whether specific news IDs are provided
        if news_ids:
            # Generate custom report for specific news
            result = await summary_agent.generate_custom_report(
                news_ids=news_ids,
                report_type=report_type
            )
        else:
            # Generate batch report for time period
            result = await summary_agent.generate_batch_report(
                time_period_hours=time_period_hours,
                report_type=report_type
            )
        
        return jsonify({
            'success': True,
            'report': result
        })
        
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}")
        return jsonify({'error': str(e)}), 500

@reports_bp.route('/market-sentiment', methods=['GET'])
async def get_market_sentiment():
    """
    Get aggregated market sentiment
    
    Query params:
    - hours: Time period in hours (default: 24)
    """
    try:
        hours = int(request.args.get('hours', 24))
        
        # Get sentiment agent
        orchestrator = current_app.orchestrator
        if not orchestrator or not orchestrator.sentiment_agent:
            return jsonify({'error': 'Sentiment agent not available'}), 503
        
        # Get market sentiment summary
        result = await orchestrator.sentiment_agent.get_market_sentiment_summary(
            time_period_hours=hours
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting market sentiment: {str(e)}")
        return jsonify({'error': str(e)}), 500

@reports_bp.route('/risk-alerts', methods=['GET'])
async def get_risk_alerts():
    """
    Get high-risk alerts
    
    Query params:
    - hours: Time period in hours (default: 24)
    - threshold: Risk score threshold (default: 70)
    """
    try:
        hours = int(request.args.get('hours', 24))
        threshold = int(request.args.get('threshold', 70))
        
        # Get risk agent
        orchestrator = current_app.orchestrator
        if not orchestrator or not orchestrator.risk_agent:
            return jsonify({'error': 'Risk agent not available'}), 503
        
        # Get risk alerts
        alerts = await orchestrator.risk_agent.get_risk_alerts(
            risk_threshold=threshold,
            time_period_hours=hours
        )
        
        return jsonify({
            'alerts': alerts,
            'count': len(alerts),
            'threshold': threshold,
            'time_period_hours': hours
        })
        
    except Exception as e:
        logger.error(f"Error getting risk alerts: {str(e)}")
        return jsonify({'error': str(e)}), 500

@reports_bp.route('/entity-summary', methods=['GET'])
async def get_entity_summary():
    """
    Get entity frequency summary
    
    Query params:
    - type: Entity type (companies|persons|locations)
    - hours: Time period in hours (default: 24)
    """
    try:
        entity_type = request.args.get('type', 'companies')
        hours = int(request.args.get('hours', 24))
        
        # Validate entity type
        valid_types = ['companies', 'persons', 'locations']
        if entity_type not in valid_types:
            return jsonify({
                'error': f'Invalid entity type. Must be one of: {", ".join(valid_types)}'
            }), 400
        
        # Get extraction agent
        orchestrator = current_app.orchestrator
        if not orchestrator or not orchestrator.extraction_agent:
            return jsonify({'error': 'Extraction agent not available'}), 503
        
        # Get entity summary
        result = await orchestrator.extraction_agent.get_entity_summary(
            entity_type=entity_type,
            time_period_hours=hours
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting entity summary: {str(e)}")
        return jsonify({'error': str(e)}), 500

@reports_bp.route('/sector-risk', methods=['GET'])
async def get_sector_risk():
    """
    Get risk analysis by sector
    
    Query params:
    - hours: Time period in hours (default: 48)
    """
    try:
        hours = int(request.args.get('hours', 48))
        
        # Get risk agent
        orchestrator = current_app.orchestrator
        if not orchestrator or not orchestrator.risk_agent:
            return jsonify({'error': 'Risk agent not available'}), 503
        
        # Get sector risk summary
        result = await orchestrator.risk_agent.get_sector_risk_summary(
            time_period_hours=hours
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting sector risk: {str(e)}")
        return jsonify({'error': str(e)}), 500

@reports_bp.route('/event-timeline', methods=['GET'])
async def get_event_timeline():
    """
    Get timeline of events
    
    Query params:
    - hours: Time period in hours (default: 48)
    """
    try:
        hours = int(request.args.get('hours', 48))
        
        # Get extraction agent
        orchestrator = current_app.orchestrator
        if not orchestrator or not orchestrator.extraction_agent:
            return jsonify({'error': 'Extraction agent not available'}), 503
        
        # Get event timeline
        events = await orchestrator.extraction_agent.get_event_timeline(
            time_period_hours=hours
        )
        
        return jsonify({
            'events': events,
            'count': len(events),
            'time_period_hours': hours
        })
        
    except Exception as e:
        logger.error(f"Error getting event timeline: {str(e)}")
        return jsonify({'error': str(e)}), 500

@reports_bp.route('/daily', methods=['GET'])
def get_daily_reports():
    """Get list of daily reports"""
    try:
        db = get_db_manager().get_session()
        
        # Query for summary reports from the last 30 days
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        reports = db.query(AnalysisResult).filter(
            AnalysisResult.agent_type == 'summary',
            AnalysisResult.analysis_date >= cutoff_date
        ).order_by(AnalysisResult.analysis_date.desc()).all()
        
        report_list = []
        for report in reports:
            report_data = {
                'id': report.id,
                'date': report.analysis_date.isoformat(),
                'type': report.result.get('report', {}).get('report_metadata', {}).get('report_type', 'unknown'),
                'analyses_count': report.result.get('analyses_count', 0),
                'confidence': report.confidence
            }
            report_list.append(report_data)
        
        db.close()
        
        return jsonify({
            'reports': report_list,
            'count': len(report_list)
        })
        
    except Exception as e:
        logger.error(f"Error getting daily reports: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Async route handler wrapper
def async_route(f):
    """Decorator to handle async routes"""
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(f(*args, **kwargs))
        finally:
            loop.close()
    wrapper.__name__ = f.__name__
    return wrapper

# Apply async wrapper to async routes
generate_report = async_route(generate_report)
get_market_sentiment = async_route(get_market_sentiment)
get_risk_alerts = async_route(get_risk_alerts)
get_entity_summary = async_route(get_entity_summary)
get_sector_risk = async_route(get_sector_risk)
get_event_timeline = async_route(get_event_timeline) 