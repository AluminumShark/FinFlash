"""Base agent classes for financial news analysis system"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import asyncio
import logging
from datetime import datetime
import time
import uuid

class BaseAgent(ABC):
    """Abstract base class for all agents"""
    
    def __init__(self, name: str, description: str = "", logger: Optional[logging.Logger] = None):
        """
        Initialize base agent
        
        Args:
            name: Agent name
            description: Agent description
            logger: Logger instance
        """
        self.name = name
        self.description = description
        self.agent_id = str(uuid.uuid4())
        self.logger = logger or logging.getLogger(f"agent.{name}")
        self.created_at = datetime.utcnow()
        self.total_requests = 0
        self.total_errors = 0
        self.total_processing_time = 0.0
        
    @abstractmethod
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process input data and return results
        
        Args:
            data: Input data dictionary
            
        Returns:
            Processing results dictionary
        """
        pass
    
    async def __call__(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make agent callable with automatic error handling and logging
        
        Args:
            data: Input data dictionary
            
        Returns:
            Processing results with metadata
        """
        start_time = time.time()
        request_id = str(uuid.uuid4())
        
        self.logger.info(f"Processing request {request_id} for agent {self.name}")
        self.total_requests += 1
        
        try:
            # Process data
            result = await self.process(data)
            
            # Calculate processing time
            processing_time = time.time() - start_time
            self.total_processing_time += processing_time
            
            # Add metadata
            return {
                "success": True,
                "agent": self.name,
                "agent_id": self.agent_id,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat(),
                "processing_time": processing_time,
                "result": result
            }
            
        except Exception as e:
            self.total_errors += 1
            processing_time = time.time() - start_time
            
            self.logger.error(f"Error in agent {self.name}: {str(e)}", exc_info=True)
            
            return {
                "success": False,
                "agent": self.name,
                "agent_id": self.agent_id,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat(),
                "processing_time": processing_time,
                "error": str(e),
                "result": None
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics"""
        return {
            "name": self.name,
            "agent_id": self.agent_id,
            "created_at": self.created_at.isoformat(),
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "error_rate": self.total_errors / self.total_requests if self.total_requests > 0 else 0,
            "total_processing_time": self.total_processing_time,
            "average_processing_time": self.total_processing_time / self.total_requests if self.total_requests > 0 else 0
        }
    
    def reset_stats(self):
        """Reset agent statistics"""
        self.total_requests = 0
        self.total_errors = 0
        self.total_processing_time = 0.0

class AIAgent(BaseAgent):
    """Base class for AI-powered agents"""
    
    def __init__(self, name: str, openai_service, model: str = "gpt-4o", 
                 temperature: float = 0.7, **kwargs):
        """
        Initialize AI agent
        
        Args:
            name: Agent name
            openai_service: OpenAI service instance
            model: Model to use
            temperature: Sampling temperature
            **kwargs: Additional arguments for BaseAgent
        """
        super().__init__(name, **kwargs)
        self.openai_service = openai_service
        self.model = model
        self.temperature = temperature
        self.total_tokens = 0
        self.total_cost = 0.0
        
    async def call_ai(self, messages: List[Dict[str, str]], 
                      response_format: Optional[Dict] = None,
                      **kwargs) -> Dict[str, Any]:
        """
        Call AI model with automatic token tracking
        
        Args:
            messages: Chat messages
            response_format: Response format specification
            **kwargs: Additional OpenAI API parameters
            
        Returns:
            AI response
        """
        result = await self.openai_service.chat_completion(
            messages=messages,
            model=self.model,
            temperature=self.temperature,
            response_format=response_format,
            **kwargs
        )
        
        # Track usage
        if result.get('usage'):
            self.total_tokens += result['usage']['total_tokens']
            
        return result
    
    def get_ai_stats(self) -> Dict[str, Any]:
        """Get AI-specific statistics"""
        base_stats = self.get_stats()
        ai_stats = {
            "model": self.model,
            "temperature": self.temperature,
            "total_tokens": self.total_tokens,
            "average_tokens_per_request": self.total_tokens / self.total_requests if self.total_requests > 0 else 0
        }
        return {**base_stats, **ai_stats}

class ResearchAgent(BaseAgent):
    """Base class for research/data collection agents"""
    
    def __init__(self, name: str, **kwargs):
        """Initialize research agent"""
        super().__init__(name, **kwargs)
        self.total_items_collected = 0
        
    async def collect_data(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Collect data based on query
        
        Args:
            query: Search query
            **kwargs: Additional parameters
            
        Returns:
            List of collected items
        """
        raise NotImplementedError("Subclasses must implement collect_data")
    
    def get_research_stats(self) -> Dict[str, Any]:
        """Get research-specific statistics"""
        base_stats = self.get_stats()
        research_stats = {
            "total_items_collected": self.total_items_collected,
            "average_items_per_request": self.total_items_collected / self.total_requests if self.total_requests > 0 else 0
        }
        return {**base_stats, **research_stats}

class AnalysisAgent(AIAgent):
    """Base class for analysis agents"""
    
    def __init__(self, name: str, analysis_type: str, **kwargs):
        """
        Initialize analysis agent
        
        Args:
            name: Agent name
            analysis_type: Type of analysis (sentiment, extraction, risk, etc.)
            **kwargs: Additional arguments for AIAgent
        """
        super().__init__(name, **kwargs)
        self.analysis_type = analysis_type
        
    def build_analysis_prompt(self, content: str) -> str:
        """
        Build analysis prompt for the specific analysis type
        
        Args:
            content: Content to analyze
            
        Returns:
            Formatted prompt
        """
        raise NotImplementedError("Subclasses must implement build_analysis_prompt")
    
    async def analyze(self, content: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Analyze content
        
        Args:
            content: Content to analyze
            context: Additional context
            
        Returns:
            Analysis results
        """
        prompt = self.build_analysis_prompt(content)
        
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": prompt}
        ]
        
        # Add context if provided
        if context:
            messages.append({
                "role": "user", 
                "content": f"Additional context: {context}"
            })
        
        # Call AI with JSON response format
        response = await self.call_ai(
            messages=messages,
            response_format={"type": "json_object"}
        )
        
        # Extract result
        if response['choices']:
            return response['choices'][0]['message']['content']
        else:
            raise ValueError("No response from AI model")
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Get system prompt for the agent"""
        pass