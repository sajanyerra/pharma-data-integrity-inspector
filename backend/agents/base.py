"""
Base Agent with LangSmith tracing
"""

from abc import ABC, abstractmethod
from typing import Any, Dict
from datetime import datetime
import asyncpg
from langchain_core.callbacks import AsyncCallbackHandler
from config import settings


class LangSmithCallback(AsyncCallbackHandler):
    """Callback handler for LangSmith tracing"""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.traces = []
        
    async def on_llm_start(self, serialized, prompts, **kwargs):
        self.traces.append({
            "event": "llm_start",
            "agent": self.agent_name,
            "prompts": prompts,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    async def on_llm_end(self, response, **kwargs):
        self.traces.append({
            "event": "llm_end",
            "agent": self.agent_name,
            "response": response.generations,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    async def on_chain_start(self, serialized, inputs, **kwargs):
        self.traces.append({
            "event": "chain_start",
            "agent": self.agent_name,
            "inputs": inputs,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    async def on_chain_end(self, outputs, **kwargs):
        self.traces.append({
            "event": "chain_end",
            "agent": self.agent_name,
            "outputs": outputs,
            "timestamp": datetime.utcnow().isoformat()
        })


class BaseAgent(ABC):
    """Base class for all agents with database and LangSmith integration"""
    
    def __init__(self, name: str):
        self.name = name
        self.session_id = "default"
        self.db_conn = None
        self.callback = LangSmithCallback(name)
        self.callbacks = [self.callback]
        
    async def connect_db(self):
        """Establish database connection"""
        self.db_conn = await asyncpg.connect(settings.DATABASE_URL)
        
    async def disconnect_db(self):
        """Close database connection"""
        if self.db_conn:
            await self.db_conn.close()
            
    async def save_trace(self, input_data: Any, output_data: Any):
        """Save agent trace to database"""
        import json
        try:
            input_json = json.dumps(input_data) if isinstance(input_data, (dict, list)) else str(input_data)
            output_json = json.dumps(output_data) if isinstance(output_data, (dict, list)) else str(output_data)
            await self.db_conn.execute(
                "INSERT INTO agent_trace (session_id, agent_name, input, output) VALUES ($1, $2, $3, $4)",
                self.session_id, self.name, input_json, output_json
            )
        except Exception as e:
            print(f"Warning: Could not save trace: {e}")
        
    @abstractmethod
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute agent logic"""
        pass