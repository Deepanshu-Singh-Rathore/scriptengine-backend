"""
LLM output validation guards.
"""
import re
from typing import Tuple


def validate_generated_code(code: str, expected_function: str) -> Tuple[bool, str]:
    """
    Validate generated code meets requirements.
    
    Returns:
        (is_valid, error_message)
    """
    # Must contain exactly one function
    function_pattern = rf'def\s+{expected_function}\s*\('
    matches = re.findall(function_pattern, code)
    
    if len(matches) == 0:
        return False, f"Code must contain function '{expected_function}'"
    
    if len(matches) > 1:
        return False, f"Code must contain exactly one function '{expected_function}'"
    
    # No imports allowed
    if re.search(r'^import\s+|^from\s+', code, re.MULTILINE):
        return False, "Code must not contain imports"
    # Check for dangerous IO operations (but allow to_csv/to_excel for format conversion)
    io_patterns = [
        r'open\s*\(',
        r'read_csv\s*\(',
        r'read_excel\s*\(',
        r'read_json\s*\(',
        r'to_json\s*\(',
        r'to_parquet\s*\(',
        r'to_sql\s*\(',
        r'\.read\s*\(',
        r'\.write\s*\(',
    ]
    for pattern in io_patterns:
        if re.search(pattern, code):
            return False, f"Code must not contain IO operations (found: {pattern})"
    
    # No config access
    if re.search(r'config|Config|CONFIG', code):
        return False, "Code must not access config"
    
    # Must return DataFrame (check for return statement)
    if not re.search(r'return\s+', code):
        return False, "Function must return a DataFrame"
    
    return True, ""
