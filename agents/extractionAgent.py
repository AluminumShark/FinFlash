"""Information Extraction Agent for financial news"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json
import re

from agents.baseAgents import AnalysisAgent
from services.openaiService import OpenAIService
from core.database import AnalysisResult, get_db_manager

class ExtractionAgent(AnalysisAgent):
    """Agent for extracting structured information from financial news"""
    
    def __init__(self, openai_service: OpenAIService, **kwargs):
        """
        Initialize Extraction Agent
        
        Args:
            openai_service: OpenAI service instance
            **kwargs: Additional arguments for AIAgent
        """
        super().__init__(
            name="ExtractionAgent",
            analysis_type="extraction",
            openai_service=openai_service,
            temperature=0.2,  # Very low temperature for accurate extraction
            **kwargs
        )
        
        # Event categories for financial news
        self.event_categories = [
            "earnings_announcement", "merger_acquisition", "ipo",
            "product_launch", "regulatory_update", "management_change",
            "partnership", "lawsuit", "market_analysis", "economic_data",
            "dividend_announcement", "stock_split", "bankruptcy",
            "expansion", "layoffs", "guidance_update"
        ]
        
        # Common financial metrics patterns
        self.metric_patterns = {
            "revenue": r"revenue.*?\$?(\d+(?:\.\d+)?)\s*(billion|million|B|M)",
            "earnings": r"earnings.*?\$?(\d+(?:\.\d+)?)\s*(billion|million|B|M)",
            "eps": r"EPS.*?\$?(\d+(?:\.\d+)?)",
            "growth": r"growth.*?(\d+(?:\.\d+)?)\s*%",
            "margin": r"margin.*?(\d+(?:\.\d+)?)\s*%"
        }
    
    def get_system_prompt(self) -> str:
        """Get system prompt for information extraction"""
        return (
            "You are an expert financial analyst specializing in information extraction. "
            "Your task is to extract structured information from financial news, including "
            "entities (companies, people, locations), events, financial metrics, and key data points. "
            "You must respond with a valid JSON object containing the extracted information."
        )
    
    def build_analysis_prompt(self, content: str) -> str:
        """Build information extraction prompt"""
        return f"""Extract all relevant structured information from the following financial news content.

Financial News Content:
{content}

Please extract and provide the information in the following JSON format:
{{
    "entities": {{
        "companies": [
            {{
                "name": "company name",
                "ticker": "stock ticker if mentioned",
                "role": "subject/mentioned/competitor"
            }}
        ],
        "persons": [
            {{
                "name": "person name",
                "title": "job title/position",
                "company": "associated company"
            }}
        ],
        "locations": ["list of geographic locations mentioned"]
    }},
    "event_type": "primary event category from the predefined list",
    "event_details": {{
        "description": "brief description of the main event",
        "date": "event date if mentioned (ISO format)",
        "status": "announced/completed/pending/rumored"
    }},
    "financial_metrics": {{
        "revenue": {{
            "value": "numerical value",
            "unit": "USD/EUR/etc",
            "period": "Q1 2024/FY 2023/etc"
        }},
        "earnings": {{
            "value": "numerical value",
            "unit": "currency",
            "period": "time period"
        }},
        "other_metrics": [
            {{
                "name": "metric name",
                "value": "value",
                "unit": "unit",
                "change": "percentage change if mentioned"
            }}
        ]
    }},
    "key_numbers": [
        {{
            "description": "what this number represents",
            "value": "the number",
            "context": "additional context"
        }}
    ],
    "products_services": ["list of products or services mentioned"],
    "sectors": ["list of industry sectors involved"],
    "time_references": {{
        "publication_date": "when the news was published",
        "reference_dates": ["other important dates mentioned"]
    }},
    "quotes": [
        {{
            "speaker": "who said it",
            "quote": "important quote",
            "context": "context of the quote"
        }}
    ]
}}

