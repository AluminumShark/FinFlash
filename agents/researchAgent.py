"""Research Agent for financial news collection using Exa API"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
import hashlib

from agents.baseAgents import ResearchAgent
from services.exaService import ExaService
from core.database import News, get_db_manager

class FinancialResearchAgent(ResearchAgent):
    """Agent for researching and collecting financial news"""
    
    def __init__(self, exa_service: ExaService, **kwargs):
        """
        Initialize Research Agent
        
        Args:
            exa_service: Exa API service instance
            **kwargs: Additional arguments for BaseAgent
        """
        super().__init__(
            name="FinancialResearchAgent",
            description="Collects and filters financial news from various sources",
            **kwargs
        )
        self.exa_service = exa_service
        
        # Default financial news domains
        self.financial_domains = [
            "bloomberg.com",
            "reuters.com",
            "cnbc.com",
            "ft.com",
            "wsj.com",
            "marketwatch.com",
            "investing.com",
            "seekingalpha.com",
            "finance.yahoo.com",
            "businessinsider.com"
        ]
        
        # Keywords for financial news
        self.finance_keywords = [
            "stock market", "earnings", "IPO", "merger", "acquisition",
            "federal reserve", "interest rate", "inflation", "GDP",
            "cryptocurrency", "bitcoin", "forex", "commodities",
            "tech stocks", "banking", "financial results", "quarterly report"
        ]
        
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process search request and collect financial news
        
        Args:
            data: {
                "query": str,  # Search query
                "keywords": List[str],  # Optional additional keywords
                "days_back": int,  # Days to look back (default: 7)
                "num_results": int,  # Number of results (default: 20)
                "include_domains": List[str],  # Optional domain filter
                "exclude_domains": List[str],  # Optional domain exclusion
                "save_to_db": bool  # Whether to save to database
            }
            
        Returns:
            Collected news articles
        """
        # Extract parameters
        query = data.get("query", "")
        keywords = data.get("keywords", self.finance_keywords)
        days_back = data.get("days_back", 7)
        num_results = data.get("num_results", 20)
        include_domains = data.get("include_domains", self.financial_domains)
        exclude_domains = data.get("exclude_domains", ["twitter.com", "facebook.com"])
        save_to_db = data.get("save_to_db", True)
        
        # Build search query
        if not query:
            # Build query from keywords
            query = " OR ".join([f'"{kw}"' for kw in keywords[:5]])
            query = f"financial news ({query})"
        
        # Search for news
        self.logger.info(f"Searching for financial news: {query}")
        
        try:
            # Use Exa service to search
            articles = await self.exa_service.search_financial_news(
                keywords=[query],
                days_back=days_back,
                num_results=num_results
            )
            
            # Process and filter articles
            processed_articles = []
            
            for article in articles:
                # Skip if no content
                if not article.get('content'):
                    continue
                
                # Create processed article
                processed = {
                    "id": self._generate_article_id(article['url']),
                    "title": article.get('title', ''),
                    "content": article.get('content', ''),
                    "summary": article.get('summary', ''),
                    "source": self._extract_source(article['url']),
                    "source_url": article['url'],
                    "author": article.get('author'),
                    "published_date": article.get('published_date'),
                    "collected_date": datetime.utcnow().isoformat(),
                    "score": article.get('score', 0),
                    "highlights": article.get('highlights', []),
                    "language": "en",  # Default to English
                    "news_type": "text",
                    "confidence_score": article.get('score', 0.8)
                }
                
                # Check for duplicates
                if not self._is_duplicate(processed['id']):
                    processed_articles.append(processed)
            
            # Update statistics
            self.total_items_collected += len(processed_articles)
            
            # Save to database if requested
            if save_to_db and processed_articles:
                await self._save_to_database(processed_articles)
            
            self.logger.info(f"Collected {len(processed_articles)} unique articles")
            
            return {
                "articles": processed_articles,
                "total_found": len(articles),
                "total_processed": len(processed_articles),
                "query": query,
                "date_range": {
                    "start": (datetime.utcnow() - timedelta(days=days_back)).isoformat(),
                    "end": datetime.utcnow().isoformat()
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error collecting financial news: {str(e)}")
            raise
    
    async def collect_data(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Collect data implementation for base class
        
        Args:
            query: Search query
            **kwargs: Additional parameters
            
        Returns:
            List of collected articles
        """
        result = await self.process({
            "query": query,
            **kwargs
        })
        return result.get("articles", [])
    
    async def search_by_ticker(self, ticker: str, days_back: int = 7) -> List[Dict[str, Any]]:
        """
        Search news for specific stock ticker
        
        Args:
            ticker: Stock ticker symbol
            days_back: Days to look back
            
        Returns:
            News articles related to the ticker
        """
        # Build ticker-specific query
        query = f'"{ticker}" stock price earnings financial'
        
        return await self.collect_data(
            query=query,
            days_back=days_back,
            num_results=30
        )
    
    async def search_by_sector(self, sector: str, days_back: int = 3) -> List[Dict[str, Any]]:
        """
        Search news for specific sector
        
        Args:
            sector: Sector name (e.g., "technology", "healthcare")
            days_back: Days to look back
            
        Returns:
            News articles related to the sector
        """
        # Sector-specific keywords
        sector_keywords = {
            "technology": ["tech stocks", "software", "semiconductor", "AI", "cloud computing"],
            "healthcare": ["biotech", "pharmaceutical", "FDA approval", "drug development"],
            "finance": ["banks", "financial services", "fintech", "insurance"],
            "energy": ["oil", "natural gas", "renewable energy", "solar", "wind"],
            "retail": ["e-commerce", "consumer spending", "retail sales"],
            "automotive": ["electric vehicles", "EV", "autonomous driving", "auto sales"]
        }
        
        keywords = sector_keywords.get(sector.lower(), [sector])
        query = f'{sector} sector {" ".join(keywords[:3])}'
        
        return await self.collect_data(
            query=query,
            days_back=days_back,
            num_results=25
        )
    
    def _generate_article_id(self, url: str) -> str:
        """Generate unique article ID from URL"""
        return hashlib.md5(url.encode()).hexdigest()
    
    def _extract_source(self, url: str) -> str:
        """Extract source name from URL"""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        return domain.replace("www.", "").split(".")[0].title()
    
    def _is_duplicate(self, article_id: str) -> bool:
        """Check if article already exists in database"""
        # TODO: Implement database check
        # For now, return False
        return False
    
    async def _save_to_database(self, articles: List[Dict[str, Any]]):
        """Save articles to database"""
        db = get_db_manager().get_session()
        
        try:
            for article in articles:
                # Convert to database model
                news = News(
                    id=article['id'],
                    title=article['title'],
                    content=article['content'],
                    source=article['source'],
                    source_url=article['source_url'],
                    author=article.get('author'),
                    published_date=datetime.fromisoformat(article['published_date']) if article.get('published_date') else None,
                    collected_date=datetime.utcnow(),
                    language=article.get('language', 'en'),
                    news_type=article['news_type'],
                    confidence_score=article['confidence_score'],
                    processed=False,
                    metadata={
                        'summary': article.get('summary'),
                        'highlights': article.get('highlights', []),
                        'score': article.get('score')
                    }
                )
                
                # Check if exists
                existing = db.query(News).filter_by(id=news.id).first()
                if not existing:
                    db.add(news)
            
            db.commit()
            self.logger.info(f"Saved {len(articles)} articles to database")
            
        except Exception as e:
            db.rollback()
            self.logger.error(f"Error saving to database: {str(e)}")
            raise
        finally:
            db.close()
    
    async def get_trending_topics(self) -> Dict[str, Any]:
        """Get current trending financial topics"""
        # Search for trending topics
        query = "trending stocks market movers breaking financial news today"
        
        articles = await self.collect_data(
            query=query,
            days_back=1,
            num_results=50
        )
        
        # Extract topics from titles and content
        topics = {}
        for article in articles:
            # Simple topic extraction (can be enhanced with NLP)
            words = article['title'].lower().split()
            for word in words:
                if len(word) > 3 and word not in ['stock', 'market', 'news', 'today']:
                    topics[word] = topics.get(word, 0) + 1
        
        # Sort by frequency
        trending = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            "trending_topics": [{"topic": t[0], "mentions": t[1]} for t in trending],
            "articles_analyzed": len(articles),
            "timestamp": datetime.utcnow().isoformat()
        } 