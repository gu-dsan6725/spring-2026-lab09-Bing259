"""
FastAPI wrapper for the memory-enabled Agent.

Provides REST endpoints for multi-tenant conversational agent with semantic memory.
Each user_id gets isolated memory, each run_id gets its own Agent session.
"""

import os
import uuid
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent import Agent

load_dotenv()

app = FastAPI(
    title="Memory Agent API",
    description="Multi-tenant conversational agent with semantic memory",
    version="1.0.0",
)

# Session cache: run_id -> Agent instance
# ONE Agent per session (run_id) maintained in memory
_session_cache: Dict[str, Agent] = {}


def _get_or_create_agent(user_id: str, run_id: str) -> Agent:
    """Get existing Agent for session or create new one."""
    if run_id in _session_cache:
        return _session_cache[run_id]

    api_key = (
        os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("GROQ_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("GEMINI_API_KEY")
    )
    if not api_key:
        raise HTTPException(status_code=500, detail="No LLM API key configured")

    agent = Agent(user_id=user_id, run_id=run_id, api_key=api_key)
    _session_cache[run_id] = agent
    return agent


class InvocationRequest(BaseModel):
    user_id: str = Field(..., description="User identifier for memory isolation")
    run_id: Optional[str] = Field(None, description="Session ID (auto-generated if omitted)")
    query: str = Field(..., description="User's message")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional context/tags")


class InvocationResponse(BaseModel):
    response: str
    user_id: str
    run_id: str


@app.get("/ping")
def ping():
    return {"status": "ok", "message": "Memory Agent API is running"}


@app.post("/invocation", response_model=InvocationResponse)
def invocation(request: InvocationRequest):
    run_id = request.run_id or str(uuid.uuid4())[:8]

    agent = _get_or_create_agent(request.user_id, run_id)

    try:
        response_text = agent.chat(request.query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return InvocationResponse(
        response=response_text,
        user_id=request.user_id,
        run_id=run_id,
    )
