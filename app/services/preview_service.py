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
            try:
                df = pd.read_csv(
                    io.BytesIO(content),
                    skiprows=start_row,
                    nrows=sample_size
                )
            except Exception:
                df = pd.read_csv(
                    io.BytesIO(content),
                    dtype=str,
                    skiprows=start_row,
                    nrows=sample_size
                )
        elif file_extension in ['xlsx', 'xls']:
            try:
                df = pd.read_excel(
                    io.BytesIO(content),
                    skiprows=start_row,
                    nrows=sample_size
                )
            except Exception:
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


def _normalize_indentation(code: str) -> str:
    """
    Normalize indentation by removing common leading whitespace.
    
    Args:
        code: Code string to normalize
    
    Returns:
        Code with normalized indentation
    """
    lines = code.split('\n')
    # Find minimum indentation (excluding empty lines)
    non_empty_indents = [
        len(line) - len(line.lstrip())
        for line in lines if line.strip()
    ]
    
    if not non_empty_indents:
        return code
    
    min_indent = min(non_empty_indents)
    normalized_lines = [
        line[min_indent:] if line.strip() else ''
        for line in lines
    ]
    return '\n'.join(normalized_lines)


def _set_timeout(timeout_seconds: int) -> None:
    """Set execution timeout using SIGALRM if available."""
    if hasattr(signal, 'SIGALRM'):
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout_seconds)


def _cancel_timeout() -> None:
    """Cancel any pending timeout alarm."""
    if hasattr(signal, 'SIGALRM'):
        signal.alarm(0)


def _validate_result(result_df, warnings: List[str]) -> Tuple[pd.DataFrame, List[str]]:
    """
    Validate the transformation result and collect warnings.
    
    Args:
        result_df: The result from code execution
        warnings: List to append warnings to
    
    Returns:
        Tuple of (validated DataFrame, warnings)
    
    Raises:
        HTTPException: If result is invalid
    """
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
    
    if len(result_df) == 0:
        warnings.append("Transformation resulted in empty DataFrame")
    
    if len(result_df.columns) == 0:
        warnings.append("Transformation resulted in DataFrame with no columns")
    
    return result_df, warnings


def _create_safe_namespace(df_copy: pd.DataFrame) -> dict:
    """Create a restricted namespace for safe code execution."""
    return {
        'pd': pd,
        'np': np,
        'df': df_copy,
        '__builtins__': __builtins__,
        'open': None,
        'eval': None,
        'exec': None,
        'compile': None,
        '__import__': None,
        'input': None,
        'file': None,
    }


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
    df_copy = df.copy()
    safe_namespace = _create_safe_namespace(df_copy)
    
    try:
        _set_timeout(settings.PREVIEW_TIMEOUT_SECONDS)
        
        normalized_code = _normalize_indentation(function_code)
        wrapped_code = f"""
def transform(df):
{_indent_code(normalized_code, 1)}
    return df

result = transform(df)
"""
        
        exec(wrapped_code, safe_namespace)
        _cancel_timeout()
        
        result_df = safe_namespace.get('result')
        return _validate_result(result_df, warnings)
    
    except TimeoutException:
        raise HTTPException(
            status_code=400,
            detail=f"Code execution timed out after {settings.PREVIEW_TIMEOUT_SECONDS} seconds"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error executing transformation: {str(e)}"
        )
    finally:
        _cancel_timeout()


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
