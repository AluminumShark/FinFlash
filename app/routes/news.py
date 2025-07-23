"""News management API routes"""
from flask import Blueprint, request, jsonify, current_app
import logging
from datetime import datetime, timedelta
from sqlalchemy import desc

from core.database import News, get_db_manager

# Create blueprint
news_bp = Blueprint('news', __name__)
logger = logging.getLogger(__name__)

@news_bp.route('/', methods=['GET'])
def get_news_list():
    """
    Get list of news articles
    
    Query params:
    - page: Page number (default: 1)
    - per_page: Items per page (default: 20, max: 100)
    - days_back: Number of days to look back (default: 7)
    - processed: Filter by processed status (true/false/all)
    """
    try:
        # Get query parameters
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 20)), 100)
        days_back = int(request.args.get('days_back', 7))
        processed_filter = request.args.get('processed', 'all')
        
        # Get database session
        db = get_db_manager().get_session()
        
        # Build query
        query = db.query(News)
        
        # Filter by date
        if days_back > 0:
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)
            query = query.filter(News.collected_date >= cutoff_date)
        
        # Filter by processed status
        if processed_filter == 'true':
            query = query.filter(News.processed == True)
        elif processed_filter == 'false':
            query = query.filter(News.processed == False)
        
        # Order by date
        query = query.order_by(desc(News.collected_date))
        
        # Paginate
        total = query.count()
        news_items = query.offset((page - 1) * per_page).limit(per_page).all()
        
        # Convert to dict
        news_list = [news.to_dict() for news in news_items]
        
        db.close()
        
        return jsonify({
            'news': news_list,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting news list: {str(e)}")
        return jsonify({'error': str(e)}), 500

@news_bp.route('/<news_id>', methods=['GET'])
def get_news_detail(news_id):
    """Get single news article with all analysis results"""
    try:
        db = get_db_manager().get_session()
        
        # Get news item
        news = db.query(News).filter_by(id=news_id).first()
        if not news:
            db.close()
            return jsonify({'error': 'News not found'}), 404
        
        # Get analysis results
        from core.database import AnalysisResult
        analyses = db.query(AnalysisResult).filter_by(news_id=news_id).all()
        
        # Build response
        result = news.to_dict()
        result['analyses'] = {}
        
        for analysis in analyses:
            result['analyses'][analysis.agent_type] = {
                'result': analysis.result,
                'confidence': analysis.confidence,
                'analysis_date': analysis.analysis_date.isoformat(),
                'processing_time': analysis.processing_time
            }
        
        db.close()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting news detail: {str(e)}")
        return jsonify({'error': str(e)}), 500

@news_bp.route('/<news_id>', methods=['DELETE'])
def delete_news(news_id):
    """Delete news article and its analysis results"""
    try:
        db = get_db_manager().get_session()
        
        # Check if news exists
        news = db.query(News).filter_by(id=news_id).first()
        if not news:
            db.close()
            return jsonify({'error': 'News not found'}), 404
        
        # Delete analysis results first
        from core.database import AnalysisResult
        db.query(AnalysisResult).filter_by(news_id=news_id).delete()
        
        # Delete news
        db.delete(news)
        db.commit()
        db.close()
        
        return jsonify({'message': 'News deleted successfully'})
        
    except Exception as e:
        db.rollback()
        db.close()
        logger.error(f"Error deleting news: {str(e)}")
        return jsonify({'error': str(e)}), 500

@news_bp.route('/search', methods=['GET'])
def search_news():
    """
    Search news by keywords
    
    Query params:
    - q: Search query
    - in: Search in (title/content/all)
    """
    try:
        query_text = request.args.get('q', '')
        search_in = request.args.get('in', 'all')
        
        if not query_text:
            return jsonify({'error': 'Query parameter q is required'}), 400
        
        db = get_db_manager().get_session()
        
        # Build search query
        query = db.query(News)
        
        if search_in == 'title':
            query = query.filter(News.title.contains(query_text))
        elif search_in == 'content':
            query = query.filter(News.content.contains(query_text))
        else:  # all
            query = query.filter(
                db.or_(
                    News.title.contains(query_text),
                    News.content.contains(query_text)
                )
            )
        
        # Get results
        results = query.order_by(desc(News.collected_date)).limit(50).all()
        
        db.close()
        
        return jsonify({
            'query': query_text,
            'results': [news.to_dict() for news in results],
            'count': len(results)
        })
        
    except Exception as e:
        logger.error(f"Error searching news: {str(e)}")
        return jsonify({'error': str(e)}), 500 