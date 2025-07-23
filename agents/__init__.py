"""
FinFlash Agents Package
Multi-agent system for financial news analysis
"""

# Import all agent classes for easier access
from .baseAgents import BaseAgent, AIAgent, ResearchAgent, AnalysisAgent
from .researchAgent import FinancialResearchAgent
from .extractionAgent import ExtractionAgent
from .sentimentAgent import SentimentAnalysisAgent
from .summaryAgent import SummaryAgent
from .riskAgent import RiskAssessmentAgent
from .speechAgent import SpeechAgent
from .orchestrator import Orchestrator, ProcessingMode

__all__ = [
    'BaseAgent',
    'AIAgent',
    'ResearchAgent',
    'AnalysisAgent',
    'FinancialResearchAgent',
    'ExtractionAgent',
    'SentimentAnalysisAgent',
    'SummaryAgent',
    'RiskAssessmentAgent',
    'SpeechAgent',
    'Orchestrator',
    'ProcessingMode'
] 