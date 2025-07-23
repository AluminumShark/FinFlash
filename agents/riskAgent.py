"""Risk Assessment Agent for financial news"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json

from agents.baseAgents import AnalysisAgent
from services.openaiService import OpenAIService
from core.database import AnalysisResult, get_db_manager, News

class RiskAssessmentAgent(AnalysisAgent):
    """Agent for assessing risks and investment implications from financial news"""
    
    def __init__(self, openai_service: OpenAIService, **kwargs):
        """
        Initialize Risk Assessment Agent
        
        Args:
            openai_service: OpenAI service instance
            **kwargs: Additional arguments for AIAgent
        """
        super().__init__(
            name="RiskAssessmentAgent",
            analysis_type="risk",
            openai_service=openai_service,
            temperature=0.4,  # Moderate temperature for balanced analysis
            **kwargs
        )
        
        # Risk categories
        self.risk_categories = {
            "market": ["volatility", "liquidity", "systemic"],
            "operational": ["management", "execution", "supply_chain"],
            "financial": ["credit", "currency", "interest_rate"],
            "regulatory": ["compliance", "policy_change", "legal"],
            "geopolitical": ["trade_war", "sanctions", "political_instability"],
            "technological": ["disruption", "cyber_security", "innovation_lag"]
        }
        
        # Impact scopes
        self.impact_scopes = ["company", "sector", "market", "global"]
        
        # Time horizons
        self.time_horizons = ["immediate", "short_term", "medium_term", "long_term"]
    
    def get_system_prompt(self) -> str:
        """Get system prompt for risk assessment"""
        return (
            "You are a senior risk analyst specializing in financial markets. "
            "Your task is to assess risks, evaluate potential impacts, and provide "
            "investment recommendations based on financial news. Focus on identifying "
            "both risks and opportunities, considering multiple time horizons and impact scopes. "
            "You must respond with a valid JSON object containing your analysis."
        )
    
    def build_analysis_prompt(self, content: str) -> str:
        """Build risk assessment prompt"""
        return f"""Analyze the following financial news and provide a comprehensive risk assessment.

Financial News Content:
{content}

Please provide your risk assessment in the following JSON format:
{{
    "risk_summary": {{
        "overall_risk_level": "low/medium/high/critical",
        "primary_risks": ["top 3 identified risks"],
        "risk_score": 0 to 100 (0=minimal risk, 100=extreme risk)
    }},
    "detailed_risks": [
        {{
            "risk_type": "market/operational/financial/regulatory/geopolitical/technological",
            "specific_risk": "description of the specific risk",
            "probability": "low/medium/high",
            "impact": "low/medium/high/severe",
            "mitigation": "potential mitigation strategies"
        }}
    ],
    "impact_analysis": {{
        "scope": "company/sector/market/global",
        "affected_entities": ["list of affected companies/sectors"],
        "time_horizon": {{
            "immediate": "impact within days",
            "short_term": "impact within weeks",
            "medium_term": "impact within months",
            "long_term": "impact beyond 6 months"
        }}
    }},
    "opportunities": [
        {{
            "description": "potential opportunity arising from this situation",
            "beneficiaries": ["who might benefit"],
            "timeframe": "when this opportunity might materialize"
        }}
    ],
    "investment_implications": {{
        "recommendation": "buy/hold/sell/avoid",
        "confidence_level": "low/medium/high",
        "alternative_strategies": ["hedging options or alternative investments"],
        "key_watchpoints": ["what to monitor going forward"]
    }},
    "sector_spillover": {{
        "directly_affected": ["sectors directly impacted"],
        "indirectly_affected": ["sectors with secondary impact"],
        "safe_havens": ["sectors likely unaffected or benefiting"]
    }}
}}

