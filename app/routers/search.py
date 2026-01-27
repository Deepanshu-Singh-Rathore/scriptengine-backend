"""
Search endpoints for approved scripts.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from app.database import get_db, ApprovedScript
from app.services.search_service import SearchService

router = APIRouter()


class SearchRequest(BaseModel):
    """Search request."""
    query: str
    script_type: Optional[str] = None
    limit: int = 10


class SearchResult(BaseModel):
    """Search result."""
    id: str
    script_type: str
    source_format: Optional[str]
    target_format: Optional[str]
    domain: Optional[str]
    intent: Optional[List[str]]
    description: Optional[str]
    tags: Optional[List[str]]
    repo_path: str
    similarity: float


class SearchResponse(BaseModel):
    """Search response."""
    results: List[SearchResult]
    total: int


@router.post("/", response_model=SearchResponse)
async def search_scripts(
    request: SearchRequest,
    db: Session = Depends(get_db)
):
    """Search approved scripts."""
    search_service = SearchService()
    
    # Build intent summary
    intent_summary = search_service.build_intent_summary(request.query)
    
    # Generate embedding
    embedding = await search_service.llm_client.embed(intent_summary)
    embedding_str = "[" + ",".join(map(str, embedding)) + "]"
    
    # Build query
    query = db.query(ApprovedScript).filter(
        ApprovedScript.embedding.isnot(None)
    )
    
    if request.script_type:
        query = query.filter(ApprovedScript.script_type == request.script_type)
    
    # Vector similarity search
    from sqlalchemy import text
    sql_query = text("""
        SELECT 
            id, script_type, source_format, target_format, domain,
            intent, description, tags, repo_path, config_path, version,
            1 - (embedding <=> :embedding::vector) as similarity
        FROM approved_scripts
        WHERE embedding IS NOT NULL
        AND (:script_type IS NULL OR script_type = :script_type)
        ORDER BY embedding <=> :embedding::vector
        LIMIT :limit
    """)
    
    results = db.execute(
        sql_query,
        {
            "embedding": embedding_str,
            "script_type": request.script_type,
            "limit": request.limit
        }
    ).fetchall()
    
    search_results = [
        SearchResult(
            id=str(r.id),
            script_type=r.script_type,
            source_format=r.source_format,
            target_format=r.target_format,
            domain=r.domain,
            intent=r.intent,
            description=r.description,
            tags=r.tags,
            repo_path=r.repo_path,
            similarity=float(r.similarity)
        )
        for r in results
    ]
    
    return SearchResponse(results=search_results, total=len(search_results))