Focus on accuracy and extract only information explicitly stated in the content."""
    
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process news content for information extraction
        
        Args:
            data: {
                "news_id": str,  # ID of news to analyze
                "content": str,  # News content
                "title": str,  # Optional news title
                "save_to_db": bool  # Whether to save results
            }
            
        Returns:
            Extracted information
        """
        news_id = data.get("news_id")
        content = data.get("content")
        title = data.get("title", "")
        save_to_db = data.get("save_to_db", True)
        
        if not content:
            raise ValueError("Content is required for information extraction")
        
        # Combine title and content for extraction
        full_content = f"Title: {title}\n\nContent: {content}" if title else content
        
        self.logger.info(f"Extracting information from news: {news_id or 'direct-content'}")
        
        try:
            # Perform information extraction
            start_time = datetime.utcnow()
            
            # Get AI extraction
            extraction_result = await self.analyze(full_content)
            
            # Parse JSON response
            try:
                extracted_data = json.loads(extraction_result)
            except json.JSONDecodeError:
                self.logger.error(f"Failed to parse JSON response: {extraction_result}")
                raise ValueError("Invalid JSON response from AI model")
            
            # Calculate processing time
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Enhance extraction with pattern matching
            pattern_metrics = self._extract_metrics_with_patterns(content)
            
            # Merge pattern-based extraction with AI extraction
            if pattern_metrics:
                if "financial_metrics" not in extracted_data:
                    extracted_data["financial_metrics"] = {}
                
                for metric_type, values in pattern_metrics.items():
                    if metric_type not in extracted_data["financial_metrics"] and values:
                        extracted_data["financial_metrics"][metric_type] = values[0]
            
            # Add metadata
            result = {
                **extracted_data,
                "extraction_metadata": {
                    "processing_time": processing_time,
                    "model_used": self.model,
                    "timestamp": datetime.utcnow().isoformat(),
                    "content_length": len(content),
                    "title_analyzed": bool(title),
                    "pattern_matching_used": bool(pattern_metrics)
                }
            }
            
            # Calculate extraction confidence
            confidence = self._calculate_extraction_confidence(result)
            result["confidence"] = confidence
            
            # Save to database if requested
            if save_to_db and news_id:
                await self._save_to_database(news_id, result, processing_time)
            
            self.logger.info(
                f"Information extraction complete: {len(result.get('entities', {}).get('companies', []))} companies, "
                f"{len(result.get('financial_metrics', {}))} metrics extracted"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error in information extraction: {str(e)}")
            raise
    
    def _extract_metrics_with_patterns(self, content: str) -> Dict[str, List[Dict[str, Any]]]:
        """Extract financial metrics using regex patterns"""
        extracted_metrics = {}
        
        for metric_type, pattern in self.metric_patterns.items():
            matches = re.findall(pattern, content, re.IGNORECASE)
            
            if matches:
                extracted_metrics[metric_type] = []
                for match in matches:
                    if isinstance(match, tuple):
                        value = match[0]
                        unit = match[1] if len(match) > 1 else ""
                        
                        # Normalize unit
                        if unit.lower() in ['billion', 'b']:
                            unit = "billion"
                        elif unit.lower() in ['million', 'm']:
                            unit = "million"
                        
                        extracted_metrics[metric_type].append({
                            "value": value,
                            "unit": f"USD {unit}" if unit else "USD"
                        })
        
        return extracted_metrics
    
    def _calculate_extraction_confidence(self, result: Dict[str, Any]) -> float:
        """Calculate confidence score based on extraction completeness"""
        confidence = 0.5  # Base confidence
        
        # Check entities
        entities = result.get("entities", {})
        if entities.get("companies"):
            confidence += 0.15
        if entities.get("persons"):
            confidence += 0.1
        
        # Check event type
        if result.get("event_type") and result["event_type"] in self.event_categories:
            confidence += 0.15
        
        # Check financial metrics
        if result.get("financial_metrics"):
            confidence += 0.1
        
        # Check key numbers
        if result.get("key_numbers"):
            confidence += 0.05
        
        # Check quotes
        if result.get("quotes"):
            confidence += 0.05
        
        return min(confidence, 1.0)
    
    async def _save_to_database(self, news_id: str, result: Dict[str, Any], 
                               processing_time: float):
        """Save extraction results to database"""
        db = get_db_manager().get_session()
        
        try:
            # Create analysis result record
            analysis = AnalysisResult(
                news_id=news_id,
                agent_type="extraction",
                result=result,
                confidence=result.get("confidence", 0.8),
                processing_time=processing_time,
                model_used=self.model,
                tokens_used=self.total_tokens  # Approximate
            )
            
            # Check if analysis already exists
            existing = db.query(AnalysisResult).filter_by(
                news_id=news_id,
                agent_type="extraction"
            ).first()
            
            if existing:
                # Update existing record
                existing.result = result
                existing.confidence = result.get("confidence", 0.8)
                existing.processing_time = processing_time
                existing.analysis_date = datetime.utcnow()
            else:
                db.add(analysis)
            
            db.commit()
            self.logger.info(f"Saved extraction results for news {news_id}")
            
        except Exception as e:
            db.rollback()
            self.logger.error(f"Error saving to database: {str(e)}")
            raise
        finally:
            db.close()
    
    async def get_entity_summary(self, entity_type: str = "companies", 
                                time_period_hours: int = 24) -> Dict[str, Any]:
        """
        Get summary of extracted entities over a time period
        
        Args:
            entity_type: Type of entity (companies, persons, locations)
            time_period_hours: Hours to look back
            
        Returns:
            Entity summary with frequency counts
        """
        db = get_db_manager().get_session()
        
        try:
            # Query recent extraction results
            cutoff_time = datetime.utcnow() - timedelta(hours=time_period_hours)
            
            results = db.query(AnalysisResult).filter(
                AnalysisResult.agent_type == "extraction",
                AnalysisResult.analysis_date >= cutoff_time
            ).all()
            
            if not results:
                return {
                    "message": "No extraction data available for the specified period",
                    "entity_type": entity_type,
                    "time_period_hours": time_period_hours
                }
            
            # Aggregate entity data
            entity_counts = {}
            
            for result in results:
                entities = result.result.get("entities", {}).get(entity_type, [])
                
                for entity in entities:
                    if isinstance(entity, dict):
                        name = entity.get("name", "")
                    else:
                        name = entity
                    
                    if name:
                        entity_counts[name] = entity_counts.get(name, 0) + 1
            
            # Sort by frequency
            top_entities = sorted(
                entity_counts.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:20]  # Top 20
            
            return {
                "entity_type": entity_type,
                "time_period_hours": time_period_hours,
                "total_unique_entities": len(entity_counts),
                "top_entities": [
                    {"name": name, "mentions": count} 
                    for name, count in top_entities
                ],
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error getting entity summary: {str(e)}")
            raise
        finally:
            db.close()
    
    async def get_event_timeline(self, time_period_hours: int = 48) -> List[Dict[str, Any]]:
        """
        Get timeline of extracted events
        
        Args:
            time_period_hours: Hours to look back
            
        Returns:
            List of events in chronological order
        """
        db = get_db_manager().get_session()
        
        try:
            # Query recent extraction results
            cutoff_time = datetime.utcnow() - timedelta(hours=time_period_hours)
            
            results = db.query(AnalysisResult).filter(
                AnalysisResult.agent_type == "extraction",
                AnalysisResult.analysis_date >= cutoff_time
            ).order_by(AnalysisResult.analysis_date.desc()).all()
            
            events = []
            
            for result in results:
                event_type = result.result.get("event_type")
                event_details = result.result.get("event_details", {})
                
                if event_type:
                    # Get primary company involved
                    companies = result.result.get("entities", {}).get("companies", [])
                    primary_company = companies[0]["name"] if companies else "Unknown"
                    
                    events.append({
                        "news_id": result.news_id,
                        "event_type": event_type,
                        "description": event_details.get("description", ""),
                        "company": primary_company,
                        "date": event_details.get("date"),
                        "status": event_details.get("status", "unknown"),
                        "analysis_date": result.analysis_date.isoformat()
                    })
            
            return events
            
        except Exception as e:
            self.logger.error(f"Error getting event timeline: {str(e)}")
            raise
        finally:
            db.close() 