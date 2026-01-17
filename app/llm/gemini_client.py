"""
Gemini (Google) LLM client implementation.
"""
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from typing import List
from app.llm.base import LLMClient
from app.config import settings


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
        self.embedding_model_name = 'models/embedding-001'
        # Try to find an available model at initialization
        self._find_available_model()
    
    def _find_available_model(self):
        """Find an available model by listing all models."""
        try:
            # List all available models
            available_models = genai.list_models()
            model_names = [m.name for m in available_models if 'generateContent' in m.supported_generation_methods]
            
            # Try to find a matching model from our preferred list
            for preferred_name in self.model_names:
                for model_name in model_names:
                    # Check if model name contains our preferred name
                    if preferred_name in model_name.lower() or preferred_name.replace('-', '_') in model_name.lower():
                        try:
                            # Extract just the model identifier (e.g., 'gemini-1.5-flash' from 'models/gemini-1.5-flash')
                            model_id = model_name.split('/')[-1] if '/' in model_name else model_name
                            self.model = genai.GenerativeModel(model_id)
                            print(f"Using model: {model_id}")
                            return
                        except:
                            continue
            
            # If no preferred model found, use the first available one
            if model_names:
                model_id = model_names[0].split('/')[-1] if '/' in model_names[0] else model_names[0]
                self.model = genai.GenerativeModel(model_id)
                print(f"Using first available model: {model_id}")
            else:
                print("Warning: No available models found. Will try models at runtime.")
        except Exception as e:
            print(f"Warning: Could not list models: {str(e)}. Will try models at runtime.")
    
    async def generate_code(self, prompt: str) -> str:
        """Generate code using Gemini."""
        # If we found a model during initialization, use it
        if self.model is not None:
            try:
                response = self.model.generate_content(prompt)
                return response.text.strip()
            except google_exceptions.ResourceExhausted as e:
                # Quota exceeded - provide helpful error message
                error_msg = str(e)
                if "quota" in error_msg.lower() or "429" in error_msg:
                    raise Exception(
                        "Gemini API quota exceeded. The free tier has limited requests. "
                        "Please wait a few minutes and try again, or upgrade your API plan. "
                        f"Details: {error_msg[:200]}"
                    )
                raise
            except Exception as e:
                # If the cached model fails, try to find a new one
                print(f"Warning: Cached model failed, trying to find new model: {str(e)}")
                self.model = None
        
        # If no model found yet, try each model until one works
        last_error = None
        for model_name in self.model_names:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                # If successful, cache this model for next time
                self.model = model
                return response.text.strip()
            except google_exceptions.ResourceExhausted as e:
                # Quota exceeded - don't try other models, just raise
                error_msg = str(e)
                if "quota" in error_msg.lower() or "429" in error_msg:
                    raise Exception(
                        "Gemini API quota exceeded. The free tier has limited requests. "
                        "Please wait a few minutes and try again, or upgrade your API plan. "
                        f"Details: {error_msg[:200]}"
                    )
                raise
            except Exception as e:
                last_error = e
                continue
        
        # If all models failed, try listing available models one more time
        try:
            available_models = genai.list_models()
            model_names = [m.name for m in available_models if 'generateContent' in m.supported_generation_methods]
            if model_names:
                model_id = model_names[0].split('/')[-1] if '/' in model_names[0] else model_names[0]
                model = genai.GenerativeModel(model_id)
                response = model.generate_content(prompt)
                self.model = model
                return response.text.strip()
        except:
            pass
        
        # If all models failed, raise the last error
        raise Exception(f"Gemini generation failed with all models. Last error: {str(last_error)}")
    
    async def embed(self, text: str) -> List[float]:
        """Generate embedding using Gemini."""
        try:
            result = genai.embed_content(
                model=self.embedding_model_name,
                content=text
            )
            return result['embedding']
        except Exception as e:
            raise Exception(f"Gemini embedding failed: {str(e)}")
