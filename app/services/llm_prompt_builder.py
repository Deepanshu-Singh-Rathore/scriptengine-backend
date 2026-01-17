"""
LLM prompt builder for code generation.
"""
from typing import Dict, Optional, List


class LLMPromptBuilder:
    """Builder for LLM prompts."""
    
    @staticmethod
    def build_prompt(
        intent: str,
        script_type: str,
        schema_info: Optional[Dict] = None,
        approved_snippets: Optional[List[str]] = None
    ) -> str:
        """Build prompt for LLM code generation."""
        function_name = "convert" if script_type == "conversion" else "transform"
        
        prompt_parts = [
            f"Generate ONLY a Python function (nothing else).",
            f"\nIntent: {intent}",
            f"\nScript Type: {script_type}",
        ]
        
        if schema_info:
            prompt_parts.append("\nSchema Information:")
            if "columns" in schema_info:
                prompt_parts.append(f"  - Columns: {', '.join(schema_info['columns'])}")
            if "data_types" in schema_info:
                prompt_parts.append(f"  - Data types: {schema_info['data_types']}")
        
        prompt_parts.extend([
            "\nCRITICAL REQUIREMENTS:",
            "  - Generate ONLY the function definition, nothing else",
            "  - Function must be named exactly: {function_name}",
            "  - Function signature: def {function_name}(df: pd.DataFrame) -> pd.DataFrame:",
            "  - Function must take exactly one parameter: df (DataFrame)",
            "  - Function must return a DataFrame",
            "  - DO NOT include any import statements",
            "  - DO NOT include any other code outside the function",
            "  - DO NOT include markdown code fences (```)",
            "  - DO NOT include any comments outside the function",
            "  - DO NOT include any other functions or classes",
            "  - Only the function definition with its body",
            "\nExample (generate similar format):",
            f"def {function_name}(df: pd.DataFrame) -> pd.DataFrame:",
            "    # Transformation logic here",
            "    return df",
            "\nGenerate ONLY the function definition now:"
        ])
        
        return "\n".join(prompt_parts).replace("{function_name}", function_name)
