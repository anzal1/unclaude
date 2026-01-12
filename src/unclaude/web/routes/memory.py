"""Memory management API routes."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


class MemoryEntry(BaseModel):
    """Memory entry model."""
    id: str
    content: str
    memory_type: str
    project_path: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] = {}


class MemorySaveRequest(BaseModel):
    """Request to save a memory."""
    content: str
    memory_type: str = "core"
    project_path: str | None = None


class MemorySearchRequest(BaseModel):
    """Request to search memories."""
    query: str
    project_path: str | None = None
    memory_type: str | None = None
    limit: int = 20


@router.get("/memories")
async def list_memories(
    query: str = Query(None, description="Search query"),
    project_path: str = Query(None, description="Filter by project"),
    memory_type: str = Query(None, description="Filter by type"),
    limit: int = Query(50, description="Max results"),
):
    """List or search memories."""
    from unclaude.memory import MemoryStore
    
    store = MemoryStore()
    
    if query:
        memories = store.search_memories(
            query=query,
            project_path=project_path,
            memory_type=memory_type,
            limit=limit,
        )
    else:
        # Get all memories (using a broad search)
        memories = store.search_memories(
            query="",
            project_path=project_path,
            memory_type=memory_type,
            limit=limit,
        )
    
    return {"memories": memories, "count": len(memories)}


@router.post("/memories")
async def save_memory(request: MemorySaveRequest):
    """Save a new memory."""
    import uuid
    from unclaude.memory import MemoryStore
    
    store = MemoryStore()
    memory_id = f"web-{uuid.uuid4()}"
    
    store.save_memory(
        memory_id=memory_id,
        content=request.content,
        memory_type=request.memory_type,
        project_path=request.project_path,
    )
    
    return {"success": True, "memory_id": memory_id}


@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str):
    """Delete a memory by ID."""
    import sqlite3
    from pathlib import Path
    
    db_path = Path.home() / ".unclaude" / "memory.db"
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        
        if deleted:
            return {"success": True, "message": "Memory deleted"}
        else:
            raise HTTPException(status_code=404, detail="Memory not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memories/stats")
async def memory_stats():
    """Get memory statistics."""
    import sqlite3
    from pathlib import Path
    
    db_path = Path.home() / ".unclaude" / "memory.db"
    
    if not db_path.exists():
        return {"total": 0, "by_type": {}, "by_project": {}}
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Total count
        cursor.execute("SELECT COUNT(*) FROM memories")
        total = cursor.fetchone()[0]
        
        # By type
        cursor.execute("SELECT memory_type, COUNT(*) FROM memories GROUP BY memory_type")
        by_type = dict(cursor.fetchall())
        
        # By project
        cursor.execute("SELECT project_path, COUNT(*) FROM memories GROUP BY project_path LIMIT 10")
        by_project = dict(cursor.fetchall())
        
        conn.close()
        
        return {
            "total": total,
            "by_type": by_type,
            "by_project": by_project,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
