"""
Preview generation endpoints.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import pandas as pd
from app.services.preview_service import PreviewService

router = APIRouter()


class PreviewRequest(BaseModel):
    """Preview generation request."""
    script_content: str
    sample_data: Optional[Dict] = None  # Optional sample data for preview


class PreviewResponse(BaseModel):
    """Preview response."""
    preview: Dict[str, Any]
    html: str
    json: str


@router.post("/", response_model=PreviewResponse)
async def generate_preview(request: PreviewRequest):
    """Generate before/after preview."""
    # For MVP, create sample dataframes
    # In production, this would execute the script with sample data
    
    if request.sample_data:
        df_before = pd.DataFrame(request.sample_data.get("before", {}))
        df_after = pd.DataFrame(request.sample_data.get("after", {}))
    else:
        # Create dummy dataframes for demonstration
        df_before = pd.DataFrame({
            "col1": [1, 2, 3],
            "col2": ["a", "b", "c"]
        })
        df_after = pd.DataFrame({
            "col1": [1, 2, 3, 4],
            "col2": ["a", "b", "c", "d"],
            "col3": [10, 20, 30, 40]
        })
    
    preview_dict = PreviewService.generate_preview(df_before, df_after)
    html = PreviewService.to_html(preview_dict)
    json_str = PreviewService.to_json(preview_dict)
    
    return PreviewResponse(
        preview=preview_dict,
        html=html,
        json=json_str
    )
