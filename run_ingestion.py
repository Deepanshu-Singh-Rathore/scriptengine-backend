"""
Run the ingestion pipeline to index approved scripts into the database.
"""
import sys
import os
from pathlib import Path

# Add the backend directory to the path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.services.ingestion import IngestionService
from app.config import settings

def main():
    """Run the ingestion pipeline."""
    print("🚀 Starting ingestion pipeline...")
    print(f"📁 Repo path: {settings.GITHUB_REPO_PATH}")
    
    # Resolve repo path - handle both absolute and relative paths
    repo_path_str = settings.GITHUB_REPO_PATH
    
    # Remove leading ./ if present
    if repo_path_str.startswith('./'):
        repo_path_str = repo_path_str[2:]
    
    repo_path = Path(repo_path_str)
    
    # If not absolute, make it relative to project root (backend's parent)
    if not repo_path.is_absolute():
        project_root = backend_dir.parent
        repo_path = project_root / repo_path_str
    
    # Normalize the path
    repo_path = repo_path.resolve()
    
    print(f"📂 Resolved repo path: {repo_path}")
    
    if not repo_path.exists():
        print(f"❌ Error: Repo path does not exist: {repo_path}")
        print(f"   Please check your GITHUB_REPO_PATH setting.")
        print(f"   Current value: {settings.GITHUB_REPO_PATH}")
        print(f"   Project root: {backend_dir.parent}")
        return 1
    
    try:
        service = IngestionService()
        service.ingest_repo(str(repo_path.absolute()))
        print("✅ Ingestion complete!")
        return 0
    except Exception as e:
        print(f"❌ Error during ingestion: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
