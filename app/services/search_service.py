"""
Script search and reuse service using pgvector.
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Optional
from app.database import ApprovedScript
from app.config import settings
from app.llm.gemini_client import GeminiClient


class SearchService:
    """Service for searching and reusing scripts."""
    
    def __init__(self):
        self.llm_client = GeminiClient()
    
    async def search_similar(
        self,
        db: Session,
        intent: str,
        intent_summary: str,
        script_type: str
    ) -> Optional[Dict]:
        """
        Search for similar approved scripts.
        
        Returns:
            Script dict if similarity >= threshold, None otherwise
        """
        # Generate embedding for intent summary
        embedding = None
        try:
            embedding = await self.llm_client.embed(intent_summary)
        except Exception as e:
            # If embedding fails (e.g., quota exceeded), fall back to text-based search
            print(f"Warning: Embedding generation failed, using text-based search: {str(e)}")
            return self._text_based_search(db, intent, script_type)
        
        embedding_str = "[" + ",".join(map(str, embedding)) + "]"
        
        # Vector similarity search
        query = text("""
            SELECT 
                id, script_type, source_format, target_format, domain,
                intent, description, tags, repo_path, config_path, version,
                1 - (embedding <=> CAST(:embedding AS vector)) as similarity
            FROM approved_scripts
            WHERE script_type = :script_type
            AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT 1
        """)
        
        result = db.execute(
            query,
            {
                "embedding": embedding_str,
                "script_type": script_type
            }
        ).fetchone()
        
        if result and result.similarity >= settings.SIMILARITY_THRESHOLD:
            return {
                "id": str(result.id),
                "script_type": result.script_type,
                "source_format": result.source_format,
                "target_format": result.target_format,
                "domain": result.domain,
                "intent": result.intent,
                "description": result.description,
                "tags": result.tags,
                "repo_path": result.repo_path,
                "config_path": result.config_path,
                "version": result.version,
                "similarity": float(result.similarity)
            }
        
        return None
    
    def build_intent_summary(
        self,
        intent: str,
        schema_info: Optional[Dict] = None
    ) -> str:
        """Build intent summary text for embedding."""
        parts = [f"Intent: {intent}"]
        
        if schema_info:
            if "columns" in schema_info:
                parts.append(f"Columns: {', '.join(schema_info['columns'])}")
            if "data_types" in schema_info:
                parts.append(f"Data types: {schema_info['data_types']}")
        
        return " ".join(parts)
    
    def _text_based_search(
        self,
        db: Session,
        intent: str,
        script_type: str
    ) -> Optional[Dict]:
        """
        Fallback text-based search when embeddings are not available.
        Searches by matching keywords in intent, description, and tags.
        Only returns matches with >= 80% similarity.
        """
        intent_lower = intent.lower()
        intent_words = set(intent_lower.split())
        
        if not intent_words:
            return None
        
        # Get all scripts of the matching type
        scripts = db.query(ApprovedScript).filter(
            ApprovedScript.script_type == script_type
        ).all()
        
        best_match, best_similarity = self._find_best_match(
            scripts, intent_lower, intent_words
        )
        
        self._log_search_result(best_match, best_similarity, intent_words, script_type)
        
        # Return match only if similarity is >= 0.8 (80%)
        if best_match and best_similarity >= 0.8:
            return self._script_to_dict(best_match, best_similarity)
        
        return None
    
    def _find_best_match(
        self,
        scripts: List[ApprovedScript],
        intent_lower: str,
        intent_words: set
    ) -> tuple:
        """Find the script with the highest similarity score."""
        best_match = None
        best_similarity = 0.0
        
        for script in scripts:
            similarity = self._calculate_text_similarity(intent_lower, intent_words, script)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = script
        
        return best_match, best_similarity
    
    def _log_search_result(
        self,
        best_match: Optional[ApprovedScript],
        best_similarity: float,
        intent_words: set,
        script_type: str
    ) -> None:
        """Log the search result for debugging."""
        if not best_match:
            print(f"❌ No matching scripts found for type: {script_type}")
            return
        
        print(f"📊 Text search: Best match similarity: {best_similarity:.2%} (threshold: 80%)")
        print(f"   Script: {best_match.repo_path}")
        print(f"   Intent words: {intent_words}")
        
        if best_similarity >= 0.8:
            print(f"✅ Match found with {best_similarity:.2%} similarity")
        else:
            print(f"❌ Match found but similarity {best_similarity:.2%} is below 80% threshold")
    
    def _script_to_dict(self, script: ApprovedScript, similarity: float) -> Dict:
        """Convert an ApprovedScript to a dictionary response."""
        return {
            "id": str(script.id),
            "script_type": script.script_type,
            "source_format": script.source_format,
            "target_format": script.target_format,
            "domain": script.domain,
            "intent": script.intent,
            "description": script.description,
            "tags": script.tags,
            "repo_path": script.repo_path,
            "config_path": script.config_path,
            "version": script.version,
            "similarity": similarity
        }

    async def search_all_similar(
        self,
        db: Session,
        intent: str,
        intent_summary: str,
        limit: int = 10,
        script_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Search for all similar approved scripts (for search UI).
        Returns multiple results sorted by similarity.
        
        Args:
            db: Database session
            intent: User's search query
            intent_summary: Summary for embedding
            limit: Maximum results to return
            script_type: Optional filter by script type
        
        Returns:
            List of matching scripts with similarity scores
        """
        # Try embedding-based search first
        try:
            embedding = await self.llm_client.embed(intent_summary)
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
            
            # Build query with optional script_type filter
            if script_type:
                query = text("""
                    SELECT 
                        id, script_type, source_format, target_format, domain,
                        intent, description, tags, repo_path, config_path, version,
                        1 - (embedding <=> CAST(:embedding AS vector)) as similarity
                    FROM approved_scripts
                    WHERE embedding IS NOT NULL AND script_type = :script_type
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT :limit
                """)
                results = db.execute(
                    query,
                    {"embedding": embedding_str, "limit": limit, "script_type": script_type}
                ).fetchall()
            else:
                query = text("""
                    SELECT 
                        id, script_type, source_format, target_format, domain,
                        intent, description, tags, repo_path, config_path, version,
                        1 - (embedding <=> CAST(:embedding AS vector)) as similarity
                    FROM approved_scripts
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT :limit
                """)
                results = db.execute(
                    query,
                    {"embedding": embedding_str, "limit": limit}
                ).fetchall()
            
            return [
                {
                    "id": str(r.id),
                    "script_type": r.script_type,
                    "source_format": r.source_format,
                    "target_format": r.target_format,
                    "domain": r.domain,
                    "intent": r.intent,
                    "description": r.description,
                    "tags": r.tags,
                    "repo_path": r.repo_path,
                    "config_path": r.config_path,
                    "version": r.version,
                    "similarity": float(r.similarity)
                }
                for r in results if r.similarity >= 0.3  # Lower threshold for search
            ]
        except Exception as e:
            print(f"Warning: Embedding search failed, using text-based: {e}")
            return self._text_based_search_all(db, intent, limit)

    def _collect_script_text_parts(self, script: ApprovedScript) -> List[str]:
        """Collect all searchable text from a script's metadata."""
        parts = []
        if script.intent:
            parts.extend([i.lower() for i in script.intent])
        if script.description:
            parts.append(script.description.lower())
        if script.tags:
            parts.extend([t.lower() for t in script.tags])
        return parts

    def _calculate_text_similarity(
        self,
        intent_lower: str,
        intent_words: set,
        script: ApprovedScript
    ) -> float:
        """Calculate similarity score between intent and script metadata."""
        all_text_parts = self._collect_script_text_parts(script)
        combined_text = " ".join(all_text_parts)
        combined_words = set(combined_text.split())
        
        # Word overlap similarity
        matching_words = intent_words.intersection(combined_words)
        word_similarity = len(matching_words) / len(intent_words)
        
        # Phrase match boost
        phrase_boost = self._check_phrase_match(intent_lower, script.intent or [])
        
        return min(word_similarity + phrase_boost, 1.0)

    def _check_phrase_match(self, intent_lower: str, script_intents: List[str]) -> float:
        """Check for phrase match and return boost value."""
        for script_intent in script_intents:
            script_intent_lower = script_intent.lower()
            if intent_lower in script_intent_lower or script_intent_lower in intent_lower:
                return 0.2
        return 0.0

    def _text_based_search_all(
        self,
        db: Session,
        intent: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        Text-based search returning multiple results.
        """
        intent_lower = intent.lower()
        intent_words = set(intent_lower.split())
        
        if not intent_words:
            return []
        
        scripts = db.query(ApprovedScript).all()
        scored_scripts = []
        
        for script in scripts:
            similarity = self._calculate_text_similarity(intent_lower, intent_words, script)
            if similarity >= 0.3:  # Lower threshold for search
                scored_scripts.append((script, similarity))
        
        # Sort by similarity descending
        scored_scripts.sort(key=lambda x: x[1], reverse=True)
        
        return [
            {
                "id": str(script.id),
                "script_type": script.script_type,
                "source_format": script.source_format,
                "target_format": script.target_format,
                "domain": script.domain,
                "intent": script.intent,
                "description": script.description,
                "tags": script.tags,
                "repo_path": script.repo_path,
                "config_path": script.config_path,
                "version": script.version,
                "similarity": similarity
            }
            for script, similarity in scored_scripts[:limit]
        ]