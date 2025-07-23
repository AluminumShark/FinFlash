"""Batch processing API routes"""
from flask import Blueprint, request, jsonify, current_app
import logging
from datetime import datetime
import asyncio

from core.database import BatchJob, get_db_manager
from agents.orchestrator import ProcessingMode

# Create blueprint
batch_bp = Blueprint('batch', __name__)
logger = logging.getLogger(__name__)

@batch_bp.route('/jobs', methods=['GET'])
def get_batch_jobs():
    """Get list of batch jobs"""
    try:
        db = get_db_manager().get_session()
        
        # Get filter parameters
        status = request.args.get('status')
        job_type = request.args.get('type')
        limit = int(request.args.get('limit', 50))
        
        # Build query
        query = db.query(BatchJob)
        
        if status:
            query = query.filter_by(status=status)
        if job_type:
            query = query.filter_by(job_type=job_type)
        
        # Order by created date descending
        jobs = query.order_by(BatchJob.created_date.desc()).limit(limit).all()
        
        db.close()
        
        return jsonify({
            'jobs': [job.to_dict() for job in jobs],
            'count': len(jobs)
        })
        
    except Exception as e:
        logger.error(f"Error getting batch jobs: {str(e)}")
        return jsonify({'error': str(e)}), 500

@batch_bp.route('/jobs/<job_id>', methods=['GET'])
def get_batch_job_detail(job_id):
    """Get single batch job details"""
    try:
        db = get_db_manager().get_session()
        
        job = db.query(BatchJob).filter_by(id=job_id).first()
        if not job:
            db.close()
            return jsonify({'error': 'Job not found'}), 404
        
        result = job.to_dict()
        
        # Calculate duration if completed
        if job.started_date and job.completed_date:
            duration = (job.completed_date - job.started_date).total_seconds()
            result['duration_seconds'] = duration
        
        # Calculate success rate
        if job.processed_items > 0:
            success_rate = ((job.processed_items - job.failed_items) / job.processed_items) * 100
            result['success_rate'] = round(success_rate, 2)
        
        db.close()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting batch job detail: {str(e)}")
        return jsonify({'error': str(e)}), 500

@batch_bp.route('/crawl', methods=['POST'])
async def start_news_crawl():
    """
    Start batch news crawling job
    
    Request JSON:
    {
        "keywords": ["keyword1", "keyword2"],
        "days_back": 7,
        "num_results": 50,
        "auto_analyze": true
    }
    """
    try:
        data = request.get_json()
        keywords = data.get('keywords', ['financial news', 'stock market'])
        days_back = data.get('days_back', 7)
        num_results = data.get('num_results', 50)
        auto_analyze = data.get('auto_analyze', True)
        
        # Get research agent
        orchestrator = current_app.orchestrator
        if not orchestrator or not orchestrator.research_agent:
            return jsonify({'error': 'Research agent not available'}), 503
        
        # Create batch job
        db = get_db_manager().get_session()
        batch_job = BatchJob(
            job_type='news_crawl',
            status='running',
            started_date=datetime.utcnow(),
            total_items=num_results,
            metadata={
                'keywords': keywords,
                'days_back': days_back,
                'auto_analyze': auto_analyze
            }
        )
        db.add(batch_job)
        db.commit()
        job_id = batch_job.id
        db.close()
        
        # Start crawling
        try:
            # Build search query from keywords
            query = ' OR '.join([f'"{kw}"' for kw in keywords])
            
            # Search for news
            result = await orchestrator.research_agent({
                'query': query,
                'days_back': days_back,
                'num_results': num_results,
                'save_to_db': True
            })
            
            articles = result['result']['articles']
            
            # Update job
            db = get_db_manager().get_session()
            job = db.query(BatchJob).filter_by(id=job_id).first()
            job.processed_items = len(articles)
            job.status = 'completed'
            job.completed_date = datetime.utcnow()
            db.commit()
            db.close()
            
            # Auto-analyze if requested
            if auto_analyze and articles:
                # Start analysis in background
                asyncio.create_task(_analyze_crawled_news(articles, job_id))
            
            return jsonify({
                'job_id': job_id,
                'status': 'completed',
                'articles_found': len(articles),
                'auto_analyze': auto_analyze
            })
            
        except Exception as e:
            # Mark job as failed
            db = get_db_manager().get_session()
            job = db.query(BatchJob).filter_by(id=job_id).first()
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_date = datetime.utcnow()
            db.commit()
            db.close()
            raise
            
    except Exception as e:
        logger.error(f"Error starting news crawl: {str(e)}")
        return jsonify({'error': str(e)}), 500

async def _analyze_crawled_news(articles, parent_job_id):
    """Background task to analyze crawled news"""
    orchestrator = current_app.orchestrator
    
    # Create analysis batch job
    db = get_db_manager().get_session()
    batch_job = BatchJob(
        job_type='batch_analysis',
        status='running',
        started_date=datetime.utcnow(),
        total_items=len(articles),
        metadata={'parent_job_id': parent_job_id}
    )
    db.add(batch_job)
    db.commit()
    job_id = batch_job.id
    db.close()
    
    processed = 0
    failed = 0
    
    for article in articles:
        try:
            await orchestrator.process_text_news(
                news_content=article['content'],
                news_title=article['title'],
                news_id=article['id'],
                mode=ProcessingMode.PARALLEL,
                save_to_db=True
            )
            processed += 1
        except Exception as e:
            logger.error(f"Error analyzing article {article['id']}: {str(e)}")
            failed += 1
        
        # Update progress
        db = get_db_manager().get_session()
        job = db.query(BatchJob).filter_by(id=job_id).first()
        job.processed_items = processed
        job.failed_items = failed
        db.commit()
        db.close()
    
    # Mark as completed
    db = get_db_manager().get_session()
    job = db.query(BatchJob).filter_by(id=job_id).first()
    job.status = 'completed'
    job.completed_date = datetime.utcnow()
    db.commit()
    db.close()

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

# Apply async wrapper
start_news_crawl = async_route(start_news_crawl) 