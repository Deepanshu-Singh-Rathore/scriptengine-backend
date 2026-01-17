"""
Helper functions for script generation.
"""
from pathlib import Path
from typing import Optional, Tuple
import re


def get_config_and_instructions(script_type: str, conversion_type: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Get sample config file and usage instructions for the script type."""
    config_filename = None
    if script_type == "conversion":
        config_filename = "csv_etl_template_config.json.example"
    elif script_type == "format_conversion":
        if conversion_type == "csv_to_xlsx":
            config_filename = "csvtoxlsx_config.json.example"
        elif conversion_type == "xlsx_to_csv":
            config_filename = "xlsxtocsv_config.json.example"
    
    config_content = None
    if config_filename:
        template_dir = Path(__file__).parent.parent / "templates"
        config_path = template_dir / config_filename
        if config_path.exists():
            config_content = config_path.read_text()
    
    usage_instructions = None
    if script_type in ["conversion", "format_conversion"]:
        usage_instructions = f"""# Usage Instructions

## Config File
This script requires a config file at: `/mnt/scratch/scripts/config.json`

### Config Fields:
- **file_mask**: Pattern to match files (e.g., "*.csv", "*.xlsx", "data_*.csv")
- **rename_file**: (Optional) New filename without extension. Leave empty ("") to keep original name.

### Example Config:
{config_content if config_content else '{"file_mask": "*.csv", "rename_file": "output"}'}

## Running the Script

### For ETL Templates (GCS):
```bash
python script.py <gcp_token> <vm_logfile> <gcp_bucket> <gcs_folder> <gcp_project> <gcs_partition>
```

### For Simple Templates (Local):
```bash
python script.py
# Reads from: input.csv (or input.xlsx)
# Writes to: output.csv (or output.xlsx)
```

## Features
- **file_mask**: Automatically processes all files matching the pattern
- **rename_file**: Optionally renames output files
"""
    
    return config_content, usage_instructions


def extract_function_body(code: str) -> str:
    """Extract function body from generated code."""
    lines = code.split('\n')
    function_lines = []
    in_function = False
    seen_first_docstring = False
    
    for line in lines:
        stripped = line.strip()
        
        if stripped.startswith('def convert(') or stripped.startswith('def transform('):
            in_function = True
            continue
        
        if in_function:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                if not seen_first_docstring:
                    seen_first_docstring = True
                    continue
            
            if stripped and not line.startswith(' ') and not line.startswith('\t'):
                break
            
            function_lines.append(line)
    
    return '\n'.join(function_lines)


def normalize_indentation(code: str) -> str:
    """Normalize code indentation to 4 spaces."""
    lines = code.split('\n')
    normalized_lines = []
    
    for line in lines:
        if not line.strip():
            normalized_lines.append('')
            continue
        
        leading_spaces = len(line) - len(line.lstrip())
        
        if leading_spaces % 4 == 0:
            normalized_lines.append(line)
        else:
            target_indent = (leading_spaces // 4) * 4
            normalized_lines.append(' ' * target_indent + line.lstrip())
    
    return '\n'.join(normalized_lines)


def detect_conversion_type(user_input: str) -> Optional[str]:
    """Detect conversion type from user input."""
    user_input_lower = user_input.lower()
    
    if 'csv' in user_input_lower and 'xlsx' in user_input_lower:
        if user_input_lower.index('csv') < user_input_lower.index('xlsx'):
            return 'csv_to_xlsx'
        else:
            return 'xlsx_to_csv'
    
    return None


def remove_duplicate_functions(code: str) -> str:
    """Remove duplicate function definitions."""
    lines = code.split('\n')
    seen_functions = set()
    result_lines = []
    current_function = None
    skip_until_next_def = False
    
    for line in lines:
        stripped = line.strip()
        
        if stripped.startswith('def '):
            match = re.match(r'def\s+(\w+)\s*\(', stripped)
            if match:
                func_name = match.group(1)
                
                if func_name in seen_functions:
                    skip_until_next_def = True
                    continue
                else:
                    seen_functions.add(func_name)
                    current_function = func_name
                    skip_until_next_def = False
        
        if not skip_until_next_def:
            result_lines.append(line)
    
    return '\n'.join(result_lines)
