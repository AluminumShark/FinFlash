"""Orchestrator for coordinating multiple agents"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
from enum import Enum

from agents.baseAgents import BaseAgent
from agents.researchAgent import FinancialResearchAgent
from agents.speechAgent import SpeechAgent
from agents.sentimentAgent import SentimentAnalysisAgent
from agents.extractionAgent import ExtractionAgent
from agents.riskAgent import RiskAssessmentAgent
from core.database import News, BatchJob, get_db_manager

class ProcessingMode(Enum):
    """Processing modes for the orchestrator"""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    ADAPTIVE = "adaptive"  # Choose based on workload

class Orchestrator:
    """Orchestrates the execution of multiple agents for financial news analysis"""
    
    def __init__(self, 
                 research_agent: Optional[FinancialResearchAgent] = None,
                 speech_agent: Optional[SpeechAgent] = None,
                 sentiment_agent: Optional[SentimentAnalysisAgent] = None,
                 extraction_agent: Optional[ExtractionAgent] = None,
                 risk_agent: Optional[RiskAssessmentAgent] = None,
                 summary_agent: Optional[Any] = None,  # Add summary agent
                 logger: Optional[logging.Logger] = None):
        """
        Initialize Orchestrator
        
        Args:
            research_agent: Research agent instance
            speech_agent: Speech agent instance
            sentiment_agent: Sentiment analysis agent
            extraction_agent: Information extraction agent
            risk_agent: Risk assessment agent
            logger: Logger instance
        """
        self.research_agent = research_agent
        self.speech_agent = speech_agent
        self.sentiment_agent = sentiment_agent
        self.extraction_agent = extraction_agent
        self.risk_agent = risk_agent
        self.summary_agent = summary_agent  # Store summary agent
        
        self.logger = logger or logging.getLogger(__name__)
        
        # Analysis agents (order matters for sequential processing)
        self.analysis_agents = []
        if sentiment_agent:
            self.analysis_agents.append(sentiment_agent)
        if extraction_agent:
            self.analysis_agents.append(extraction_agent)
        if risk_agent:
            self.analysis_agents.append(risk_agent)
        
        # Statistics
        self.total_jobs = 0
        self.successful_jobs = 0
        self.failed_jobs = 0
    
    async def process_text_news(self, 
                               news_content: str,
                               news_title: str = "",
                               news_id: Optional[str] = None,
                               mode: ProcessingMode = ProcessingMode.PARALLEL,
                               save_to_db: bool = True) -> Dict[str, Any]:
        """
        Process text news through all analysis agents
        
        Args:
            news_content: News content text
            news_title: News title
            news_id: Optional news ID
            mode: Processing mode
            save_to_db: Whether to save results
            
        Returns:
            Complete analysis results
        """
        job_id = str(uuid.uuid4())
        self.logger.info(f"Starting text news processing job {job_id}")
        
        # Create or get news ID
        if not news_id and save_to_db:
            news_id = await self._save_news_to_db(news_content, news_title, "text")
        
        # Prepare data for agents
        agent_data = {
            "news_id": news_id,
            "content": news_content,
            "title": news_title,
            "save_to_db": save_to_db
        }
        
        # Process based on mode
        if mode == ProcessingMode.PARALLEL:
            results = await self._process_parallel(agent_data)
        elif mode == ProcessingMode.SEQUENTIAL:
            results = await self._process_sequential(agent_data)
        else:  # ADAPTIVE
            # Use parallel for short content, sequential for long
            if len(news_content) < 2000:
                results = await self._process_parallel(agent_data)
            else:
                results = await self._process_sequential(agent_data)
        
        # Compile final result
        final_result = {
            "job_id": job_id,
            "news_id": news_id,
            "processing_mode": mode.value,
            "timestamp": datetime.utcnow().isoformat(),
            "analysis_results": results,
            "summary": self._generate_quick_summary(results)
        }
        
        self.total_jobs += 1
        if all(r.get("success", False) for r in results.values()):
            self.successful_jobs += 1
        else:
            self.failed_jobs += 1
        
        return final_result
    
    async def process_audio_news(self,
                                audio_file_path: str,
                                mode: ProcessingMode = ProcessingMode.SEQUENTIAL,
                                save_to_db: bool = True) -> Dict[str, Any]:
        """
        Process audio news: transcribe then analyze
        
        Args:
            audio_file_path: Path to audio file
            mode: Processing mode for analysis
            save_to_db: Whether to save results
            
        Returns:
            Complete analysis results including transcription
        """
        if not self.speech_agent:
            raise ValueError("Speech agent is required for audio processing")
        
        job_id = str(uuid.uuid4())
        self.logger.info(f"Starting audio news processing job {job_id}")
        
        # First, transcribe the audio
        try:
            transcription_result = await self.speech_agent.process({
                "audio_file_path": audio_file_path,
                "save_to_db": save_to_db
            })
            
            if not transcription_result.get("success", False):
                return {
                    "job_id": job_id,
                    "success": False,
                    "error": "Transcription failed",
                    "transcription_result": transcription_result
                }
            
            # Extract transcribed content
            transcribed_content = transcription_result["result"]["transcription"]
            news_id = transcription_result["result"].get("news_id")
            
            # Now process the transcribed content
            text_result = await self.process_text_news(
                news_content=transcribed_content,
                news_title=f"Audio Transcription from {audio_file_path}",
                news_id=news_id,
                mode=mode,
                save_to_db=save_to_db
            )
            
            # Combine results
            return {
                **text_result,
                "transcription": transcription_result["result"],
                "audio_file": audio_file_path
            }
            
        except Exception as e:
            self.logger.error(f"Error processing audio: {str(e)}")
            self.failed_jobs += 1
            return {
                "job_id": job_id,
                "success": False,
                "error": str(e)
            }
    
    async def process_search_and_analyze(self,
                                       search_query: str,
                                       num_results: int = 10,
                                       days_back: int = 7,
                                       mode: ProcessingMode = ProcessingMode.PARALLEL) -> Dict[str, Any]:
        """
        Search for news and analyze all results
        
        Args:
            search_query: Search query
            num_results: Number of results to fetch
            days_back: Days to look back
            mode: Processing mode
            
        Returns:
            Search and analysis results
        """
        if not self.research_agent:
            raise ValueError("Research agent is required for search")
        
        job_id = str(uuid.uuid4())
        batch_job_id = None
        
        try:
            # Create batch job record
            batch_job_id = await self._create_batch_job("search_and_analyze", num_results)
            
            # Search for news
            self.logger.info(f"Searching for news: {search_query}")
            search_result = await self.research_agent({
                "query": search_query,
                "num_results": num_results,
                "days_back": days_back,
                "save_to_db": True
            })
            
            articles = search_result["result"]["articles"]
            self.logger.info(f"Found {len(articles)} articles to analyze")
            
            # Analyze each article
            analysis_results = []
            
            for i, article in enumerate(articles):
                self.logger.info(f"Analyzing article {i+1}/{len(articles)}")
                
                try:
                    result = await self.process_text_news(
                        news_content=article["content"],
                        news_title=article["title"],
                        news_id=article["id"],
                        mode=mode,
                        save_to_db=True
                    )
                    
                    analysis_results.append({
                        "article": article,
                        "analysis": result,
                        "success": True
                    })
                    
                    # Update batch job progress
                    await self._update_batch_job(batch_job_id, i + 1, 0)
                    
                except Exception as e:
                    self.logger.error(f"Error analyzing article {article['id']}: {str(e)}")
                    analysis_results.append({
                        "article": article,
                        "error": str(e),
                        "success": False
                    })
                    
                    await self._update_batch_job(batch_job_id, i + 1, 1)
            
            # Complete batch job
            await self._complete_batch_job(batch_job_id)
            
            # Generate summary using Summary Agent if available
            successful_analyses = [r for r in analysis_results if r.get("success", False)]
            
            summary_report = None
            if hasattr(self, 'summary_agent') and self.summary_agent and successful_analyses:
                try:
                    # Prepare data for summary agent
                    all_analysis_results = {}
                    for analysis in successful_analyses:
                        if analysis.get("analysis", {}).get("analysis_results"):
                            # Merge all analysis results
                            for agent_name, agent_result in analysis["analysis"]["analysis_results"].items():
                                if agent_name not in all_analysis_results:
                                    all_analysis_results[agent_name] = []
                                all_analysis_results[agent_name].append(agent_result)
                    
                    # Generate comprehensive summary report
                    self.logger.info("Generating comprehensive summary report")
                    summary_result = await self.summary_agent({
                        "analysis_results": all_analysis_results,
                        "num_articles": len(successful_analyses),
                        "search_query": search_query
                    })
                    
                    if summary_result.get("success", False):
                        summary_report = summary_result.get("result")
                        
                except Exception as e:
                    self.logger.error(f"Error generating summary report: {str(e)}")
            
            return {
                "job_id": job_id,
                "batch_job_id": batch_job_id,
                "search_query": search_query,
                "total_articles": len(articles),
                "analyzed_successfully": len(successful_analyses),
                "analysis_results": analysis_results,
                "aggregate_summary": self._generate_aggregate_summary(successful_analyses),
                "summary_report": summary_report  # Add comprehensive summary report
            }
            
        except Exception as e:
            self.logger.error(f"Error in search and analyze: {str(e)}")
            if batch_job_id:
                await self._fail_batch_job(batch_job_id, str(e))
            raise
    
    async def _process_parallel(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process agents in parallel"""
        tasks = []
        agent_names = []
        
        for agent in self.analysis_agents:
            tasks.append(agent(agent_data))
            agent_names.append(agent.name)
        
        # Execute all agents in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Compile results
        compiled_results = {}
        for agent_name, result in zip(agent_names, results):
            if isinstance(result, Exception):
                compiled_results[agent_name] = {
                    "success": False,
                    "error": str(result)
                }
            else:
                compiled_results[agent_name] = result
        
        return compiled_results
    
    async def _process_sequential(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process agents sequentially"""
        results = {}
        
        for agent in self.analysis_agents:
            try:
                result = await agent(agent_data)
                results[agent.name] = result
                
                # Add results from previous agents to context
                if result.get("success", False):
                    agent_data["context"] = agent_data.get("context", {})
                    agent_data["context"][agent.name] = result.get("result", {})
                    
            except Exception as e:
                self.logger.error(f"Error in {agent.name}: {str(e)}")
                results[agent.name] = {
                    "success": False,
                    "error": str(e)
                }
        
        return results
    
    def _generate_quick_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate quick summary from analysis results"""
        summary = {
            "sentiment": "unknown",
            "risk_level": "unknown",
            "key_entities": [],
            "recommendations": []
        }
        
        # Extract sentiment
        sentiment_result = results.get("SentimentAnalysisAgent", {})
        if sentiment_result.get("success", False):
            sentiment_data = sentiment_result.get("result", {})
            summary["sentiment"] = sentiment_data.get("overall_sentiment", "unknown")
            summary["fear_greed_index"] = sentiment_data.get("fear_greed_index", 50)
        
        # Extract risk level
        risk_result = results.get("RiskAssessmentAgent", {})
        if risk_result.get("success", False):
            risk_data = risk_result.get("result", {})
            summary["risk_level"] = risk_data.get("risk_summary", {}).get("overall_risk_level", "unknown")
            summary["risk_score"] = risk_data.get("risk_summary", {}).get("risk_score", 0)
            
            # Get recommendations
            investment_impl = risk_data.get("investment_implications", {})
            if investment_impl.get("recommendation"):
                summary["recommendations"].append(investment_impl["recommendation"])
        
        # Extract key entities
        extraction_result = results.get("ExtractionAgent", {})
        if extraction_result.get("success", False):
            extraction_data = extraction_result.get("result", {})
            companies = extraction_data.get("entities", {}).get("companies", [])
            summary["key_entities"] = [c.get("name", "") for c in companies[:3]]
            summary["event_type"] = extraction_data.get("event_type", "unknown")
        
        return summary
    
    def _generate_aggregate_summary(self, successful_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate aggregate summary from multiple analyses"""
        if not successful_analyses:
            return {"message": "No successful analyses to summarize"}
        
        # Aggregate sentiment
        sentiments = {"positive": 0, "negative": 0, "neutral": 0}
        total_risk_score = 0
        all_entities = {}
        event_types = {}
        
        for analysis in successful_analyses:
            summary = analysis["analysis"].get("summary", {})
            
            # Count sentiments
            sentiment = summary.get("sentiment", "neutral")
            sentiments[sentiment] = sentiments.get(sentiment, 0) + 1
            
            # Sum risk scores
            total_risk_score += summary.get("risk_score", 0)
            
            # Collect entities
            for entity in summary.get("key_entities", []):
                all_entities[entity] = all_entities.get(entity, 0) + 1
            
            # Count event types
            event_type = summary.get("event_type", "unknown")
            event_types[event_type] = event_types.get(event_type, 0) + 1
        
        # Calculate aggregates
        total_analyses = len(successful_analyses)
        dominant_sentiment = max(sentiments.items(), key=lambda x: x[1])[0]
        avg_risk_score = total_risk_score / total_analyses if total_analyses > 0 else 0
        
        # Sort entities by frequency
        top_entities = sorted(all_entities.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            "total_articles_analyzed": total_analyses,
            "dominant_sentiment": dominant_sentiment,
            "sentiment_distribution": sentiments,
            "average_risk_score": round(avg_risk_score, 1),
            "top_entities": [{"name": e[0], "mentions": e[1]} for e in top_entities],
            "event_type_distribution": event_types,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def _save_news_to_db(self, content: str, title: str, news_type: str) -> str:
        """Save news to database and return ID"""
        db = get_db_manager().get_session()
        
        try:
            news = News(
                title=title or content[:200] + "...",
                content=content,
                source="Direct Input",
                news_type=news_type,
                language="en",
                processed=False
            )
            
            db.add(news)
            db.commit()
            
            return news.id
            
        except Exception as e:
            db.rollback()
            self.logger.error(f"Error saving news: {str(e)}")
            raise
        finally:
            db.close()
    
    async def _create_batch_job(self, job_type: str, total_items: int) -> str:
        """Create batch job record"""
        db = get_db_manager().get_session()
        
        try:
            batch_job = BatchJob(
                job_type=job_type,
                status="running",
                started_date=datetime.utcnow(),
                total_items=total_items,
                processed_items=0,
                failed_items=0
            )
            
            db.add(batch_job)
            db.commit()
            
            return batch_job.id
            
        except Exception as e:
            db.rollback()
            self.logger.error(f"Error creating batch job: {str(e)}")
            raise
        finally:
            db.close()
    
    async def _update_batch_job(self, job_id: str, processed: int, failed: int):
        """Update batch job progress"""
        db = get_db_manager().get_session()
        
        try:
            job = db.query(BatchJob).filter_by(id=job_id).first()
            if job:
                job.processed_items = processed
                job.failed_items = job.failed_items + failed
                db.commit()
                
        except Exception as e:
            db.rollback()
            self.logger.error(f"Error updating batch job: {str(e)}")
        finally:
            db.close()
    
    async def _complete_batch_job(self, job_id: str):
        """Mark batch job as completed"""
        db = get_db_manager().get_session()
        
        try:
            job = db.query(BatchJob).filter_by(id=job_id).first()
            if job:
                job.status = "completed"
                job.completed_date = datetime.utcnow()
                db.commit()
                
        except Exception as e:
            db.rollback()
            self.logger.error(f"Error completing batch job: {str(e)}")
        finally:
            db.close()
    
    async def _fail_batch_job(self, job_id: str, error_message: str):
        """Mark batch job as failed"""
        db = get_db_manager().get_session()
        
        try:
            job = db.query(BatchJob).filter_by(id=job_id).first()
            if job:
                job.status = "failed"
                job.completed_date = datetime.utcnow()
                job.error_message = error_message
                db.commit()
                
        except Exception as e:
            db.rollback()
            self.logger.error(f"Error failing batch job: {str(e)}")
        finally:
            db.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics"""
        return {
            "total_jobs": self.total_jobs,
            "successful_jobs": self.successful_jobs,
            "failed_jobs": self.failed_jobs,
            "success_rate": round(self.successful_jobs / self.total_jobs * 100, 2) if self.total_jobs > 0 else 0,
            "active_agents": len([a for a in self.analysis_agents if a is not None])
        } 