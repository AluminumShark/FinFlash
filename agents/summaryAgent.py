"""Summary Agent for generating comprehensive analysis reports"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
import uuid

from agents.baseAgents import AnalysisAgent
from services.openaiService import OpenAIService
from core.database import AnalysisResult, News, get_db_manager

class SummaryAgent(AnalysisAgent):
    """Agent for generating comprehensive summaries from multiple analysis results"""
    
    def __init__(self, openai_service: OpenAIService, **kwargs):
        """
        Initialize Summary Agent
        
        Args:
            openai_service: OpenAI service instance
            **kwargs: Additional arguments for AIAgent
        """
        super().__init__(
            name="SummaryAgent",
            analysis_type="summary",
            openai_service=openai_service,
            temperature=0.5,  # Balanced temperature for creative yet accurate summaries
            **kwargs
        )
        
        # Report templates
        self.report_templates = {
            "executive": "concise executive summary",
            "detailed": "comprehensive detailed analysis",
            "technical": "technical analysis with metrics",
            "investor": "investor-focused insights",
            "risk": "risk-focused assessment"
        }
    
    def get_system_prompt(self) -> str:
        """Get system prompt for summary generation"""
        return (
            "You are a senior financial analyst and expert report writer. "
            "Your task is to synthesize multiple analysis results into clear, "
            "actionable reports. Focus on key insights, trends, and recommendations. "
            "You must respond with a valid JSON object containing the report."
        )
    
    def build_analysis_prompt(self, content: str) -> str:
        """Build summary generation prompt"""
        return f"""Generate a comprehensive financial analysis report based on the following analysis results.

Analysis Results:
{content}

Please generate a report in the following JSON format:
{{
    "executive_summary": {{
        "key_findings": ["top 3-5 most important findings"],
        "market_outlook": "brief market outlook based on analysis",
        "immediate_actions": ["recommended immediate actions"],
        "confidence_level": "high/medium/low"
    }},
    "detailed_analysis": {{
        "sentiment_overview": {{
            "current_sentiment": "description of current market sentiment",
            "sentiment_drivers": ["main factors driving sentiment"],
            "sentiment_risks": ["risks to current sentiment"]
        }},
        "entity_analysis": {{
            "key_companies": [
                {{
                    "name": "company name",
                    "impact": "positive/negative/neutral",
                    "reason": "why this company is significant"
                }}
            ],
            "sector_impacts": ["sectors most affected and how"]
        }},
        "risk_assessment": {{
            "primary_risks": ["main risks identified"],
            "risk_mitigation": ["suggested mitigation strategies"],
            "opportunity_areas": ["potential opportunities"]
        }},
        "market_implications": {{
            "short_term": "1-7 days outlook",
            "medium_term": "1-4 weeks outlook",
            "long_term": "1-6 months outlook"
        }}
    }},
    "investment_recommendations": {{
        "buy_signals": ["assets showing buy signals"],
        "sell_signals": ["assets showing sell signals"],
        "watch_list": ["assets to monitor closely"],
        "portfolio_adjustments": ["suggested portfolio changes"]
    }},
    "data_quality": {{
        "analysis_coverage": "percentage of news successfully analyzed",
        "confidence_metrics": "overall confidence in analysis",
        "data_limitations": ["any limitations in the analysis"]
    }},
    "next_steps": ["recommended follow-up actions"]
}}

