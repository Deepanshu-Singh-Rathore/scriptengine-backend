"""
Template router for managing script templates.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter()


class Template(BaseModel):
    """Template model."""
    id: str
    name: str
    description: str
    icon: str
    file_types: List[str]
    examples: List[str]


# Template definitions
TEMPLATES = [
    Template(
        id="csv_etl",
        name="CSV ETL",
        description="Transform CSV files - add columns, filter rows, clean data, apply formulas",
        icon="📄",
        file_types=["csv"],
        examples=[
            "Add a new column with today's date",
            "Filter rows where status is 'active'",
            "Convert all text to uppercase"
        ]
    ),
    Template(
        id="xlsx_etl",
        name="XLSX ETL",
        description="Transform Excel files with full formatting and multi-sheet support",
        icon="📊",
        file_types=["xlsx", "xls"],
        examples=[
            "Merge columns A and B",
            "Add a summary row at the bottom",
            "Format dates as YYYY-MM-DD"
        ]
    ),
    Template(
        id="xlsx_to_csv",
        name="XLSX to CSV",
        description="Convert Excel to CSV format with optional data transformations",
        icon="⬇️",
        file_types=["xlsx", "xls"],
        examples=[
            "Convert Excel to CSV keeping only first sheet",
            "Export with semicolon delimiter",
            "Convert and filter specific columns"
        ]
    ),
    Template(
        id="csv_to_xlsx",
        name="CSV to XLSX",
        description="Convert CSV to Excel format with optional styling and formatting",
        icon="⬆️",
        file_types=["csv"],
        examples=[
            "Convert to Excel with auto-column-width",
            "Add Excel formatting with headers",
            "Create styled Excel report"
        ]
    )
]


@router.get("/", response_model=List[Template])
async def get_templates():
    """Get all available templates."""
    return TEMPLATES


@router.get("/{template_id}", response_model=Template)
async def get_template(template_id: str):
    """Get a specific template by ID."""
    for template in TEMPLATES:
        if template.id == template_id:
            return template
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
