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
            return await self._text_based_search(db, intent, script_type)
        
        embedding_str = "[" + ",".join(map(str, embedding)) + "]"
        
        # Vector similarity search
        query = text("""
            SELECT 
                id, script_type, source_format, target_format, domain,
                intent, description, tags, repo_path, config_path, version,
                1 - (embedding <=> :embedding::vector) as similarity
            FROM approved_scripts
            WHERE script_type = :script_type
            AND embedding IS NOT NULL
            ORDER BY embedding <=> :embedding::vector
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
    
    async def build_intent_summary(
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
    
    async def _text_based_search(
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
        
        best_match = None
        best_similarity = 0.0
        
        for script in scripts:
            # Collect all text from script metadata
            all_text_parts = []
            
            # Add intent phrases
            if script.intent:
                all_text_parts.extend([i.lower() for i in script.intent])
            
            # Add description
            if script.description:
                all_text_parts.append(script.description.lower())
            
            # Add tags
            if script.tags:
                all_text_parts.extend([t.lower() for t in script.tags])
            
            # Combine all text
            combined_text = " ".join(all_text_parts)
            combined_words = set(combined_text.split())
            
            # Calculate word overlap
            matching_words = intent_words.intersection(combined_words)
            word_similarity = len(matching_words) / len(intent_words) if intent_words else 0
            
            # Check for exact phrase matches (boost similarity)
            phrase_match = False
            for script_intent in (script.intent or []):
                if intent_lower in script_intent.lower() or script_intent.lower() in intent_lower:
                    phrase_match = True
                    break
            
            # Calculate final similarity
            # Base similarity from word overlap (0-1)
            # Boost by 0.2 if exact phrase match found
            similarity = min(word_similarity + (0.2 if phrase_match else 0), 1.0)
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = script
        
        # Debug: Print search results
        if best_match:
            print(f"📊 Text search: Best match similarity: {best_similarity:.2%} (threshold: 80%)")
            print(f"   Script: {best_match.repo_path}")
            print(f"   Intent words: {intent_words}")
        
        # Return match only if similarity is >= 0.8 (80%)
        if best_match and best_similarity >= 0.8:
            print(f"✅ Match found with {best_similarity:.2%} similarity")
            return {
                "id": str(best_match.id),
                "script_type": best_match.script_type,
                "source_format": best_match.source_format,
                "target_format": best_match.target_format,
                "domain": best_match.domain,
                "intent": best_match.intent,
                "description": best_match.description,
                "tags": best_match.tags,
                "repo_path": best_match.repo_path,
                "config_path": best_match.config_path,
                "version": best_match.version,
                "similarity": best_similarity
            }
        else:
            if best_match:
                print(f"❌ Match found but similarity {best_similarity:.2%} is below 80% threshold")
            else:
                print(f"❌ No matching scripts found for type: {script_type}")
        
        return None