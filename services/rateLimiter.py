"""Rate Limiter for API calls"""
import asyncio
import time
from collections import deque
from typing import Optional
import logging

class RateLimiter:
    """Token bucket rate limiter for API calls"""
    
    def __init__(self, rate: int, period: int = 60):
        """
        Initialize rate limiter
        
        Args:
            rate: Number of requests allowed
            period: Time period in seconds (default: 60 for per minute)
        """
        self.rate = rate
        self.period = period
        self.calls = deque()
        self.lock = asyncio.Lock()
        self.logger = logging.getLogger(__name__)
        
    async def acquire(self, tokens: int = 1) -> None:
        """
        Acquire permission to make API call(s)
        
        Args:
            tokens: Number of tokens to acquire (default: 1)
        """
        async with self.lock:
            now = time.time()
            
            # Remove old calls outside the time window
            while self.calls and self.calls[0] <= now - self.period:
                self.calls.popleft()
            
            # Check if we need to wait
            if len(self.calls) >= self.rate:
                # Calculate wait time
                sleep_time = self.calls[0] + self.period - now
                if sleep_time > 0:
                    self.logger.debug(f"Rate limit reached, waiting {sleep_time:.2f}s")
                    await asyncio.sleep(sleep_time)
                    
                    # Retry after waiting
                    await self.acquire(tokens)
                    return
            
            # Add current call
            for _ in range(tokens):
                self.calls.append(now)
    
    def get_remaining_calls(self) -> int:
        """Get number of remaining calls in current window"""
        now = time.time()
        
        # Remove old calls
        while self.calls and self.calls[0] <= now - self.period:
            self.calls.popleft()
            
        return max(0, self.rate - len(self.calls))
    
    def reset(self):
        """Reset the rate limiter"""
        self.calls.clear()


class MultiServiceRateLimiter:
    """Rate limiter for multiple services"""
    
    def __init__(self):
        """Initialize multi-service rate limiter"""
        self.limiters = {}
        self.logger = logging.getLogger(__name__)
        
    def add_service(self, service_name: str, rate: int, period: int = 60):
        """
        Add a service with rate limiting
        
        Args:
            service_name: Name of the service
            rate: Number of requests allowed
            period: Time period in seconds
        """
        self.limiters[service_name] = RateLimiter(rate, period)
        self.logger.info(f"Added rate limiter for {service_name}: {rate} requests per {period}s")
        
    async def acquire(self, service_name: str, tokens: int = 1) -> None:
        """
        Acquire permission for a specific service
        
        Args:
            service_name: Name of the service
            tokens: Number of tokens to acquire
        """
        if service_name not in self.limiters:
            self.logger.warning(f"No rate limiter for service: {service_name}")
            return
            
        await self.limiters[service_name].acquire(tokens)
    
    def get_remaining_calls(self, service_name: str) -> Optional[int]:
        """Get remaining calls for a service"""
        if service_name not in self.limiters:
            return None
            
        return self.limiters[service_name].get_remaining_calls()
    
    def get_all_stats(self) -> dict:
        """Get statistics for all services"""
        return {
            service: {
                "remaining_calls": limiter.get_remaining_calls(),
                "rate": limiter.rate,
                "period": limiter.period
            }
            for service, limiter in self.limiters.items()
        }
    
    def reset_service(self, service_name: str):
        """Reset a specific service's rate limiter"""
        if service_name in self.limiters:
            self.limiters[service_name].reset()
    
    def reset_all(self):
        """Reset all rate limiters"""
        for limiter in self.limiters.values():
            limiter.reset()