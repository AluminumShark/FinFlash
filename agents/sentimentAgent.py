"""Sentiment Analysis Agent for financial news"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json

from agents.baseAgents import AnalysisAgent
from services.openaiService import OpenAIService
from core.database import AnalysisResult, get_db_manager

class SentimentAnalysisAgent(AnalysisAgent):
    """Agent for analyzing market sentiment in financial news"""
    
    def __init__(self, openai_service: OpenAIService, **kwargs):
        """
        Initialize Sentiment Analysis Agent
        
        Args:
            openai_service: OpenAI service instance
            **kwargs: Additional arguments for AIAgent
        """
        super().__init__(
            name="SentimentAnalysisAgent",
            analysis_type="sentiment",
            openai_service=openai_service,
            temperature=0.3,  # Lower temperature for consistent analysis
            **kwargs
        )
        
        # Sentiment categories
        self.sentiment_categories = ["positive", "negative", "neutral"]
        
        # Market sentiment indicators
        self.sentiment_indicators = {
            "positive": [
                "growth", "profit", "surge", "rally", "gain", "breakthrough",
                "success", "expansion", "record high", "beat expectations",
                "strong performance", "bullish", "optimistic", "upgrade"
            ],
            "negative": [
                "loss", "decline", "fall", "crash", "recession", "layoff",
                "downturn", "bear market", "concern", "warning", "risk",
                "uncertainty", "volatility", "miss expectations", "downgrade"
            ],
            "neutral": [
                "stable", "unchanged", "steady", "maintain", "flat",
                "mixed", "moderate", "average", "as expected"
            ]
        }
    
    def get_system_prompt(self) -> str:
        """Get system prompt for sentiment analysis"""
        return (
            "You are an expert financial analyst specializing in market sentiment analysis. "
            "Your task is to analyze financial news and determine the overall market sentiment, "
            "intensity, and potential impact on markets. "
            "You must respond with a valid JSON object containing your analysis."
        )
    
    def build_analysis_prompt(self, content: str) -> str:
        """Build sentiment analysis prompt"""
        return f"""Analyze the following financial news content and provide a comprehensive sentiment analysis.

Financial News Content:
{content}

Please provide your analysis in the following JSON format:
{{
    "overall_sentiment": "positive/negative/neutral",
    "sentiment_score": 0.0 to 1.0 (intensity),
    "confidence": 0.0 to 1.0,
    "fear_greed_index": 0 to 100 (0=extreme fear, 50=neutral, 100=extreme greed),
    "market_impact": {{
        "immediate": "high/medium/low",
        "short_term": "positive/negative/neutral",
        "long_term": "positive/negative/neutral"
    }},
    "key_phrases": ["list of important sentiment-driving phrases"],
    "sentiment_breakdown": {{
        "positive_aspects": ["list of positive elements"],
        "negative_aspects": ["list of negative elements"],
        "neutral_aspects": ["list of neutral elements"]
    }},
    "investor_sentiment": "risk-on/risk-off/neutral",
    "recommendation": "brief recommendation based on sentiment"
}}

