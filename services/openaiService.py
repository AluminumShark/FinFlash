"""OpenAI API Service Wrapper"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from openai import AsyncOpenAI
import tiktoken
import time
import os
from pathlib import Path

from services.rateLimiter import RateLimiter

class OpenAIService:
    """Service for managing OpenAI API calls"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o", 
                 rate_limit: int = 60, max_retries: int = 3):
        """
        Initialize OpenAI service
        
        Args:
            api_key: OpenAI API key
            model: Default model to use
            rate_limit: Requests per minute limit
            max_retries: Maximum retry attempts
        """
        self.api_key = api_key
        self.model = model
        self.max_retries = max_retries
        self.logger = logging.getLogger(__name__)
        
        # Initialize async client
        self.client = AsyncOpenAI(api_key=api_key)
        
        # Initialize rate limiter
        self.rate_limiter = RateLimiter(rate_limit, 60)  # per minute
        
        # Token encoding for the model
        try:
            self.encoding = tiktoken.encoding_for_model(model)
        except:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        
        # Statistics
        self.total_requests = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        
    async def chat_completion(self, messages: List[Dict[str, str]], 
                            model: Optional[str] = None,
                            temperature: float = 0.7,
                            max_tokens: Optional[int] = None,
                            response_format: Optional[Dict] = None,
                            **kwargs) -> Dict[str, Any]:
        """
        Create a chat completion with retry logic
        
        Args:
            messages: List of message dictionaries
            model: Model to use (overrides default)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            response_format: Response format (e.g., {"type": "json_object"})
            **kwargs: Additional parameters for the API
            
        Returns:
            API response dictionary
        """
        model = model or self.model
        
        # Wait for rate limit
        await self.rate_limiter.acquire()
        
        # Prepare request
        request_params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            **kwargs
        }
        
        if max_tokens:
            request_params["max_tokens"] = max_tokens
            
        if response_format:
            request_params["response_format"] = response_format
        
        # Retry logic
        last_error = None
        for attempt in range(self.max_retries):
            try:
                self.logger.debug(f"OpenAI API call attempt {attempt + 1}")
                
                # Make API call
                response = await self.client.chat.completions.create(**request_params)
                
                # Update statistics
                self.total_requests += 1
                if response.usage:
                    self.total_tokens += response.usage.total_tokens
                    self.total_cost += self._calculate_cost(
                        response.usage.prompt_tokens,
                        response.usage.completion_tokens,
                        model
                    )
                
                # Convert to dictionary
                result = {
                    "id": response.id,
                    "model": response.model,
                    "created": response.created,
                    "choices": [
                        {
                            "index": choice.index,
                            "message": {
                                "role": choice.message.role,
                                "content": choice.message.content
                            },
                            "finish_reason": choice.finish_reason
                        }
                        for choice in response.choices
                    ],
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    } if response.usage else None
                }
                
                self.logger.info(f"OpenAI API call successful (tokens: {response.usage.total_tokens if response.usage else 'N/A'})")
                return result
                
            except openai.RateLimitError as e:
                wait_time = min(2 ** attempt * 5, 60)  # Exponential backoff, max 60s
                self.logger.warning(f"Rate limit hit, waiting {wait_time}s: {str(e)}")
                await asyncio.sleep(wait_time)
                last_error = e
                
            except openai.APIError as e:
                self.logger.error(f"OpenAI API error: {str(e)}")
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    
            except Exception as e:
                self.logger.error(f"Unexpected error: {str(e)}")
                last_error = e
                break
        
        # All retries failed
        raise Exception(f"OpenAI API call failed after {self.max_retries} attempts: {str(last_error)}")
    
    async def transcribe_audio(self, audio_file_path: str, 
                             model: str = "whisper-1",
                             language: Optional[str] = None,
                             prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Transcribe audio using Whisper API
        
        Args:
            audio_file_path: Path to audio file
            model: Whisper model to use
            language: Language code (e.g., 'zh' for Chinese)
            prompt: Optional prompt to guide transcription
            
        Returns:
            Transcription result dictionary
        """
        # Validate file
        file_path = Path(audio_file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file_path}")
        
        # Check file size (max 25MB for Whisper)
        file_size = file_path.stat().st_size
        if file_size > 25 * 1024 * 1024:
            raise ValueError(f"Audio file too large: {file_size / 1024 / 1024:.1f}MB (max 25MB)")
        
        # Wait for rate limit
        await self.rate_limiter.acquire()
        
        # Retry logic
        last_error = None
        for attempt in range(self.max_retries):
            try:
                self.logger.debug(f"Whisper API call attempt {attempt + 1}")
                
                # Open file and make API call
                with open(audio_file_path, "rb") as audio_file:
                    params = {"model": model, "file": audio_file}
                    
                    if language:
                        params["language"] = language
                    if prompt:
                        params["prompt"] = prompt
                    
                    response = await self.client.audio.transcriptions.create(**params)
                
                # Update statistics
                self.total_requests += 1
                
                # Calculate approximate cost (Whisper charges per minute)
                # Estimate based on file size (very rough approximation)
                estimated_minutes = file_size / (128 * 1024 * 60)  # Assume 128kbps
                self.total_cost += estimated_minutes * 0.006  # $0.006 per minute
                
                result = {
                    "text": response.text,
                    "model": model,
                    "file_size": file_size,
                    "estimated_duration_minutes": estimated_minutes
                }
                
                self.logger.info(f"Whisper transcription successful")
                return result
                
            except openai.RateLimitError as e:
                wait_time = min(2 ** attempt * 5, 60)
                self.logger.warning(f"Rate limit hit, waiting {wait_time}s: {str(e)}")
                await asyncio.sleep(wait_time)
                last_error = e
                
            except Exception as e:
                self.logger.error(f"Whisper API error: {str(e)}")
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        raise Exception(f"Whisper API call failed after {self.max_retries} attempts: {str(last_error)}")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.encoding.encode(text))
    
    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """
        Calculate API cost based on tokens and model
        
        Note: Prices as of 2024 - update as needed
        """
        # GPT-4o pricing (per 1K tokens)
        if "gpt-4o" in model:
            prompt_cost = prompt_tokens * 0.005 / 1000
            completion_cost = completion_tokens * 0.015 / 1000
        # GPT-4 Turbo pricing (per 1K tokens)
        elif "gpt-4-turbo" in model or "gpt-4-1106" in model:
            prompt_cost = prompt_tokens * 0.01 / 1000
            completion_cost = completion_tokens * 0.03 / 1000
        # GPT-4 pricing
        elif "gpt-4" in model:
            prompt_cost = prompt_tokens * 0.03 / 1000
            completion_cost = completion_tokens * 0.06 / 1000
        # GPT-3.5 Turbo pricing
        elif "gpt-3.5-turbo" in model:
            prompt_cost = prompt_tokens * 0.0005 / 1000
            completion_cost = completion_tokens * 0.0015 / 1000
        else:
            # Default/unknown model
            prompt_cost = prompt_tokens * 0.002 / 1000
            completion_cost = completion_tokens * 0.002 / 1000
            
        return prompt_cost + completion_cost
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "total_cost": round(self.total_cost, 4),
            "average_tokens_per_request": round(self.total_tokens / self.total_requests, 2) if self.total_requests > 0 else 0,
            "model": self.model
        }
    
    def reset_stats(self):
        """Reset statistics"""
        self.total_requests = 0
        self.total_tokens = 0
        self.total_cost = 0.0