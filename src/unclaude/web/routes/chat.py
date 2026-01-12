"""Chat WebSocket and API routes."""

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

router = APIRouter()


class ChatMessage(BaseModel):
    """Chat message model."""
    message: str
    provider: str | None = None
    model: str | None = None


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    success: bool
    conversation_id: str | None = None


@router.websocket("/chat")
async def chat_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time chat streaming."""
    await websocket.accept()
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get("message", "")
            
            if not user_message:
                continue
            
            # Create agent
            from unclaude.agent import AgentLoop
            from unclaude.providers.llm import Provider
            from unclaude.onboarding import get_provider_api_key, PROVIDERS, load_config
            import os
            
            provider_name = message_data.get("provider", "gemini")
            
            # Load API key from credentials and set environment variable
            api_key = get_provider_api_key(provider_name)
            if api_key:
                provider_info = PROVIDERS.get(provider_name, {})
                env_var = provider_info.get("env_var")
                if env_var:
                    os.environ[env_var] = api_key
            
            # Load model from config
            config = load_config()
            model = message_data.get("model") or config.get("providers", {}).get(provider_name, {}).get("model")
            
            try:
                provider = Provider(provider_name)
                if model:
                    provider.config.model = model
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "content": f"Provider error: {str(e)}"
                })
                continue
            
            agent = AgentLoop(provider=provider)
            
            # Send start message
            await websocket.send_json({
                "type": "start",
                "conversation_id": agent.conversation_id
            })
            
            # Run agent and stream response
            try:
                response = await agent.run(user_message)
                
                # Send complete response
                await websocket.send_json({
                    "type": "response",
                    "content": response
                })
                
            except Exception as e:
                await websocket.send_json({
                    "type": "error", 
                    "content": f"LLM Error: {str(e)}"
                })
            
            await websocket.send_json({"type": "done"})
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
        except:
            pass


@router.post("/chat", response_model=ChatResponse)
async def chat_http(request: ChatMessage):
    """HTTP endpoint for single chat messages (non-streaming)."""
    from unclaude.agent import AgentLoop
    from unclaude.providers.llm import Provider
    from unclaude.onboarding import get_provider_api_key, PROVIDERS, load_config
    import os
    
    try:
        provider_name = request.provider or "gemini"
        
        # Load API key from credentials and set environment variable
        api_key = get_provider_api_key(provider_name)
        if api_key:
            provider_info = PROVIDERS.get(provider_name, {})
            env_var = provider_info.get("env_var")
            if env_var:
                os.environ[env_var] = api_key
        
        # Load model from config
        config = load_config()
        model = request.model or config.get("providers", {}).get(provider_name, {}).get("model")
        
        provider = Provider(provider_name)
        if model:
            provider.config.model = model
            
        agent = AgentLoop(provider=provider)
        
        response = await agent.run(request.message)
        
        return ChatResponse(
            response=response,
            success=True,
            conversation_id=agent.conversation_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations")
async def get_conversations(limit: int = 20):
    """Get recent conversations."""
    from unclaude.memory import MemoryStore
    
    store = MemoryStore()
    conversations = store.get_recent_conversations(limit=limit)
    
    return {"conversations": conversations}


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str):
    """Get messages for a conversation."""
    from unclaude.memory import MemoryStore
    
    store = MemoryStore()
    messages = store.get_messages(conversation_id)
    
    return {"messages": messages}