Ensure your analysis is objective and based solely on the content provided."""
    
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process news content for sentiment analysis
        
        Args:
            data: {
                "news_id": str,  # ID of news to analyze
                "content": str,  # News content
                "title": str,  # Optional news title
                "save_to_db": bool  # Whether to save results
            }
            
        Returns:
            Sentiment analysis results
        """
        news_id = data.get("news_id")
        content = data.get("content")
        title = data.get("title", "")
        save_to_db = data.get("save_to_db", True)
        
        if not content:
            raise ValueError("Content is required for sentiment analysis")
        
        # Combine title and content for analysis
        full_content = f"Title: {title}\n\nContent: {content}" if title else content
        
        self.logger.info(f"Analyzing sentiment for news: {news_id or 'direct-content'}")
        
        try:
            # Perform sentiment analysis
            start_time = datetime.utcnow()
            
            # Get AI analysis
            analysis_result = await self.analyze(full_content)
            
            # Parse JSON response
            try:
                sentiment_data = json.loads(analysis_result)
            except json.JSONDecodeError:
                self.logger.error(f"Failed to parse JSON response: {analysis_result}")
                raise ValueError("Invalid JSON response from AI model")
            
            # Calculate processing time
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Add metadata
            result = {
                **sentiment_data,
                "analysis_metadata": {
                    "processing_time": processing_time,
                    "model_used": self.model,
                    "timestamp": datetime.utcnow().isoformat(),
                    "content_length": len(content),
                    "title_analyzed": bool(title)
                }
            }
            
            # Validate sentiment result
            self._validate_sentiment_result(result)
            
            # Save to database if requested
            if save_to_db and news_id:
                await self._save_to_database(news_id, result, processing_time)
            
            self.logger.info(
                f"Sentiment analysis complete: {result['overall_sentiment']} "
                f"(score: {result['sentiment_score']}, confidence: {result['confidence']})"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error in sentiment analysis: {str(e)}")
            raise
    
    async def batch_analyze(self, news_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyze sentiment for multiple news items
        
        Args:
            news_items: List of news items with id, title, and content
            
        Returns:
            List of sentiment analysis results
        """
        results = []
        
        for item in news_items:
            try:
                result = await self.process({
                    "news_id": item.get("id"),
                    "content": item.get("content"),
                    "title": item.get("title"),
                    "save_to_db": True
                })
                results.append({
                    "news_id": item.get("id"),
                    "sentiment_analysis": result,
                    "success": True
                })
                
            except Exception as e:
                self.logger.error(f"Error analyzing {item.get('id')}: {str(e)}")
                results.append({
                    "news_id": item.get("id"),
                    "error": str(e),
                    "success": False
                })
            
            # Small delay to avoid rate limits
            await asyncio.sleep(0.5)
        
        return results
    
    def _validate_sentiment_result(self, result: Dict[str, Any]):
        """Validate sentiment analysis result structure"""
        required_fields = [
            "overall_sentiment", "sentiment_score", "confidence",
            "fear_greed_index", "market_impact", "key_phrases",
            "sentiment_breakdown", "investor_sentiment", "recommendation"
        ]
        
        for field in required_fields:
            if field not in result:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate sentiment category
        if result["overall_sentiment"] not in self.sentiment_categories:
            raise ValueError(f"Invalid sentiment category: {result['overall_sentiment']}")
        
        # Validate numeric ranges
        if not 0 <= result["sentiment_score"] <= 1:
            raise ValueError(f"Sentiment score out of range: {result['sentiment_score']}")
        
        if not 0 <= result["confidence"] <= 1:
            raise ValueError(f"Confidence score out of range: {result['confidence']}")
        
        if not 0 <= result["fear_greed_index"] <= 100:
            raise ValueError(f"Fear/Greed index out of range: {result['fear_greed_index']}")
    
    async def _save_to_database(self, news_id: str, result: Dict[str, Any], 
                               processing_time: float):
        """Save sentiment analysis results to database"""
        db = get_db_manager().get_session()
        
        try:
            # Create analysis result record
            analysis = AnalysisResult(
                news_id=news_id,
                agent_type="sentiment",
                result=result,
                confidence=result["confidence"],
                processing_time=processing_time,
                model_used=self.model,
                tokens_used=self.total_tokens  # Approximate
            )
            
            # Check if analysis already exists
            existing = db.query(AnalysisResult).filter_by(
                news_id=news_id,
                agent_type="sentiment"
            ).first()
            
            if existing:
                # Update existing record
                existing.result = result
                existing.confidence = result["confidence"]
                existing.processing_time = processing_time
                existing.analysis_date = datetime.utcnow()
            else:
                db.add(analysis)
            
            db.commit()
            self.logger.info(f"Saved sentiment analysis for news {news_id}")
            
        except Exception as e:
            db.rollback()
            self.logger.error(f"Error saving to database: {str(e)}")
            raise
        finally:
            db.close()
    
    async def get_market_sentiment_summary(self, time_period_hours: int = 24) -> Dict[str, Any]:
        """
        Get aggregated market sentiment for a time period
        
        Args:
            time_period_hours: Hours to look back
            
        Returns:
            Market sentiment summary
        """
        db = get_db_manager().get_session()
        
        try:
            # Query recent sentiment analyses
            cutoff_time = datetime.utcnow() - timedelta(hours=time_period_hours)
            
            results = db.query(AnalysisResult).filter(
                AnalysisResult.agent_type == "sentiment",
                AnalysisResult.analysis_date >= cutoff_time
            ).all()
            
            if not results:
                return {
                    "message": "No sentiment data available for the specified period",
                    "time_period_hours": time_period_hours
                }
            
            # Aggregate sentiment data
            sentiments = {"positive": 0, "negative": 0, "neutral": 0}
            total_fear_greed = 0
            total_confidence = 0
            
            for result in results:
                sentiment = result.result.get("overall_sentiment", "neutral")
                sentiments[sentiment] += 1
                total_fear_greed += result.result.get("fear_greed_index", 50)
                total_confidence += result.confidence
            
            total_analyses = len(results)
            
            # Calculate percentages and averages
            sentiment_distribution = {
                k: round((v / total_analyses) * 100, 2) 
                for k, v in sentiments.items()
            }
            
            avg_fear_greed = round(total_fear_greed / total_analyses, 1)
            avg_confidence = round(total_confidence / total_analyses, 2)
            
            # Determine overall market sentiment
            if sentiment_distribution["positive"] > 50:
                overall_sentiment = "Bullish"
            elif sentiment_distribution["negative"] > 50:
                overall_sentiment = "Bearish"
            else:
                overall_sentiment = "Mixed/Neutral"
            
            return {
                "time_period_hours": time_period_hours,
                "total_analyses": total_analyses,
                "overall_market_sentiment": overall_sentiment,
                "sentiment_distribution": sentiment_distribution,
                "average_fear_greed_index": avg_fear_greed,
                "average_confidence": avg_confidence,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error getting market sentiment summary: {str(e)}")
            raise
        finally:
            db.close() 