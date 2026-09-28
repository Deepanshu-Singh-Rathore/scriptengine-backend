"""
Gemini (Google) LLM client implementation.
"""
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from typing import List
from app.llm.base import LLMClient
from app.config import settings


class GeminiQuotaExceededError(Exception):
    """Raised when Gemini API quota is exceeded."""
    pass


class GeminiGenerationError(Exception):
    """Raised when Gemini code generation fails."""
    pass


class GeminiEmbeddingError(Exception):
    """Raised when Gemini embedding fails."""
    pass


class GeminiClient(LLMClient):
    """Gemini online LLM client."""
    
    def __init__(self):
        """Initialize Gemini client."""
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not set")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        # List of models to try in order (prioritize gemini-2.5-flash)
        self.model_names = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
        self.model = None
        self.embedding_model_names = ['models/gemini-embedding-001', 'models/gemini-embedding-2', 'models/text-embedding-004']
        self.embedding_model_name = self.embedding_model_names[0]
        # Try to find an available model at initialization
        self._find_available_model()
    
    def _get_model_id(self, model_name: str) -> str:
        """Extract just the model identifier from a full model name."""
        return model_name.split('/')[-1] if '/' in model_name else model_name
    
    def _try_model(self, model_id: str) -> bool:
        """Try to initialize a model. Returns True if successful."""
        try:
            self.model = genai.GenerativeModel(model_id)
            print(f"Using model: {model_id}")
            return True
        except Exception:
            return False
    
    def _matches_preferred(self, preferred_name: str, model_name: str) -> bool:
        """Check if a model name matches a preferred name."""
        model_lower = model_name.lower()
        return preferred_name in model_lower or preferred_name.replace('-', '_') in model_lower
    
    def _try_preferred_models(self, model_names: list) -> bool:
        """Try to find and use a preferred model. Returns True if successful."""
        for preferred_name in self.model_names:
            for model_name in model_names:
                if self._matches_preferred(preferred_name, model_name):
                    model_id = self._get_model_id(model_name)
                    if self._try_model(model_id):
                        return True
        return False
    
    def _find_available_model(self):
        """Find an available model by listing all models."""
        try:
            available_models = genai.list_models()
            model_names = [m.name for m in available_models if 'generateContent' in m.supported_generation_methods]
            
            if self._try_preferred_models(model_names):
                return
            
            # If no preferred model found, use the first available one
            if model_names:
                model_id = self._get_model_id(model_names[0])
                self._try_model(model_id)
                print(f"Using first available model: {model_id}")
            else:
                print("Warning: No available models found. Will try models at runtime.")
        except Exception as e:
            print(f"Warning: Could not list models: {str(e)}. Will try models at runtime.")
    
    def _handle_quota_exceeded(self, error: google_exceptions.ResourceExhausted) -> None:
        """Check if error is quota-related and raise a helpful exception."""
        error_msg = str(error)
        if "quota" in error_msg.lower() or "429" in error_msg:
            raise GeminiQuotaExceededError(
                "Gemini API quota exceeded. The free tier has limited requests. "
                "Please wait a few minutes and try again, or upgrade your API plan. "
                f"Details: {error_msg[:200]}"
            )
        raise error
    
    def _try_generate_with_model(self, model, prompt: str) -> str:
        """Try to generate content with a given model. Returns response text or raises."""
        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except google_exceptions.ResourceExhausted as e:
            self._handle_quota_exceeded(e)
    
    def _try_fallback_models(self, prompt: str) -> str | None:
        """Try to find and use any available model as a fallback. Returns response or None."""
        try:
            available_models = genai.list_models()
            model_names = [m.name for m in available_models if 'generateContent' in m.supported_generation_methods]
            if not model_names:
                return None
            model_id = self._get_model_id(model_names[0])
            model = genai.GenerativeModel(model_id)
            response = model.generate_content(prompt)
            self.model = model
            return response.text.strip()
        except Exception:
            return None
    
    async def generate_code(self, prompt: str) -> str:
        """Generate code using Gemini."""
        # If we found a model during initialization, use it
        if self.model is not None:
            try:
                return self._try_generate_with_model(self.model, prompt)
            except Exception as e:
                # If the cached model fails, try to find a new one
                print(f"Warning: Cached model failed, trying to find new model: {str(e)}")
                self.model = None
        
        # Try each preferred model until one works
        last_error = None
        for model_name in self.model_names:
            try:
                model = genai.GenerativeModel(model_name)
                result = self._try_generate_with_model(model, prompt)
                self.model = model  # Cache successful model
                return result
            except Exception as e:
                last_error = e
                continue
        
        # Final fallback: try listing available models
        fallback_result = self._try_fallback_models(prompt)
        if fallback_result is not None:
            return fallback_result
        
        raise GeminiGenerationError(f"Gemini generation failed with all models. Last error: {str(last_error)}")
    
    async def embed(self, text: str) -> List[float]:
        """Generate embedding using Gemini."""
        last_error = None
        for model_name in self.embedding_model_names:
            try:
                result = genai.embed_content(
                    model=model_name,
                    content=text
                )
                self.embedding_model_name = model_name
                return result['embedding']
            except Exception as e:
                last_error = e
                continue
        
        raise GeminiEmbeddingError(f"Gemini embedding failed with all models: {str(last_error)}")
