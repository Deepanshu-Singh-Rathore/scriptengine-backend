"""
Template engine for script generation.
Loads templates from files in app/templates/ directory.
"""
from pathlib import Path
from typing import Dict, Optional
from jinja2 import Template


class TemplateEngine:
    """Template engine for generating scripts."""
    
    # Template file mapping
    # Maps (script_type, file_type/conversion_type) -> template filename
    TEMPLATE_MAP = {
        "conversion": {
            "csv": "csv_etl_template.py",  # Use ETL template by default
            "csv_simple": "csv_simple_template.py",  # Simple version
            "xlsx": "xlsx_etl_template.py",  # Use ETL template by default
            "xlsx_simple": "xlsx_simple_template.py",  # Simple version
        },
        "format_conversion": {
            "csv_to_xlsx": "csv_to_xlsx_template.py",
            "xlsx_to_csv": "xlsx_to_csv_template.py",
        },
        "etl": {
            "csv": "csv_etl_template.py",
            "csv_simple": "csv_simple_template.py",
            "xlsx": "xlsx_etl_template.py",
            "xlsx_simple": "xlsx_simple_template.py",
        }
    }
    
    _template_cache: Dict[str, str] = {}
    
    @classmethod
    def _get_template_path(cls) -> Path:
        """Get the templates directory path."""
        return Path(__file__).parent.parent / "templates"
    
    @classmethod
    def _load_template(cls, template_filename: str) -> str:
        """Load template from file with caching."""
        if template_filename in cls._template_cache:
            return cls._template_cache[template_filename]
        
        template_path = cls._get_template_path() / template_filename
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")
        
        template_content = template_path.read_text()
        cls._template_cache[template_filename] = template_content
        return template_content
    
    @classmethod
    def generate_script(
        cls,
        script_type: str,
        file_type: Optional[str] = None,
        function_code: str = "",
        conversion_type: Optional[str] = None,
        use_etl: bool = True
    ) -> str:
        """
        Generate script from template file.
        
        Args:
            script_type: Type of script (conversion, format_conversion, etl)
            file_type: File type for conversion (csv, xlsx)
            function_code: AI-generated function body code
            conversion_type: Type for format_conversion (csv_to_xlsx, xlsx_to_csv)
            use_etl: If True, use ETL template (with GCS), else use simple template
        """
        # Determine template key
        if script_type == "format_conversion":
            template_key = conversion_type or "csv_to_xlsx"
        else:
            # For conversion and etl, choose between ETL and simple
            if use_etl:
                template_key = file_type or "csv"
            else:
                template_key = f"{file_type or 'csv'}_simple"
        
        # Get template filename from map
        template_map = cls.TEMPLATE_MAP.get(script_type, {})
        template_filename = template_map.get(template_key)
        
        if not template_filename:
            raise ValueError(
                f"No template found for {script_type}/{template_key}. "
                f"Available: {list(template_map.keys())}"
            )
        
        # Load template from file
        template_str = cls._load_template(template_filename)
        
        # Render template with function code
        template = Template(template_str)
        return template.render(
            function_code=function_code or "# No transformation applied"
        )
