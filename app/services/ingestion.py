"""
Ingestion pipeline for approved scripts from GitHub.
"""
import json
import asyncio
import aiofiles
from pathlib import Path
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from app.database import ApprovedScript, engine, SessionLocal
from app.llm.gemini_client import GeminiClient
from app.config import settings


class IngestionService:
    """Service for ingesting approved scripts."""
    
    def __init__(self):
        self.llm_client = GeminiClient()
    
    async def ingest_repo_async(self, repo_path: Optional[str] = None):
        """Ingest all approved scripts from repo (async)."""
        repo_path = repo_path or settings.GITHUB_REPO_PATH
        repo_dir = Path(repo_path)
        
        # Store the repo path for use in _ingest_script_async
        self._current_repo_path = repo_path
        
        if not repo_dir.exists():
            raise ValueError(f"Repo path does not exist: {repo_path}")
        
        # Find all metadata.json files (excluding _pending)
        metadata_files = list(repo_dir.rglob("metadata.json"))
        metadata_files = [
            f for f in metadata_files
            if "_pending" not in str(f)
        ]
        
        print(f"📋 Found {len(metadata_files)} script(s) to ingest")
        
        db = SessionLocal()
        try:
            for i, metadata_file in enumerate(metadata_files, 1):
                print(f"📝 Processing {i}/{len(metadata_files)}: {metadata_file.relative_to(repo_dir)}")
                await self._ingest_script_async(metadata_file, db)
            db.commit()
            print(f"✅ Successfully ingested {len(metadata_files)} script(s)")
        except Exception as e:
            db.rollback()
            print(f"❌ Error during ingestion: {str(e)}")
            raise e
        finally:
            db.close()
    
    def ingest_repo(self, repo_path: Optional[str] = None):
        """Ingest all approved scripts from repo (sync wrapper)."""
        asyncio.run(self.ingest_repo_async(repo_path))
    
    async def _ingest_script_async(self, metadata_file: Path, db: Session):
        """Ingest a single script (async)."""
        # Load metadata
        async with aiofiles.open(metadata_file, 'r') as f:
            content = await f.read()
            metadata = json.loads(content)
        
        # Find script file
        script_dir = metadata_file.parent
        script_files = list(script_dir.glob("*.py"))
        if not script_files:
            return
        
        script_file = script_files[0]
        
        # Handle both absolute and relative paths
        # Use the repo_path passed to ingest_repo_async, or fall back to settings
        repo_base_str = getattr(self, '_current_repo_path', None) or settings.GITHUB_REPO_PATH
        repo_base = Path(repo_base_str)
        
        if not repo_base.is_absolute():
            # If relative, make it relative to the backend directory
            backend_dir = Path(__file__).parent.parent.parent
            repo_base = backend_dir.parent / repo_base_str
        
        repo_base = repo_base.resolve()
        
        try:
            repo_path = str(script_file.relative_to(repo_base))
        except ValueError:
            # If relative path fails, use absolute path
            repo_path = str(script_file)
        
        # Build intent summary
        intent_summary_parts = [
            f"Script type: {metadata.get('script_type')}",
            f"Intent: {', '.join(metadata.get('intent', []))}",
            f"Description: {metadata.get('description', '')}",
        ]
        intent_summary = " ".join(intent_summary_parts)
        
        # Generate embedding (skip if quota exceeded)
        embedding_list = None
        try:
            embedding = await self.llm_client.embed(intent_summary)
            embedding_list = list(embedding) if isinstance(embedding, (list, tuple)) else embedding
        except Exception as e:
            print(f"⚠️ Warning: Could not generate embedding for {repo_path}: {str(e)}")
            print("   Script will be indexed without embedding. Search functionality may be limited.")
        
        # Check if script already exists
        existing = db.query(ApprovedScript).filter(
            ApprovedScript.repo_path == repo_path
        ).first()
        
        # Handle both old format (file_type) and new format (source_format)
        source_format = metadata.get("source_format") or metadata.get("file_type")
        target_format = metadata.get("target_format")
        
        if existing:
            # Update
            existing.script_type = metadata.get("script_type")
            existing.source_format = source_format
            existing.target_format = target_format
            existing.domain = metadata.get("domain")
            existing.intent = metadata.get("intent", [])
            existing.description = metadata.get("description")
            existing.tags = metadata.get("tags", [])
            existing.config_path = metadata.get("config_path")
            existing.version = metadata.get("version")
            existing.embedding = embedding_list
        else:
            # Create new
            script = ApprovedScript(
                script_type=metadata.get("script_type"),
                source_format=source_format,
                target_format=target_format,
                domain=metadata.get("domain"),
                intent=metadata.get("intent", []),
                description=metadata.get("description"),
                tags=metadata.get("tags", []),
                repo_path=repo_path,
                config_path=metadata.get("config_path"),
                version=metadata.get("version"),
                embedding=embedding_list
            )
            db.add(script)


if __name__ == "__main__":
    service = IngestionService()
    service.ingest_repo()
    print("Ingestion complete!")
