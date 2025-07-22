"""Exa API Service Wrapper"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
from exa_py import Exa

from services.rate_limiter import RateLimiter

class ExaService:
    """Service for managing Exa API calls"""
    
    def __init__(self, api_key: str, rate_limit: int = 100, max_retries: int = 3):
        """
        Initialize Exa service
        
        Args:
            api_key: Exa API key
            rate_limit: Requests per minute limit
            max_retries: Maximum retry attempts
        """
        self.api_key = api_key
        self.max_retries = max_retries
        self.logger = logging.getLogger(__name__)
        
        # Initialize Exa client
        self.client = Exa(api_key=api_key)
        
        # Initialize rate limiter
        self.rate_limiter = RateLimiter(rate_limit, 60)
        
        # Statistics
        self.total_requests = 0
        self.total_results = 0
        
    async def search(self, query: str, num_results: int = 10,
                    use_autoprompt: bool = True,
                    type: str = "neural",
                    include_domains: Optional[List[str]] = None,
                    exclude_domains: Optional[List[str]] = None,
                    start_published_date: Optional[str] = None,
                    end_published_date: Optional[str] = None,
                    category: Optional[str] = None,
                    text: bool = False,
                    highlights: bool = False) -> Dict[str, Any]:
        """
        Search for content using Exa API
        
        Args:
            query: Search query
            num_results: Number of results to return
            use_autoprompt: Whether to use autoprompt feature
            type: Search type ("neural" or "keyword")
            include_domains: List of domains to include
            exclude_domains: List of domains to exclude
            start_published_date: Start date for publish date filter (YYYY-MM-DD)
            end_published_date: End date for publish date filter
            category: Category filter (e.g., "news", "papers")
            text: Whether to include text content
            highlights: Whether to include highlights
            
        Returns:
            Search results dictionary
        """
        # Wait for rate limit
        await self.rate_limiter.acquire()
        
        # Make API call with retry logic
        last_error = None
        for attempt in range(self.max_retries):
            try:
                self.logger.debug(f"Exa API search attempt {attempt + 1}")
                
                # Run sync operation in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self._sync_search(
                        query=query,
                        num_results=num_results,
                        use_autoprompt=use_autoprompt,
                        type=type,
                        include_domains=include_domains,
                        exclude_domains=exclude_domains,
                        start_published_date=start_published_date,
                        end_published_date=end_published_date,
                        category=category,
                        text=text,
                        highlights=highlights
                    )
                )
                
                # Update statistics
                self.total_requests += 1
                if hasattr(result, 'results'):
                    self.total_results += len(result.results)
                
                self.logger.info(f"Exa search successful: {len(result.results) if hasattr(result, 'results') else 0} results")
                
                # Convert to dictionary format
                return self._convert_search_response(result)
                
            except Exception as e:
                last_error = str(e)
                self.logger.error(f"Exa API error on attempt {attempt + 1}: {str(e)}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        raise Exception(f"Exa API search failed after {self.max_retries} attempts: {last_error}")
    
    def _sync_search(self, **kwargs) -> Any:
        """Synchronous search wrapper for Exa SDK"""
        # Remove None values from kwargs
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        
        # Handle text/highlights options
        text = kwargs.pop('text', False)
        highlights = kwargs.pop('highlights', False)
        
        if text or highlights:
            # Use search_and_contents if content is needed
            return self.client.search_and_contents(**kwargs, text=text, highlights=highlights)
        else:
            # Use basic search
            return self.client.search(**kwargs)
    
    async def get_contents(self, ids: List[str], 
                          text: bool = True,
                          highlights: bool = False) -> Dict[str, Any]:
        """
        Get full content for search results
        
        Args:
            ids: List of result IDs/URLs
            text: Whether to include full text
            highlights: Whether to include highlights
            
        Returns:
            Content results dictionary
        """
        # Wait for rate limit
        await self.rate_limiter.acquire()
        
        # Make API call with retry logic
        last_error = None
        for attempt in range(self.max_retries):
            try:
                self.logger.debug(f"Exa API get contents attempt {attempt + 1}")
                
                # Run sync operation in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self.client.get_contents(
                        ids=ids,
                        text=text,
                        highlights=highlights
                    )
                )
                
                self.total_requests += 1
                
                self.logger.info(f"Exa get contents successful: {len(result.results) if hasattr(result, 'results') else 0} items")
                
                # Convert to dictionary format
                return self._convert_contents_response(result)
                
            except Exception as e:
                last_error = str(e)
                self.logger.error(f"Exa API error: {str(e)}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        raise Exception(f"Exa API get contents failed after {self.max_retries} attempts: {last_error}")
    
    async def search_financial_news(self, 
                                   keywords: List[str],
                                   days_back: int = 7,
                                   num_results: int = 20) -> List[Dict[str, Any]]:
        """
        Specialized search for financial news
        
        Args:
            keywords: List of keywords to search
            days_back: Number of days to look back
            num_results: Number of results to return
            
        Returns:
            List of financial news articles with content
        """
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Format dates
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        
        # Build search query
        query = " OR ".join([f'"{keyword}"' for keyword in keywords])
        query = f"financial news ({query})"
        
        # Search with financial news filters
        search_results = await self.search(
            query=query,
            num_results=num_results,
            category="news",
            start_published_date=start_date_str,
            end_published_date=end_date_str,
            exclude_domains=["twitter.com", "facebook.com", "instagram.com"],
            text=True,  # Get text content directly
            highlights=True
        )
        
        # Process results
        articles = []
        for result in search_results.get('results', []):
            article = {
                'id': result.get('id', result.get('url', '')),
                'title': result.get('title', ''),
                'url': result.get('url', ''),
                'published_date': result.get('published_date'),
                'author': result.get('author'),
                'score': result.get('score'),
                'content': result.get('text', ''),
                'summary': result.get('summary', ''),
                'highlights': result.get('highlights', [])
            }
            articles.append(article)
        
        return articles
    
    async def find_similar(self, url: str, num_results: int = 10,
                          exclude_source_domain: bool = True,
                          text: bool = False) -> Dict[str, Any]:
        """
        Find similar content to a given URL
        
        Args:
            url: URL to find similar content for
            num_results: Number of results to return
            exclude_source_domain: Whether to exclude the source domain
            text: Whether to include text content
            
        Returns:
            Similar results dictionary
        """
        # Wait for rate limit
        await self.rate_limiter.acquire()
        
        try:
            # Run sync operation in thread pool
            loop = asyncio.get_event_loop()
            
            if text:
                result = await loop.run_in_executor(
                    None,
                    lambda: self.client.find_similar_and_contents(
                        url=url,
                        num_results=num_results,
                        exclude_source_domain=exclude_source_domain,
                        text=True
                    )
                )
            else:
                result = await loop.run_in_executor(
                    None,
                    lambda: self.client.find_similar(
                        url=url,
                        num_results=num_results,
                        exclude_source_domain=exclude_source_domain
                    )
                )
            
            self.total_requests += 1
            
            return self._convert_search_response(result)
            
        except Exception as e:
            self.logger.error(f"Exa find similar error: {str(e)}")
            raise
    
    def _convert_search_response(self, response) -> Dict[str, Any]:
        """Convert Exa SDK response to dictionary format"""
        results = []
        
        if hasattr(response, 'results'):
            for result in response.results:
                result_dict = {
                    'id': getattr(result, 'id', getattr(result, 'url', '')),
                    'url': getattr(result, 'url', ''),
                    'title': getattr(result, 'title', ''),
                    'score': getattr(result, 'score', 0),
                    'published_date': getattr(result, 'published_date', None),
                    'author': getattr(result, 'author', None),
                }
                
                # Add content fields if available
                if hasattr(result, 'text'):
                    result_dict['text'] = result.text
                if hasattr(result, 'highlights'):
                    result_dict['highlights'] = result.highlights
                if hasattr(result, 'summary'):
                    result_dict['summary'] = result.summary
                
                results.append(result_dict)
        
        return {
            'results': results,
            'autoprompt_string': getattr(response, 'autoprompt_string', None)
        }
    
    def _convert_contents_response(self, response) -> Dict[str, Any]:
        """Convert Exa contents response to dictionary format"""
        results = []
        
        if hasattr(response, 'results'):
            for result in response.results:
                result_dict = {
                    'id': getattr(result, 'id', getattr(result, 'url', '')),
                    'url': getattr(result, 'url', ''),
                    'title': getattr(result, 'title', ''),
                }
                
                # Add content fields
                if hasattr(result, 'text'):
                    result_dict['text'] = result.text
                if hasattr(result, 'highlights'):
                    result_dict['highlights'] = result.highlights
                if hasattr(result, 'summary'):
                    result_dict['summary'] = result.summary
                
                results.append(result_dict)
        
        return {'results': results}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            "total_requests": self.total_requests,
            "total_results": self.total_results,
            "average_results_per_request": round(self.total_results / self.total_requests, 2) if self.total_requests > 0 else 0
        }
    
    def reset_stats(self):
        """Reset statistics"""
        self.total_requests = 0
        self.total_results = 0