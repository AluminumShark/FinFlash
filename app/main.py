"""Main Flask application"""
import os
import logging
from flask import Flask, render_template, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import redis
from datetime import datetime

from app.config import get_config
from core.database import get_db_manager
from services.openaiService import OpenAIService
from services.exaService import ExaService
from agents.researchAgent import FinancialResearchAgent
from agents.speechAgent import SpeechAgent
from agents.sentimentAgent import SentimentAnalysisAgent
from agents.extractionAgent import ExtractionAgent
from agents.riskAgent import RiskAssessmentAgent
from agents.summaryAgent import SummaryAgent
from agents.orchestrator import Orchestrator

# Initialize Flask app
app = Flask(__name__)
config = get_config()
app.config.from_object(config)

# Setup logging
log_level = getattr(config, 'LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize extensions
cors_origins = getattr(config, 'CORS_ORIGINS', ['*'])
CORS(app, origins=cors_origins)
socketio = SocketIO(app, cors_allowed_origins=cors_origins)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri=config.REDIS_URL
)

# Initialize Redis
redis_client = redis.from_url(config.REDIS_URL)

# Create upload folder if it doesn't exist
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

# Initialize services and agents
openai_service = None
exa_service = None
orchestrator = None

def initialize_services():
    """Initialize AI services and agents"""
    global openai_service, exa_service, orchestrator
    
    try:
        # Initialize services
        logger.info("Initializing AI services...")
        
        openai_service = OpenAIService(
            api_key=config.OPENAI_API_KEY,
            model=getattr(config, 'OPENAI_MODEL', 'gpt-4o'),
            rate_limit=60  # Default rate limit
        )
        
        exa_service = ExaService(
            api_key=config.EXA_API_KEY,
            rate_limit=100  # Default rate limit
        )
        
        # Initialize agents
        logger.info("Initializing agents...")
        
        research_agent = FinancialResearchAgent(exa_service=exa_service)
        speech_agent = SpeechAgent(openai_service=openai_service)
        sentiment_agent = SentimentAnalysisAgent(openai_service=openai_service)
        extraction_agent = ExtractionAgent(openai_service=openai_service)
        risk_agent = RiskAssessmentAgent(openai_service=openai_service)
        summary_agent = SummaryAgent(openai_service=openai_service)
        
        # Initialize orchestrator
        orchestrator = Orchestrator(
            research_agent=research_agent,
            speech_agent=speech_agent,
            sentiment_agent=sentiment_agent,
            extraction_agent=extraction_agent,
            risk_agent=risk_agent,
            logger=logger
        )
        
        # Store orchestrator and summary agent on the app instance
        app.orchestrator = orchestrator
        app.summary_agent = summary_agent
        
        # Also store orchestrator in global variable for module-level access
        globals()['orchestrator'] = orchestrator
        
        logger.info("All services and agents initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {str(e)}")
        raise

# Initialize orchestrator as None first
app.orchestrator = None
app.summary_agent = None

# Initialize services on startup
with app.app_context():
    initialize_services()

# Error handlers
@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(429)
def ratelimit_handler(e):
    """Handle rate limit errors"""
    return jsonify({'error': 'Rate limit exceeded', 'message': str(e.description)}), 429

# Basic routes
@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        # Check database
        db = get_db_manager().get_session()
        db.execute('SELECT 1')
        db.close()
        db_status = 'healthy'
    except:
        db_status = 'unhealthy'
    
    # Check Redis
    try:
        redis_client.ping()
        redis_status = 'healthy'
    except:
        redis_status = 'unhealthy'
    
    # Check services
    services_status = {
        'openai': 'healthy' if openai_service else 'not initialized',
        'exa': 'healthy' if exa_service else 'not initialized',
        'orchestrator': 'healthy' if app.orchestrator else 'not initialized'
    }
    
    return jsonify({
        'status': 'healthy' if db_status == 'healthy' and redis_status == 'healthy' else 'degraded',
        'timestamp': datetime.utcnow().isoformat(),
        'components': {
            'database': db_status,
            'redis': redis_status,
            'services': services_status
        }
    })

@app.route('/stats')
def stats():
    """Get system statistics"""
    stats_data = {
        'timestamp': datetime.utcnow().isoformat(),
        'services': {},
        'orchestrator': {}
    }
    
    # Get service stats
    if openai_service:
        stats_data['services']['openai'] = openai_service.get_stats()
    
    if exa_service:
        stats_data['services']['exa'] = exa_service.get_stats()
    
    # Get orchestrator stats
    if app.orchestrator:
        stats_data['orchestrator'] = app.orchestrator.get_stats()
    
    return jsonify(stats_data)

# Import and register blueprints
from app.routes.news import news_bp
from app.routes.analysis import analysis_bp
from app.routes.batch import batch_bp
from app.routes.reports import reports_bp

app.register_blueprint(news_bp, url_prefix='/api/news')
app.register_blueprint(analysis_bp, url_prefix='/api/analysis')
app.register_blueprint(batch_bp, url_prefix='/api/batch')
app.register_blueprint(reports_bp, url_prefix='/api/reports')

# WebSocket events for real-time updates
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info(f"Client connected")
    socketio.emit('connected', {'message': 'Connected to Financial News Analysis System'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected")

@socketio.on('analysis_progress')
def handle_analysis_progress(data):
    """Send analysis progress updates"""
    socketio.emit('progress_update', data)

if __name__ == '__main__':
    # Run the application
    socketio.run(
        app,
        host='0.0.0.0',
        port=5000,
        debug=config.DEBUG
    ) 