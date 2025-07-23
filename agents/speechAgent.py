"""Speech Agent for audio transcription using OpenAI Whisper"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import os
from pathlib import Path
import hashlib
import mimetypes

from agents.baseAgents import BaseAgent
from services.openaiService import OpenAIService
from core.database import News, get_db_manager

class SpeechAgent(BaseAgent):
    """Agent for transcribing audio news using OpenAI Whisper"""
    
    def __init__(self, openai_service: OpenAIService, **kwargs):
        """
        Initialize Speech Agent
        
        Args:
            openai_service: OpenAI service instance
            **kwargs: Additional arguments for BaseAgent
        """
        super().__init__(
            name="SpeechAgent",
            description="Transcribes audio financial news to text using Whisper",
            **kwargs
        )
        self.openai_service = openai_service
        
        # Supported audio formats
        self.supported_formats = [
            '.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'
        ]
        
        # Financial terms for better transcription
        self.financial_terms_prompt = (
            "Financial news broadcast discussing stocks, earnings, IPO, merger, acquisition, "
            "Federal Reserve, interest rates, inflation, GDP, cryptocurrency, Bitcoin, forex, "
            "commodities, banking, quarterly reports, market analysis."
        )
        
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process audio file and transcribe to text
        
        Args:
            data: {
                "audio_file_path": str,  # Path to audio file
                "language": str,  # Language code (optional, default: auto-detect)
                "save_to_db": bool,  # Whether to save to database
                "metadata": dict  # Additional metadata
            }
            
        Returns:
            Transcription result
        """
        # Extract parameters
        audio_file_path = data.get("audio_file_path")
        if not audio_file_path:
            raise ValueError("audio_file_path is required")
        
        language = data.get("language")  # None for auto-detect
        save_to_db = data.get("save_to_db", True)
        metadata = data.get("metadata", {})
        
        # Validate file
        file_path = Path(audio_file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file_path}")
        
        # Check file format
        file_extension = file_path.suffix.lower()
        if file_extension not in self.supported_formats:
            raise ValueError(f"Unsupported audio format: {file_extension}. Supported: {self.supported_formats}")
        
        self.logger.info(f"Processing audio file: {audio_file_path}")
        
        try:
            # Transcribe audio
            result = await self.openai_service.transcribe_audio(
                audio_file_path=str(file_path),
                language=language,
                prompt=self.financial_terms_prompt  # Help with financial terms
            )
            
            # Extract transcription
            transcription = result.get('text', '')
            
            # Analyze transcription quality
            quality_analysis = self._analyze_transcription_quality(transcription)
            
            # Create result
            processed_result = {
                "transcription": transcription,
                "audio_file": str(file_path),
                "file_size_mb": file_path.stat().st_size / (1024 * 1024),
                "duration_estimate_minutes": result.get('estimated_duration_minutes', 0),
                "language": language or "auto-detected",
                "confidence": quality_analysis['confidence'],
                "word_count": quality_analysis['word_count'],
                "has_financial_terms": quality_analysis['has_financial_terms'],
                "quality_indicators": quality_analysis['indicators'],
                "metadata": metadata,
                "transcribed_at": datetime.utcnow().isoformat()
            }
            
            # Save to database if requested
            if save_to_db and transcription:
                news_id = await self._save_to_database(processed_result)
                processed_result['news_id'] = news_id
            
            self.logger.info(f"Successfully transcribed audio: {quality_analysis['word_count']} words")
            
            return processed_result
            
        except Exception as e:
            self.logger.error(f"Error transcribing audio: {str(e)}")
            raise
    
    async def process_batch(self, audio_files: List[str]) -> List[Dict[str, Any]]:
        """
        Process multiple audio files
        
        Args:
            audio_files: List of audio file paths
            
        Returns:
            List of transcription results
        """
        results = []
        
        for audio_file in audio_files:
            try:
                result = await self.process({
                    "audio_file_path": audio_file,
                    "save_to_db": True
                })
                results.append(result)
                
                # Add small delay to avoid rate limits
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Error processing {audio_file}: {str(e)}")
                results.append({
                    "audio_file": audio_file,
                    "error": str(e),
                    "transcription": None
                })
        
        return results
    
    def _analyze_transcription_quality(self, transcription: str) -> Dict[str, Any]:
        """
        Analyze transcription quality and extract metrics
        
        Args:
            transcription: Transcribed text
            
        Returns:
            Quality analysis results
        """
        if not transcription:
            return {
                "confidence": 0.0,
                "word_count": 0,
                "has_financial_terms": False,
                "indicators": []
            }
        
        # Basic metrics
        words = transcription.split()
        word_count = len(words)
        
        # Check for financial terms
        financial_keywords = [
            'stock', 'market', 'share', 'earnings', 'revenue', 'profit',
            'ipo', 'merger', 'acquisition', 'interest', 'rate', 'inflation',
            'gdp', 'economy', 'financial', 'investment', 'portfolio', 'trading',
            'bitcoin', 'cryptocurrency', 'forex', 'commodity', 'oil', 'gold'
        ]
        
        text_lower = transcription.lower()
        found_terms = [term for term in financial_keywords if term in text_lower]
        has_financial_terms = len(found_terms) > 0
        
        # Quality indicators
        indicators = []
        
        # Check sentence structure
        sentences = transcription.split('.')
        avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences) if sentences else 0
        
        if avg_sentence_length > 5 and avg_sentence_length < 30:
            indicators.append("good_sentence_structure")
        
        # Check for coherence (simple heuristic)
        if word_count > 50:
            indicators.append("sufficient_length")
        
        # Check for repeated words (might indicate transcription errors)
        word_freq = {}
        for word in words:
            word_lower = word.lower()
            word_freq[word_lower] = word_freq.get(word_lower, 0) + 1
        
        max_repetition = max(word_freq.values()) if word_freq else 0
        if max_repetition < word_count * 0.1:  # No word repeated more than 10%
            indicators.append("low_repetition")
        
        # Calculate confidence score
        confidence = 0.5  # Base confidence
        
        if has_financial_terms:
            confidence += 0.2
        
        if "good_sentence_structure" in indicators:
            confidence += 0.15
        
        if "sufficient_length" in indicators:
            confidence += 0.1
        
        if "low_repetition" in indicators:
            confidence += 0.05
        
        confidence = min(confidence, 1.0)  # Cap at 1.0
        
        return {
            "confidence": confidence,
            "word_count": word_count,
            "has_financial_terms": has_financial_terms,
            "financial_terms_found": found_terms[:10],  # Top 10 terms
            "indicators": indicators,
            "avg_sentence_length": round(avg_sentence_length, 2)
        }
    
    async def _save_to_database(self, transcription_result: Dict[str, Any]) -> str:
        """
        Save transcription to database as news item
        
        Args:
            transcription_result: Transcription result dictionary
            
        Returns:
            News ID
        """
        db = get_db_manager().get_session()
        
        try:
            # Generate ID from audio file path
            audio_path = transcription_result['audio_file']
            news_id = hashlib.md5(audio_path.encode()).hexdigest()
            
            # Extract title from first sentence or first 100 chars
            content = transcription_result['transcription']
            sentences = content.split('.')
            title = sentences[0][:200] if sentences else content[:200]
            if len(title) == 200:
                title += "..."
            
            # Create news record
            news = News(
                id=news_id,
                title=title,
                content=content,
                source="Audio Transcription",
                source_url=audio_path,
                author=transcription_result.get('metadata', {}).get('author'),
                published_date=transcription_result.get('metadata', {}).get('published_date'),
                collected_date=datetime.utcnow(),
                language=transcription_result.get('language', 'en'),
                news_type='audio',
                original_audio_path=audio_path,
                confidence_score=transcription_result['confidence'],
                processed=False,
                metadata={
                    'transcription_quality': {
                        'word_count': transcription_result['word_count'],
                        'has_financial_terms': transcription_result['has_financial_terms'],
                        'quality_indicators': transcription_result['quality_indicators']
                    },
                    'audio_info': {
                        'file_size_mb': transcription_result['file_size_mb'],
                        'duration_minutes': transcription_result['duration_estimate_minutes']
                    },
                    **transcription_result.get('metadata', {})
                }
            )
            
            # Check if exists
            existing = db.query(News).filter_by(id=news_id).first()
            if existing:
                # Update existing record
                existing.content = news.content
                existing.confidence_score = news.confidence_score
                existing.metadata = news.metadata
                existing.collected_date = news.collected_date
            else:
                db.add(news)
            
            db.commit()
            self.logger.info(f"Saved transcription to database with ID: {news_id}")
            
            return news_id
            
        except Exception as e:
            db.rollback()
            self.logger.error(f"Error saving to database: {str(e)}")
            raise
        finally:
            db.close()
    
    async def enhance_transcription(self, transcription: str) -> str:
        """
        Use GPT to enhance/correct transcription
        
        Args:
            transcription: Raw transcription
            
        Returns:
            Enhanced transcription
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a financial news editor. Your task is to clean up and enhance "
                    "audio transcriptions of financial news broadcasts. Fix any obvious errors, "
                    "add proper punctuation, and ensure financial terms are correctly spelled. "
                    "Maintain the original meaning and content."
                )
            },
            {
                "role": "user",
                "content": f"Please enhance this financial news transcription:\n\n{transcription}"
            }
        ]
        
        response = await self.openai_service.chat_completion(
            messages=messages,
            temperature=0.3,  # Lower temperature for more consistent output
            max_tokens=2000
        )
        
        if response['choices']:
            return response['choices'][0]['message']['content']
        else:
            return transcription  # Return original if enhancement fails 