Ensure the report is professional, data-driven, and actionable."""
    
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process multiple analysis results to generate summary
        
        Args:
            data: {
                "analyses": List[Dict],  # List of analysis results
                "report_type": str,  # Type of report to generate
                "include_raw_data": bool,  # Whether to include raw analysis data
                "custom_focus": str,  # Optional custom focus area
                "save_to_db": bool  # Whether to save results
            }
            
        Returns:
            Summary report
        """
        analyses = data.get("analyses", [])
        report_type = data.get("report_type", "executive")
        include_raw_data = data.get("include_raw_data", False)
        custom_focus = data.get("custom_focus", "")
        save_to_db = data.get("save_to_db", True)
        
        if not analyses:
            raise ValueError("No analyses provided for summary")
        
        self.logger.info(f"Generating {report_type} summary for {len(analyses)} analyses")
        
        try:
            # Prepare analysis data for summarization
            consolidated_data = self._consolidate_analyses(analyses)
            
            # Add custom focus if provided
            if custom_focus:
                consolidated_data["custom_focus"] = custom_focus
            
            # Generate summary
            start_time = datetime.utcnow()
            
            # Build prompt with consolidated data
            content = json.dumps(consolidated_data, indent=2)
            analysis_result = await self.analyze(content)
            
            # Parse JSON response
            try:
                summary_data = json.loads(analysis_result)
            except json.JSONDecodeError:
                self.logger.error(f"Failed to parse JSON response: {analysis_result}")
                raise ValueError("Invalid JSON response from AI model")
            
            # Calculate processing time
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Add metadata
            result = {
                **summary_data,
                "report_metadata": {
                    "report_type": report_type,
                    "analyses_count": len(analyses),
                    "generation_time": processing_time,
                    "timestamp": datetime.utcnow().isoformat(),
                    "custom_focus": custom_focus,
                    "model_used": self.model
                }
            }
            
            # Include raw data if requested
            if include_raw_data:
                result["raw_analyses"] = analyses
            
            # Calculate overall confidence
            confidence = self._calculate_overall_confidence(analyses)
            result["overall_confidence"] = confidence
            
            # Save to database if requested
            if save_to_db:
                report_id = await self._save_report_to_db(result, analyses)
                result["report_id"] = report_id
            
            self.logger.info(f"Summary report generated successfully")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error generating summary: {str(e)}")
            raise
    
    def _consolidate_analyses(self, analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Consolidate multiple analyses into structured data"""
        consolidated = {
            "total_analyses": len(analyses),
            "sentiment_summary": {},
            "risk_summary": {},
            "entity_summary": {},
            "event_summary": {},
            "key_metrics": {}
        }
        
        # Aggregate sentiment data
        sentiments = {"positive": 0, "negative": 0, "neutral": 0}
        fear_greed_total = 0
        sentiment_count = 0
        
        # Aggregate risk data
        risk_scores = []
        risk_levels = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        
        # Aggregate entities
        all_companies = {}
        all_persons = {}
        event_types = {}
        
        for analysis in analyses:
            # Process sentiment data
            if "sentiment" in analysis:
                sentiment_data = analysis["sentiment"]
                sentiment = sentiment_data.get("overall_sentiment", "neutral")
                sentiments[sentiment] += 1
                
                if "fear_greed_index" in sentiment_data:
                    fear_greed_total += sentiment_data["fear_greed_index"]
                    sentiment_count += 1
            
            # Process risk data
            if "risk" in analysis:
                risk_data = analysis["risk"]
                risk_summary = risk_data.get("risk_summary", {})
                
                if "risk_score" in risk_summary:
                    risk_scores.append(risk_summary["risk_score"])
                
                risk_level = risk_summary.get("overall_risk_level", "medium")
                risk_levels[risk_level] += 1
            
            # Process extraction data
            if "extraction" in analysis:
                extraction_data = analysis["extraction"]
                entities = extraction_data.get("entities", {})
                
                # Aggregate companies
                for company in entities.get("companies", []):
                    name = company.get("name", "")
                    if name:
                        all_companies[name] = all_companies.get(name, 0) + 1
                
                # Aggregate persons
                for person in entities.get("persons", []):
                    name = person.get("name", "")
                    if name:
                        all_persons[name] = all_persons.get(name, 0) + 1
                
                # Count event types
                event_type = extraction_data.get("event_type", "unknown")
                event_types[event_type] = event_types.get(event_type, 0) + 1
        
        # Calculate aggregates
        consolidated["sentiment_summary"] = {
            "distribution": sentiments,
            "dominant_sentiment": max(sentiments.items(), key=lambda x: x[1])[0] if sentiments else "neutral",
            "average_fear_greed": round(fear_greed_total / sentiment_count, 1) if sentiment_count > 0 else 50
        }
        
        consolidated["risk_summary"] = {
            "average_risk_score": round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else 0,
            "risk_level_distribution": risk_levels,
            "high_risk_percentage": round((risk_levels["high"] + risk_levels["critical"]) / len(analyses) * 100, 1) if analyses else 0
        }
        
        # Top entities
        consolidated["entity_summary"] = {
            "top_companies": sorted(all_companies.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_persons": sorted(all_persons.items(), key=lambda x: x[1], reverse=True)[:5],
            "total_unique_companies": len(all_companies),
            "total_unique_persons": len(all_persons)
        }
        
        consolidated["event_summary"] = {
            "event_distribution": event_types,
            "dominant_event_type": max(event_types.items(), key=lambda x: x[1])[0] if event_types else "unknown"
        }
        
        return consolidated
    
    def _calculate_overall_confidence(self, analyses: List[Dict[str, Any]]) -> float:
        """Calculate overall confidence from multiple analyses"""
        if not analyses:
            return 0.0
        
        total_confidence = 0
        confidence_count = 0
        
        for analysis in analyses:
            # Check each analysis type for confidence
            for agent_type in ["sentiment", "extraction", "risk"]:
                if agent_type in analysis:
                    agent_data = analysis[agent_type]
                    if "confidence" in agent_data:
                        total_confidence += agent_data["confidence"]
                        confidence_count += 1
        
        return round(total_confidence / confidence_count, 2) if confidence_count > 0 else 0.5
    
    async def _save_report_to_db(self, report: Dict[str, Any], 
                                analyses: List[Dict[str, Any]]) -> str:
        """Save summary report to database"""
        db = get_db_manager().get_session()
        
        try:
            # Create a virtual news entry for the report
            report_id = str(uuid.uuid4())
            
            # Get news IDs from analyses
            news_ids = []
            for analysis in analyses:
                if "news_id" in analysis:
                    news_ids.append(analysis["news_id"])
            
            # Create analysis result record
            analysis_result = AnalysisResult(
                news_id=report_id,  # Use report ID as news ID
                agent_type="summary",
                result={
                    "report": report,
                    "source_news_ids": news_ids,
                    "analyses_count": len(analyses)
                },
                confidence=report.get("overall_confidence", 0.8),
                processing_time=report["report_metadata"]["generation_time"],
                model_used=self.model,
                tokens_used=self.total_tokens
            )
            
            db.add(analysis_result)
            db.commit()
            
            self.logger.info(f"Saved summary report with ID: {report_id}")
            return report_id
            
        except Exception as e:
            db.rollback()
            self.logger.error(f"Error saving report: {str(e)}")
            raise
        finally:
            db.close()
    
    async def generate_batch_report(self, 
                                   time_period_hours: int = 24,
                                   report_type: str = "executive") -> Dict[str, Any]:
        """
        Generate report for all analyses in a time period
        
        Args:
            time_period_hours: Hours to look back
            report_type: Type of report to generate
            
        Returns:
            Batch report
        """
        db = get_db_manager().get_session()
        
        try:
            # Query recent analysis results
            cutoff_time = datetime.utcnow() - timedelta(hours=time_period_hours)
            
            # Get all analysis results
            results = db.query(AnalysisResult).filter(
                AnalysisResult.analysis_date >= cutoff_time,
                AnalysisResult.agent_type.in_(["sentiment", "extraction", "risk"])
            ).all()
            
            if not results:
                return {
                    "message": "No analysis results found for the specified period",
                    "time_period_hours": time_period_hours
                }
            
            # Group by news ID
            news_analyses = {}
            for result in results:
                news_id = result.news_id
                if news_id not in news_analyses:
                    news_analyses[news_id] = {}
                
                news_analyses[news_id][result.agent_type] = {
                    "result": result.result,
                    "confidence": result.confidence,
                    "analysis_date": result.analysis_date.isoformat()
                }
            
            # Convert to list format
            analyses_list = []
            for news_id, analyses in news_analyses.items():
                # Get news info
                news = db.query(News).filter_by(id=news_id).first()
                
                analysis_entry = {
                    "news_id": news_id,
                    "news_title": news.title if news else "Unknown",
                    "news_date": news.published_date.isoformat() if news and news.published_date else None,
                    **analyses
                }
                analyses_list.append(analysis_entry)
            
            # Generate summary report
            report = await self.process({
                "analyses": analyses_list,
                "report_type": report_type,
                "save_to_db": True
            })
            
            return {
                "batch_report": report,
                "time_period_hours": time_period_hours,
                "total_news_analyzed": len(news_analyses),
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error generating batch report: {str(e)}")
            raise
        finally:
            db.close()
    
    async def generate_custom_report(self,
                                    news_ids: List[str],
                                    report_type: str = "detailed",
                                    custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate custom report for specific news items
        
        Args:
            news_ids: List of news IDs to include
            report_type: Type of report
            custom_prompt: Optional custom instructions
            
        Returns:
            Custom report
        """
        db = get_db_manager().get_session()
        
        try:
            analyses_list = []
            
            for news_id in news_ids:
                # Get all analyses for this news
                results = db.query(AnalysisResult).filter_by(news_id=news_id).all()
                
                if results:
                    news = db.query(News).filter_by(id=news_id).first()
                    
                    analysis_entry = {
                        "news_id": news_id,
                        "news_title": news.title if news else "Unknown",
                        "news_content": news.content[:500] if news else "",  # First 500 chars
                    }
                    
                    for result in results:
                        analysis_entry[result.agent_type] = {
                            "result": result.result,
                            "confidence": result.confidence
                        }
                    
                    analyses_list.append(analysis_entry)
            
            if not analyses_list:
                return {
                    "message": "No analyses found for the specified news IDs",
                    "news_ids": news_ids
                }
            
            # Generate report with custom focus
            report = await self.process({
                "analyses": analyses_list,
                "report_type": report_type,
                "custom_focus": custom_prompt or "",
                "save_to_db": True
            })
            
            return report
            
        except Exception as e:
            self.logger.error(f"Error generating custom report: {str(e)}")
            raise
        finally:
            db.close() 