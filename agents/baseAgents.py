"""Base Agents Class for all AI Agents"""
import asyncio
import logging
import uuid
import json
from enum import Enum
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime

class AgentStatus(Enum):
    """Agent Status Enumeration"""
    IDLE = "idle"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    TIMEOUT = "timeout"

class AgentType(Enum):
    """Agent Type Enumeration"""
    RESEARCH = "research"
    SPEECH = "speech"
    SENTIMENT = "sentiment"
    EXTRACTION = "extraction"
    RISK = "risk"
    SUMMARY = "summary"
    ORCHESTRATOR = "orchestrator"

class BaseAgent(ABC):
    """Base Class for all Agents in the System"""
    def __init__(self, name: str, agent_type: AgentType, config: dict = None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.agent_type = agent_type
        self.status = AgentStatus.IDLE        
        self.config = config or {}
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self.created_at = datetime.utcnow()
        self.last_execution = None
        self.execution_count = 0
        self.error_count = 0
        self._timeout = self.config.get('timeout', 30)

    @abstractmethod
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Args:
            data: Input Data for Processing
        
        Returns:
            Processed Result Dictionary
        """
        pass

    async def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute Agent Processing with Error Handling and Timeout
        
        Args:
            Data: Input Data for Processing
        
        Returns:
            Result Dictionary with Status and Data
        """
        self.status = AgentStatus.PROCESSING
        self.last_execution = datetime.utcnow()
        self.execution_count += 1

        result = {
            'agent_id': self.id,
            'agent_name': self.name,
            'agent_type': self.agent_type.value,
            'status': None,
            'data': None,
            'error': None,
            'execution_time': None,
            'timestamp': datetime.utcnow().isoformat()
        }

        start_time = datetime.utcnow()

        try:
            # Execute with Timeout
            self.logger.info(f"Agent {self.name} starting execution")

            processed_data = await asyncio.wait_for(
                self.process(data)
                timeout=self._timeout
            )

            self.status = AgentStatus.COMPLETED
            result['status'] = 'success'
            result['data'] = processed_data

            self.logger.info(f"Agent {self.name} completed successfully")
        
        except Exception as e:
            self.status = AgentStatus.ERROR
            self.error_count += 1
            result['status'] = 'error'
            result['error'] = str(e)

            self.logger.error(f"Agent {self.name} encountered error: {str(e)}", exc_info=True)

        finally:
            # Calculate Execution Time
            end_time = datetime.utcnow()
            execution_time = (end_time - start_time).total_seconds()
            result['execution_time'] = execution_time

            # Reset to Idle
            if self.status == AgentStatus.PROCESSING:
                self.status = AgentStatus.IDLE

        return result

    def validate_config(self, data: Dict[str, Any], required_field: list[str]) -> bool:
        """
        Validate Input Data Has Required Fields
        
        Args:
            data: Input Data to Validate
            required_field: List of Required Fields Names
        
        Returns:
            True if valid, raises ValueError if not
        """
        missing_fields = []

        for field in required_field:
            if field not in data or data[field] is None:
                missing_fields.append(field)
            
        if missing_fields:
            raise ValueError(f"Missing Required Fields: {','.join(missing_fields)}")

        return True

    def get_status(self) -> Dict[str, Any]:
        """Get Agent Statistics"""
        retrun {
            'agent_id': self.id,
            'agent_name': self.name,
            'agent_type': self.agent_type.value,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'last_execution': self.last_execution.isoformat() if self.last_execution else None,
            'execution_count': self.execution_count,
            'error_count': self.error_count,
            'error_rate': self.error_count / self.execution_count if self.execution_count > 0 else 0,
        }

    def reset_stats(self):
        """Reset Agent Statistics"""
        self.execution_count = 0
        self.error_count = 0
        self.last_execution = None
        self.status = AgentStatus.IDLE
    
    def __repr__(self):
        return f"<{self.__class__.__name__}(name={self.name}, status={self.status.value})>"