Provide balanced analysis considering both downside risks and upside opportunities."""
    
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process news content for risk assessment
        
        Args:
            data: {
                "news_id": str,  # ID of news to analyze
                "content": str,  # News content
                "title": str,  # Optional news title
                "context": dict,  # Optional market context
                "save_to_db": bool  # Whether to save results
            }
            
        Returns:
            Risk assessment results
        """
        news_id = data.get("news_id")
        content = data.get("content")
        title = data.get("title", "")
        context = data.get("context", {})
        save_to_db = data.get("save_to_db", True)
        
        if not content:
            raise ValueError("Content is required for risk assessment")
        
        # Combine title and content for analysis
        full_content = f"Title: {title}\n\nContent: {content}" if title else content
        
        # Add market context if provided
        if context:
            full_content += f"\n\nMarket Context: {json.dumps(context)}"
        
        self.logger.info(f"Assessing risks for news: {news_id or 'direct-content'}")
        
        try:
            # Perform risk assessment
            start_time = datetime.utcnow()
            
            # Get AI analysis
            analysis_result = await self.analyze(full_content)
            
            # Parse JSON response
            try:
                risk_data = json.loads(analysis_result)
            except json.JSONDecodeError:
                self.logger.error(f"Failed to parse JSON response: {analysis_result}")
                raise ValueError("Invalid JSON response from AI model")
            
            # Calculate processing time
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Calculate composite risk score
            composite_score = self._calculate_composite_risk_score(risk_data)
            risk_data["composite_risk_score"] = composite_score
            
            # Add metadata
            result = {
                **risk_data,
                "analysis_metadata": {
                    "processing_time": processing_time,
                    "model_used": self.model,
                    "timestamp": datetime.utcnow().isoformat(),
                    "content_length": len(content),
                    "title_analyzed": bool(title),
                    "context_included": bool(context)
                }
            }
            
            # Validate risk assessment
            self._validate_risk_assessment(result)
            
            # Calculate confidence
            confidence = self._calculate_confidence(result)
            result["confidence"] = confidence
            
            # Save to database if requested
            if save_to_db and news_id:
                await self._save_to_database(news_id, result, processing_time)
            
            self.logger.info(
                f"Risk assessment complete: {result['risk_summary']['overall_risk_level']} "
                f"(score: {result['risk_summary']['risk_score']}, confidence: {confidence})"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error in risk assessment: {str(e)}")
            raise
    
    def _calculate_composite_risk_score(self, risk_data: Dict[str, Any]) -> float:
        """Calculate composite risk score based on multiple factors"""
        base_score = risk_data.get("risk_summary", {}).get("risk_score", 50)
        
        # Adjust based on number of high-impact risks
        detailed_risks = risk_data.get("detailed_risks", [])
        high_impact_count = sum(1 for risk in detailed_risks if risk.get("impact") in ["high", "severe"])
        
        # Adjust based on scope
        scope = risk_data.get("impact_analysis", {}).get("scope", "company")
        scope_multiplier = {
            "company": 1.0,
            "sector": 1.2,
            "market": 1.5,
            "global": 2.0
        }.get(scope, 1.0)
        
        # Calculate composite score
        composite = base_score * scope_multiplier
        composite += high_impact_count * 5  # Add 5 points per high-impact risk
        
        # Cap at 100
        return min(composite, 100.0)
    
    def _calculate_confidence(self, result: Dict[str, Any]) -> float:
        """Calculate confidence score for the risk assessment"""
        confidence = 0.5  # Base confidence
        
        # Check completeness of analysis
        if result.get("risk_summary"):
            confidence += 0.1
        
        if len(result.get("detailed_risks", [])) > 0:
            confidence += 0.15
        
        if result.get("impact_analysis"):
            confidence += 0.1
        
        if result.get("investment_implications"):
            confidence += 0.1
        
        if result.get("opportunities"):
            confidence += 0.05
        
        # Investment recommendation confidence
        inv_confidence = result.get("investment_implications", {}).get("confidence_level", "low")
        if inv_confidence == "high":
            confidence += 0.1
        elif inv_confidence == "medium":
            confidence += 0.05
        
        return min(confidence, 1.0)
    
    def _validate_risk_assessment(self, result: Dict[str, Any]):
        """Validate risk assessment structure"""
        required_fields = [
            "risk_summary", "detailed_risks", "impact_analysis",
            "investment_implications"
        ]
        
        for field in required_fields:
            if field not in result:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate risk level
        risk_level = result["risk_summary"].get("overall_risk_level")
        valid_levels = ["low", "medium", "high", "critical"]
        if risk_level not in valid_levels:
            raise ValueError(f"Invalid risk level: {risk_level}")
        
        # Validate risk score
        risk_score = result["risk_summary"].get("risk_score", 0)
        if not 0 <= risk_score <= 100:
            raise ValueError(f"Risk score out of range: {risk_score}")
    
    async def _save_to_database(self, news_id: str, result: Dict[str, Any], 
                               processing_time: float):
        """Save risk assessment results to database"""
        db = get_db_manager().get_session()
        
        try:
            # Create analysis result record
            analysis = AnalysisResult(
                news_id=news_id,
                agent_type="risk",
                result=result,
                confidence=result.get("confidence", 0.8),
                processing_time=processing_time,
                model_used=self.model,
                tokens_used=self.total_tokens  # Approximate
            )
            
            # Check if analysis already exists
            existing = db.query(AnalysisResult).filter_by(
                news_id=news_id,
                agent_type="risk"
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
            self.logger.info(f"Saved risk assessment for news {news_id}")
            
        except Exception as e:
            db.rollback()
            self.logger.error(f"Error saving to database: {str(e)}")
            raise
        finally:
            db.close()
    
    async def get_risk_alerts(self, risk_threshold: int = 70, 
                             time_period_hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get high-risk alerts from recent assessments
        
        Args:
            risk_threshold: Minimum risk score to trigger alert
            time_period_hours: Hours to look back
            
        Returns:
            List of high-risk alerts
        """
        db = get_db_manager().get_session()
        
        try:
            # Query recent risk assessments
            cutoff_time = datetime.utcnow() - timedelta(hours=time_period_hours)
            
            results = db.query(AnalysisResult).filter(
                AnalysisResult.agent_type == "risk",
                AnalysisResult.analysis_date >= cutoff_time
            ).all()
            
            alerts = []
            
            for result in results:
                risk_score = result.result.get("risk_summary", {}).get("risk_score", 0)
                
                if risk_score >= risk_threshold:
                    # Get associated news info
                    news = db.query(News).filter_by(id=result.news_id).first()
                    
                    alerts.append({
                        "news_id": result.news_id,
                        "title": news.title if news else "Unknown",
                        "risk_score": risk_score,
                        "risk_level": result.result.get("risk_summary", {}).get("overall_risk_level"),
                        "primary_risks": result.result.get("risk_summary", {}).get("primary_risks", []),
                        "impact_scope": result.result.get("impact_analysis", {}).get("scope"),
                        "recommendation": result.result.get("investment_implications", {}).get("recommendation"),
                        "analysis_date": result.analysis_date.isoformat()
                    })
            
            # Sort by risk score descending
            alerts.sort(key=lambda x: x["risk_score"], reverse=True)
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error getting risk alerts: {str(e)}")
            raise
        finally:
            db.close()
    
    async def get_sector_risk_summary(self, time_period_hours: int = 48) -> Dict[str, Any]:
        """
        Get risk summary by sector
        
        Args:
            time_period_hours: Hours to look back
            
        Returns:
            Sector risk summary
        """
        db = get_db_manager().get_session()
        
        try:
            # Query recent risk assessments
            cutoff_time = datetime.utcnow() - timedelta(hours=time_period_hours)
            
            results = db.query(AnalysisResult).filter(
                AnalysisResult.agent_type == "risk",
                AnalysisResult.analysis_date >= cutoff_time
            ).all()
            
            sector_risks = {}
            
            for result in results:
                spillover = result.result.get("sector_spillover", {})
                risk_score = result.result.get("risk_summary", {}).get("risk_score", 0)
                
                # Process directly affected sectors
                for sector in spillover.get("directly_affected", []):
                    if sector not in sector_risks:
                        sector_risks[sector] = {
                            "total_risks": 0,
                            "cumulative_score": 0,
                            "high_risk_count": 0
                        }
                    
                    sector_risks[sector]["total_risks"] += 1
                    sector_risks[sector]["cumulative_score"] += risk_score
                    
                    if risk_score >= 70:
                        sector_risks[sector]["high_risk_count"] += 1
            
            # Calculate average risk scores
            sector_summary = {}
            for sector, data in sector_risks.items():
                avg_risk_score = data["cumulative_score"] / data["total_risks"] if data["total_risks"] > 0 else 0
                
                sector_summary[sector] = {
                    "average_risk_score": round(avg_risk_score, 1),
                    "total_risk_events": data["total_risks"],
                    "high_risk_events": data["high_risk_count"],
                    "risk_level": self._get_risk_level_from_score(avg_risk_score)
                }
            
            # Sort by average risk score
            sorted_sectors = sorted(
                sector_summary.items(),
                key=lambda x: x[1]["average_risk_score"],
                reverse=True
            )
            
            return {
                "time_period_hours": time_period_hours,
                "total_assessments": len(results),
                "sector_risks": dict(sorted_sectors[:10]),  # Top 10 risky sectors
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error getting sector risk summary: {str(e)}")
            raise
        finally:
            db.close()
    
    def _get_risk_level_from_score(self, score: float) -> str:
        """Convert numeric risk score to risk level"""
        if score >= 80:
            return "critical"
        elif score >= 60:
            return "high"
        elif score >= 40:
            return "medium"
        else:
            return "low" 