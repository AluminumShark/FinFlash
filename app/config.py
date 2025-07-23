"""Flask application configuration"""
import os
from datetime import timedelta
from config.config_loader import get_config, load_config

# Load configuration based on environment
config_data = load_config()
config_loader = get_config()

class Config:
    """Base configuration"""
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', config_loader.get('app.secret_key', 'dev-secret-key-change-in-production'))
    DEBUG = config_loader.get('app.debug', False)
    TESTING = config_loader.get('app.testing', False)
    
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL', config_loader.get('database.url', 'sqlite:///financial_news.db'))
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_POOL_SIZE = config_loader.get('database.pool_size', 10)
    SQLALCHEMY_POOL_TIMEOUT = config_loader.get('database.pool_timeout', 30)
    SQLALCHEMY_POOL_RECYCLE = config_loader.get('database.pool_recycle', 3600)
    SQLALCHEMY_ECHO = config_loader.get('database.echo', False)
    
    # Redis
    REDIS_URL = os.getenv('REDIS_URL', config_loader.get('redis.url', 'redis://localhost:6379/0'))
    REDIS_DECODE_RESPONSES = config_loader.get('redis.decode_responses', True)
    REDIS_SOCKET_TIMEOUT = config_loader.get('redis.socket_timeout', 5)
    REDIS_HEALTH_CHECK_INTERVAL = config_loader.get('redis.health_check_interval', 30)
    
    # API Keys
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o')
    OPENAI_TEMPERATURE = float(os.getenv('OPENAI_TEMPERATURE', '0.7'))
    OPENAI_MAX_TOKENS = int(os.getenv('OPENAI_MAX_TOKENS', '4000'))
    
    EXA_API_KEY = os.getenv('EXA_API_KEY')
    EXA_TIMEOUT = int(os.getenv('EXA_TIMEOUT', '30'))
    
    # Rate Limiting
    RATELIMIT_ENABLED = config_loader.get('rate_limiting.enabled', True)
    RATELIMIT_STORAGE_URL = config_loader.get('rate_limiting.storage_backend', 'redis') == 'redis' and REDIS_URL or 'memory://'
    RATELIMIT_DEFAULT = config_loader.get('rate_limiting.default_limits', ["100 per hour"])[0]
    RATELIMIT_KEY_PREFIX = config_loader.get('rate_limiting.key_prefix', 'finflash_rate_limit')
    
    # Session
    SESSION_TYPE = 'redis'
    SESSION_REDIS_URL = REDIS_URL
    SESSION_PERMANENT = False
    PERMANENT_SESSION_LIFETIME = timedelta(seconds=config_loader.get('security.session_timeout', 3600))
    
    # File Upload
    UPLOAD_FOLDER = config_loader.get('file_upload.folder', 'app/uploads')
    MAX_CONTENT_LENGTH = config_loader.get('file_upload.max_content_length', 16 * 1024 * 1024)  # 16MB
    ALLOWED_EXTENSIONS = set(config_loader.get('agents.speech.supported_formats', 
                                               ['mp3', 'mp4', 'mpeg', 'mpga', 'm4a', 'wav', 'webm']))
    
    # CORS
    CORS_ENABLED = config_loader.get('security.cors.enabled', True)
    CORS_ORIGINS = config_loader.get('security.cors.origins', ['http://localhost:3000', 'http://localhost:5000'])
    
    # Application settings from YAML
    APP_NAME = config_loader.get('app.name', 'FinFlash')
    APP_VERSION = config_loader.get('app.version', '1.0.0')
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', config_loader.get('logging.root.level', 'INFO'))
    
    # Agent Configuration
    AGENT_TIMEOUT = config_loader.get('agents.timeout', 300)
    MAX_CONCURRENT_ANALYSES = config_loader.get('orchestrator.max_concurrent_analyses', 5)
    
    # Features
    ENABLE_WEBSOCKET = config_loader.get('features.enable_websocket', True)
    ENABLE_EMAIL_NOTIFICATIONS = config_loader.get('features.enable_email_notifications', False)
    ENABLE_EXPORT_API = config_loader.get('features.enable_export_api', True)
    ENABLE_BULK_ANALYSIS = config_loader.get('features.enable_bulk_analysis', True)


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SQLALCHEMY_ECHO = False


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

def get_config(config_name=None):
    """Get configuration class based on environment"""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')
    return config.get(config_name, DevelopmentConfig) 