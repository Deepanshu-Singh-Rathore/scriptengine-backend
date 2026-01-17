"""
Preview service for executing transformations on sample data.
"""
import io
import signal
from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np
from fastapi import UploadFile, HTTPException

from app.config import settings


class TimeoutException(Exception):
    """Raised when code execution times out."""
    pass


def timeout_handler(signum, frame):
    """Signal handler for timeout."""
    raise TimeoutException("Code execution timed out")


def read_sample_data(
    file: UploadFile,
    start_row: int = 0,
    sample_size: Optional[int] = None
) -> pd.DataFrame:
    """
    Read sample data from uploaded file.
    
    Args:
        file: Uploaded CSV or XLSX file
        start_row: Row index to start sampling from (0-based)
        sample_size: Number of rows to read (default from config)
    
    Returns:
        DataFrame with sample data
    
    Raises:
        HTTPException: If file type is unsupported or reading fails
    """
    if sample_size is None:
        sample_size = settings.PREVIEW_SAMPLE_SIZE
    
    try:
        # Read file content
        content = file.file.read()
        file_extension = file.filename.split('.')[-1].lower()
        
        if file_extension == 'csv':
            df = pd.read_csv(
                io.BytesIO(content),
                dtype=str,
                skiprows=start_row,
                nrows=sample_size
            )
        elif file_extension in ['xlsx', 'xls']:
            df = pd.read_excel(
                io.BytesIO(content),
                dtype=str,
                skiprows=start_row,
                nrows=sample_size
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_extension}. Only CSV and XLSX are supported."
            )
        
        return df
    
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=400,
            detail=f"Error reading file: {str(e)}"
        )


def execute_transformation(
    df: pd.DataFrame,
    function_code: str
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Safely execute transformation code on DataFrame.
    
    Args:
        df: Input DataFrame
        function_code: Generated function body code
    
    Returns:
        Tuple of (transformed DataFrame, list of warnings)
    
    Raises:
        HTTPException: If code execution fails
    """
    warnings = []
    
    # Create a copy to avoid modifying original
    df_copy = df.copy()
    
    # Create safe namespace with restricted globals
    # We allow builtins but restrict dangerous modules via globals
    safe_namespace = {
        'pd': pd,
        'np': np,
        'df': df_copy,
        '__builtins__': __builtins__,
        # Block dangerous modules
        'open': None,
        'eval': None,
        'exec': None,
        'compile': None,
        '__import__': None,
        'input': None,
        'file': None,
    }
    
    try:
        # Set timeout alarm (Unix only)
        if hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(settings.PREVIEW_TIMEOUT_SECONDS)
        
        # Normalize indentation of function_code
        # Remove common leading whitespace
        lines = function_code.split('\n')
        # Find minimum indentation (excluding empty lines)
        min_indent = float('inf')
        for line in lines:
            if line.strip():  # Skip empty lines
                indent = len(line) - len(line.lstrip())
                min_indent = min(min_indent, indent)
        
        # Remove the minimum indentation from all lines
        if min_indent < float('inf'):
            normalized_lines = []
            for line in lines:
                if line.strip():  # Non-empty line
                    normalized_lines.append(line[min_indent:])
                else:  # Empty line
                    normalized_lines.append('')
            function_code = '\n'.join(normalized_lines)
        
        # Wrap code in a function and execute
        wrapped_code = f"""
def transform(df):
{_indent_code(function_code, 1)}
    return df

result = transform(df)
"""
        
        # Execute code in restricted namespace
        exec(wrapped_code, safe_namespace)
        
        # Cancel timeout
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
        
        # Get result
        result_df = safe_namespace.get('result')
        
        if result_df is None:
            raise HTTPException(
                status_code=400,
                detail="Transformation did not return a DataFrame"
            )
        
        if not isinstance(result_df, pd.DataFrame):
            raise HTTPException(
                status_code=400,
                detail=f"Transformation returned {type(result_df).__name__} instead of DataFrame"
            )
        
        # Check for common issues
        if len(result_df) == 0:
            warnings.append("Transformation resulted in empty DataFrame")
        
        if len(result_df.columns) == 0:
            warnings.append("Transformation resulted in DataFrame with no columns")
        
        return result_df, warnings
    
    except TimeoutException:
        raise HTTPException(
            status_code=400,
            detail=f"Code execution timed out after {settings.PREVIEW_TIMEOUT_SECONDS} seconds"
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=400,
            detail=f"Error executing transformation: {str(e)}"
        )
    finally:
        # Always cancel timeout
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)


def dataframe_to_json(df: pd.DataFrame, max_rows: Optional[int] = None) -> Dict:
    """
    Convert DataFrame to JSON-serializable format.
    
    Args:
        df: DataFrame to convert
        max_rows: Maximum number of rows to include (None for all)
    
    Returns:
        Dict with columns and data
    """
    if max_rows is not None:
        df = df.head(max_rows)
    
    # Replace NaN with None for JSON serialization
    df_clean = df.replace({pd.NA: None, np.nan: None})
    
    return {
        'columns': df_clean.columns.tolist(),
        'data': df_clean.to_dict('records')
    }


def _indent_code(code: str, levels: int = 1) -> str:
    """
    Indent code by specified number of levels (4 spaces each).
    
    Args:
        code: Code to indent
        levels: Number of indentation levels
    
    Returns:
        Indented code
    """
    indent = '    ' * levels
    lines = code.split('\n')
    return '\n'.join(indent + line if line.strip() else line for line in lines)
