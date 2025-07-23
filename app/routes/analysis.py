"""Analysis API routes"""
from flask import Blueprint, request, jsonify, current_app
from flask_limiter.util import get_remote_address
import logging
import asyncio
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import yt_dlp
import tempfile

from agents.orchestrator import ProcessingMode

# Create blueprint
analysis_bp = Blueprint('analysis', __name__)
logger = logging.getLogger(__name__)

# Note: Limiter is applied via decorator, not from current_app

@analysis_bp.route('/text', methods=['POST'])
async def analyze_text():
    """
    Analyze text news content
    
    Request JSON:
    {
        "content": "news content",
        "title": "optional title",
        "mode": "parallel|sequential|adaptive",
        "save_to_db": true
    }
    """
    try:
        data = request.get_json()
        
        # Validate input
        if not data or 'content' not in data:
            return jsonify({'error': 'Content is required'}), 400
        
        content = data['content']
        title = data.get('title', '')
        mode_str = data.get('mode', 'parallel')
        save_to_db = data.get('save_to_db', True)
        
        # Convert mode string to enum
        mode_map = {
            'parallel': ProcessingMode.PARALLEL,
            'sequential': ProcessingMode.SEQUENTIAL,
            'adaptive': ProcessingMode.ADAPTIVE
        }
        mode = mode_map.get(mode_str, ProcessingMode.PARALLEL)
        
        # Get orchestrator
        orchestrator = current_app.orchestrator
        if not orchestrator:
            return jsonify({'error': 'Analysis service not available'}), 503
        
        # Perform analysis
        logger.info(f"Starting text analysis with mode: {mode}")
        result = await orchestrator.process_text_news(
            news_content=content,
            news_title=title,
            mode=mode,
            save_to_db=save_to_db
        )
        
        return jsonify({
            'success': True,
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in text analysis: {str(e)}")
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/audio', methods=['POST'])
async def analyze_audio():
    """
    Analyze audio news file
    
    Request: multipart/form-data with audio file
    """
    try:
        # Check if file is present
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400
        
        file = request.files['audio']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate file extension
        allowed_extensions = current_app.config['ALLOWED_EXTENSIONS']
        if not any(file.filename.lower().endswith(ext) for ext in allowed_extensions):
            return jsonify({
                'error': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'
            }), 400
        
        # Save file
        filename = secure_filename(file.filename)
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Get processing mode
        mode_str = request.form.get('mode', 'sequential')
        mode_map = {
            'parallel': ProcessingMode.PARALLEL,
            'sequential': ProcessingMode.SEQUENTIAL,
            'adaptive': ProcessingMode.ADAPTIVE
        }
        mode = mode_map.get(mode_str, ProcessingMode.SEQUENTIAL)
        
        # Get orchestrator
        orchestrator = current_app.orchestrator
        if not orchestrator:
            return jsonify({'error': 'Analysis service not available'}), 503
        
        # Perform analysis
        logger.info(f"Starting audio analysis for file: {filename}")
        result = await orchestrator.process_audio_news(
            audio_file_path=filepath,
            mode=mode,
            save_to_db=True
        )
        
        # Clean up file after processing
        try:
            os.remove(filepath)
        except:
            logger.warning(f"Failed to clean up audio file: {filepath}")
        
        return jsonify({
            'success': True,
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in audio analysis: {str(e)}")
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/search', methods=['POST'])
async def search_and_analyze():
    """
    Search for news and analyze results
    
    Request JSON:
    {
        "query": "search query",
        "num_results": 10,
        "days_back": 7,
        "mode": "parallel|sequential|adaptive"
    }
    """
    try:
        data = request.get_json()
        
        # Validate input
        if not data or 'query' not in data:
            return jsonify({'error': 'Query is required'}), 400
        
        query = data['query']
        num_results = min(data.get('num_results', 10), 50)  # Cap at 50
        days_back = min(data.get('days_back', 7), 30)  # Cap at 30 days
        mode_str = data.get('mode', 'parallel')
        
        # Convert mode
        mode_map = {
            'parallel': ProcessingMode.PARALLEL,
            'sequential': ProcessingMode.SEQUENTIAL,
            'adaptive': ProcessingMode.ADAPTIVE
        }
        mode = mode_map.get(mode_str, ProcessingMode.PARALLEL)
        
        # Get orchestrator
        orchestrator = current_app.orchestrator
        if not orchestrator:
            return jsonify({'error': 'Analysis service not available'}), 503
        
        # Perform search and analysis
        logger.info(f"Starting search and analysis for query: {query}")
        result = await orchestrator.process_search_and_analyze(
            search_query=query,
            num_results=num_results,
            days_back=days_back,
            mode=mode
        )
        
        return jsonify({
            'success': True,
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in search and analysis: {str(e)}")
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/youtube', methods=['POST'])
async def analyze_youtube():
    """
    Download and analyze YouTube video audio
    
    Request JSON:
    {
        "url": "youtube_url",
        "mode": "parallel|sequential|adaptive"
    }
    """
    try:
        data = request.get_json()
        
        # Validate input
        if not data or 'url' not in data:
            return jsonify({'error': 'YouTube URL is required'}), 400
        
        youtube_url = data['url']
        mode_str = data.get('mode', 'sequential')
        
        # Convert mode
        mode_map = {
            'parallel': ProcessingMode.PARALLEL,
            'sequential': ProcessingMode.SEQUENTIAL,
            'adaptive': ProcessingMode.ADAPTIVE
        }
        mode = mode_map.get(mode_str, ProcessingMode.SEQUENTIAL)
        
        # Create temporary directory for download
        with tempfile.TemporaryDirectory() as temp_dir:
            # Configure yt-dlp options
            ydl_opts = {
                'format': 'bestaudio/best',
                'extractaudio': True,
                'audioformat': 'mp3',
                'outtmpl': os.path.join(temp_dir, 'audio.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
            
            logger.info(f"Downloading audio from YouTube: {youtube_url}")
            
            # Download audio
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(youtube_url, download=True)
                    video_title = info.get('title', 'Unknown')
                    video_duration = info.get('duration', 0)
                    
                    # Check duration (limit to 30 minutes)
                    if video_duration > 1800:
                        return jsonify({
                            'error': 'Video too long. Maximum duration is 30 minutes.'
                        }), 400
            except Exception as e:
                logger.error(f"YouTube download error: {str(e)}")
                return jsonify({'error': f'Failed to download YouTube video: {str(e)}'}), 500
            
            # Find the downloaded audio file
            audio_files = [f for f in os.listdir(temp_dir) if f.endswith('.mp3')]
            if not audio_files:
                return jsonify({'error': 'Failed to extract audio from YouTube video'}), 500
            
            audio_path = os.path.join(temp_dir, audio_files[0])
            
            # Check file size
            file_size = os.path.getsize(audio_path)
            if file_size > current_app.config['MAX_CONTENT_LENGTH']:
                return jsonify({
                    'error': f'Audio file too large: {file_size / (1024*1024):.1f}MB (max 16MB)'
                }), 400
            
            # Get orchestrator
            orchestrator = current_app.orchestrator
            if not orchestrator:
                return jsonify({'error': 'Analysis service not available'}), 503
            
            # Perform analysis
            logger.info(f"Starting YouTube audio analysis: {video_title}")
            result = await orchestrator.process_audio_news(
                audio_file_path=audio_path,
                mode=mode,
                save_to_db=True
            )
            
            # Add YouTube metadata
            result['youtube_metadata'] = {
                'title': video_title,
                'url': youtube_url,
                'duration_seconds': video_duration
            }
            
            return jsonify({
                'success': True,
                'result': result
            })
        
    except Exception as e:
        logger.error(f"Error in YouTube analysis: {str(e)}")
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get status of analysis job"""
    # TODO: Implement job status tracking
    return jsonify({
        'job_id': job_id,
        'status': 'completed',
        'message': 'Job tracking not yet implemented'
    })

@analysis_bp.route('/agents', methods=['GET'])
def get_agent_status():
    """Get status of all agents"""
    orchestrator = current_app.orchestrator
    
    if not orchestrator:
        return jsonify({'error': 'Orchestrator not available'}), 503
    
    agents_status = {
        'research': bool(orchestrator.research_agent),
        'speech': bool(orchestrator.speech_agent),
        'sentiment': bool(orchestrator.sentiment_agent),
        'extraction': bool(orchestrator.extraction_agent),
        'risk': bool(orchestrator.risk_agent)
    }
    
    return jsonify({
        'agents': agents_status,
        'orchestrator_stats': orchestrator.get_stats()
    })

# Async route handler wrapper for Flask
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
analyze_text = async_route(analyze_text)
analyze_audio = async_route(analyze_audio)
search_and_analyze = async_route(search_and_analyze)
analyze_youtube = async_route(analyze_youtube) 