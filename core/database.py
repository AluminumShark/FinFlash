"""Database models and connection management"""
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
import uuid
import os
from typing import Optional

Base = declarative_base()

class News(Base):
    """News article model"""
    __tablename__ = 'news'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    source = Column(String(200))
    source_url = Column(String(500))
    author = Column(String(200))
    published_date = Column(DateTime)
    collected_date = Column(DateTime, default=datetime.utcnow)
    language = Column(String(10), default='zh-TW')
    news_type = Column(String(50))  # text, audio, video
    original_audio_path = Column(String(500))  # For audio news
    confidence_score = Column(Float, default=1.0)
    processed = Column(Boolean, default=False)
    additional_metadata = Column(JSON)  # Additional metadata
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'source': self.source,
            'source_url': self.source_url,
            'author': self.author,
            'published_date': self.published_date.isoformat() if self.published_date else None,
            'collected_date': self.collected_date.isoformat() if self.collected_date else None,
            'language': self.language,
            'news_type': self.news_type,
            'confidence_score': self.confidence_score,
            'processed': self.processed,
            'metadata': self.additional_metadata
        }

class AnalysisResult(Base):
    """Analysis results from agents"""
    __tablename__ = 'analysis_results'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    news_id = Column(String(36), nullable=False)
    agent_type = Column(String(50), nullable=False)  # sentiment, extraction, risk
    analysis_date = Column(DateTime, default=datetime.utcnow)
    result = Column(JSON, nullable=False)  # Agent-specific results
    confidence = Column(Float, default=1.0)
    processing_time = Column(Float)  # seconds
    model_used = Column(String(50))
    tokens_used = Column(Integer)
    error_message = Column(Text)
    
    def to_dict(self):
        return {
            'id': self.id,
            'news_id': self.news_id,
            'agent_type': self.agent_type,
            'analysis_date': self.analysis_date.isoformat() if self.analysis_date else None,
            'result': self.result,
            'confidence': self.confidence,
            'processing_time': self.processing_time,
            'model_used': self.model_used,
            'tokens_used': self.tokens_used,
            'error_message': self.error_message
        }

class BatchJob(Base):
    """Batch processing job records"""
    __tablename__ = 'batch_jobs'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_type = Column(String(50), nullable=False)  # crawl, analyze, report
    status = Column(String(20), default='pending')  # pending, running, completed, failed
    created_date = Column(DateTime, default=datetime.utcnow)
    started_date = Column(DateTime)
    completed_date = Column(DateTime)
    total_items = Column(Integer, default=0)
    processed_items = Column(Integer, default=0)
    failed_items = Column(Integer, default=0)
    error_message = Column(Text)
    additional_metadata = Column(JSON)
    
    def to_dict(self):
        return {
            'id': self.id,
            'job_type': self.job_type,
            'status': self.status,
            'created_date': self.created_date.isoformat() if self.created_date else None,
            'started_date': self.started_date.isoformat() if self.started_date else None,
            'completed_date': self.completed_date.isoformat() if self.completed_date else None,
            'total_items': self.total_items,
            'processed_items': self.processed_items,
            'failed_items': self.failed_items,
            'error_message': self.error_message,
            'metadata': self.additional_metadata
        }

class UserSession(Base):
    """User session tracking"""
    __tablename__ = 'user_sessions'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(100), unique=True, nullable=False)
    created_date = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    user_ip = Column(String(50))
    user_agent = Column(String(500))
    requests_count = Column(Integer, default=0)
    additional_metadata = Column(JSON)
    
    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'created_date': self.created_date.isoformat() if self.created_date else None,
            'last_active': self.last_active.isoformat() if self.last_active else None,
            'user_ip': self.user_ip,
            'requests_count': self.requests_count,
            'metadata': self.additional_metadata
        }

# Database connection management
class DatabaseManager:
    """Database connection and session management"""
    
    def __init__(self, database_url: Optional[str] = None):
        """Initialize database connection"""
        self.database_url = database_url or os.getenv('DATABASE_URL', 'sqlite:///financial_news.db')
        
        # Create engine
        self.engine = create_engine(
            self.database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True
        )
        
        # Create session factory
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
        # Create tables
        Base.metadata.create_all(bind=self.engine)
    
    def get_session(self) -> Session:
        """Get database session"""
        return self.SessionLocal()
    
    def close(self):
        """Close database connection"""
        self.engine.dispose()

# Global database manager instance
db_manager = None

def get_db_manager() -> DatabaseManager:
    """Get or create database manager instance"""
    global db_manager
    if db_manager is None:
        db_manager = DatabaseManager()
    return db_manager

def get_db() -> Session:
    """Get database session for dependency injection"""
    db = get_db_manager().get_session()
    try:
        yield db
    finally:
        db.close() 