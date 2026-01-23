"""
Script generation and management endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, List
from pathlib import Path
import os
import time
from app.database import get_db
from app.services.intent_classifier import IntentClassifier
from app.services.search_service import SearchService
from app.services.template_engine import TemplateEngine
from app.services.llm_prompt_builder import LLMPromptBuilder
from app.llm.gemini_client import GeminiClient
from app.llm.guards import validate_generated_code
from app.config import settings
from app.services import preview_service

router = APIRouter()


class ScriptRequest(BaseModel):
    """Script generation request."""
    user_input: str
    template_id: Optional[str] = None  # Manual template selection
    schema_info: Optional[Dict] = None
    file_type: Optional[str] = None


class SearchRequest(BaseModel):
    """Search approved scripts request."""
    query: str
    limit: int = 10


class SearchResult(BaseModel):
    """Individual search result."""
    repo_path: str
    similarity: float
    script_type: str
    description: Optional[str] = None


class SearchResponse(BaseModel):
    """Search response with matching scripts."""
    results: List[SearchResult]
    total: int


class ScriptResponse(BaseModel):
    """Script generation response."""
    script_type: str
    script_content: str
    reused: bool
    similarity: Optional[float] = None
    repo_path: Optional[str] = None
    config_content: Optional[str] = None
    usage_instructions: Optional[str] = None


class PreviewResponse(BaseModel):
    """Preview execution response."""
    before_data: List[Dict]
    after_data: List[Dict]
    before_columns: List[str]
    after_columns: List[str]
    rows_processed: int
    execution_time_ms: float
    warnings: Optional[List[str]] = None


def _get_config_and_instructions(script_type: str, conversion_type: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """Get sample config file and usage instructions for the script type."""
    # Determine config file name based on script type
    config_filename = None
    if script_type == "conversion":
        # ETL templates use specific config files
        config_filename = "csv_etl_template_config.json.example"  # Default to CSV
    elif script_type == "format_conversion":
        if conversion_type == "csv_to_xlsx":
            config_filename = "csvtoxlsx_config.json.example"
        elif conversion_type == "xlsx_to_csv":
            config_filename = "xlsxtocsv_config.json.example"
    
    # Load config file if applicable
    config_content = None
    if config_filename:
        template_dir = Path(__file__).parent.parent / "templates"
        config_path = template_dir / config_filename
        if config_path.exists():
            config_content = config_path.read_text()
    
    # Generate usage instructions
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

## Features:
- **file_mask**: Supports wildcards (*, ?) for flexible file matching
- **rename_file**: Automatically renames output files (useful for standardization)
- **GCS Integration**: ETL templates handle download, process, upload, and cleanup
- **Archive**: Processed files are archived to `processed/` folder before deletion
"""
    
    return config_content, usage_instructions


@router.post("/generate", response_model=ScriptResponse)
async def generate_script(
    request: ScriptRequest,
    db: Session = Depends(get_db)
):
    """Generate or reuse a script."""
    # Use template_id if provided, otherwise classify intent
    if request.template_id:
        # Map template_id to script_type
        template_to_script_type = {
            "csv_etl": "conversion",
            "xlsx_etl": "conversion",
            "xlsx_to_csv": "format_conversion",
            "csv_to_xlsx": "format_conversion"
        }
        script_type = template_to_script_type.get(request.template_id, "conversion")
        print(f"📋 Using selected template: {request.template_id} -> {script_type}")
    else:
        # Classify intent from user input
        script_type = IntentClassifier.classify(request.user_input)
        print(f"📋 Classified intent as: {script_type} for input: '{request.user_input}'")
    
    # Build intent summary
    search_service = SearchService()
    intent_summary = await search_service.build_intent_summary(
        request.user_input,
        request.schema_info
    )
    
    # Search for similar approved script
    similar_script = await search_service.search_similar(
        db,
        request.user_input,
        intent_summary,
        script_type
    )
    
    if similar_script:
        print(f"🔍 Search result: Found match with {similar_script['similarity']:.2%} similarity (threshold: 80%)")
    else:
        print(f"🔍 Search result: No match found (threshold: 80%)")
    
    # If similar script found, reuse it
    if similar_script:
        # Read script from repo
        repo_base = Path(settings.GITHUB_REPO_PATH)
        if not repo_base.is_absolute():
            # If relative, make it relative to project root
            backend_dir = Path(__file__).parent.parent.parent
            repo_base = backend_dir.parent / repo_base
        
        script_path = repo_base / similar_script["repo_path"]
        
        if script_path.exists():
            script_content = script_path.read_text()
            # Get config and usage instructions
            config_content, usage_instructions = _get_config_and_instructions(script_type)
            
            return ScriptResponse(
                script_type=script_type,
                script_content=script_content,
                reused=True,
                similarity=similar_script["similarity"],
                repo_path=similar_script["repo_path"],
                config_content=config_content,
                usage_instructions=usage_instructions
            )
        else:
            print(f"Warning: Script file not found at {script_path}")
    
    # Check if LLM generation is enabled for this type
    if script_type not in IntentClassifier.get_llm_enabled_types():
        raise HTTPException(
            status_code=400,
            detail=f"LLM generation not enabled for script type: {script_type}"
        )
    
    # Generate using LLM
    llm_client = GeminiClient()
    function_name = "convert" if script_type == "conversion" else "transform"
    
    prompt = LLMPromptBuilder.build_prompt(
        request.user_input,
        script_type,
        request.schema_info
    )
    
    generated_code = await llm_client.generate_code(prompt)
    
    print(f"📝 Generated code (full):\n{generated_code}")
    
    # Extract only the function definition from the generated code
    # The LLM might generate extra content, so we need to extract just the function
    function_start = generated_code.find(f"def {function_name}(")
    if function_start == -1:
        # Try without type hints
        function_start = generated_code.find(f"def {function_name}(")
    
    if function_start != -1:
        # Find the function definition
        function_code = generated_code[function_start:]
        
        # Remove markdown code fences if present
        function_code = function_code.replace('```python', '').replace('```', '').strip()
        
        # Extract just the function (find the end of the function)
        lines = function_code.split('\n')
        function_lines = []
        in_function = False
        indent_level = None
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Skip empty lines at the start
            if not in_function and not stripped:
                continue
            
            # Find function start
            if f"def {function_name}(" in line:
                in_function = True
                function_lines.append(line)
                # Determine base indentation (should be 0 for function definition)
                indent_level = len(line) - len(line.lstrip())
                continue
            
            if in_function:
                # Check if we've hit another top-level definition (end of function)
                if stripped and not line.startswith(' ') and not line.startswith('\t'):
                    # This is a new top-level definition, stop here
                    break
                
                # Check if line is part of function body
                current_indent = len(line) - len(line.lstrip())
                if stripped and current_indent <= indent_level and i > 0:
                    # This might be outside the function, but could be continuation
                    # Only break if it's clearly a new definition
                    if stripped.startswith('def ') or stripped.startswith('class '):
                        break
                
                function_lines.append(line)
        
        generated_code = '\n'.join(function_lines).strip()
        print(f"🧹 Extracted function:\n{generated_code}")
    else:
        print(f"⚠️ Warning: Could not find function definition, using full generated code")
    
    # Remove any remaining markdown code fences
    generated_code = generated_code.replace('```python', '').replace('```', '').strip()
    
    # Remove any import statements that might still be there
    lines = generated_code.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if not (stripped.startswith('import ') or stripped.startswith('from ')):
            cleaned_lines.append(line)
    generated_code = '\n'.join(cleaned_lines)
    
    # Fix common syntax errors: remove duplicate docstrings and fix indentation
    # Look for function definition and clean up docstrings
    if f"def {function_name}(" in generated_code:
        lines = generated_code.split('\n')
        cleaned_function_lines = []
        in_function = False
        docstring_count = 0
        seen_first_docstring = False
        
        for line in lines:
            if f"def {function_name}(" in line:
                in_function = True
                cleaned_function_lines.append(line)
                continue
            
            if in_function:
                stripped = line.strip()
                # Skip duplicate docstrings (keep only first one)
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    docstring_count += 1
                    if docstring_count == 1:
                        # Keep first docstring
                        cleaned_function_lines.append(line)
                    elif docstring_count == 2:
                        # Skip closing of first docstring if it's immediately followed by another
                        continue
                    else:
                        # Skip all subsequent docstrings
                        continue
                else:
                    cleaned_function_lines.append(line)
                    # If we see code after a docstring, we're past the first docstring
                    if docstring_count > 0 and stripped and not stripped.startswith('#'):
                        seen_first_docstring = True
                
                # Stop if we hit another top-level definition
                if stripped and not line.startswith(' ') and not line.startswith('\t'):
                    if stripped.startswith('def ') or stripped.startswith('class '):
                        break
            else:
                # Before function, skip everything
                continue
        
        if cleaned_function_lines:
            generated_code = '\n'.join(cleaned_function_lines)
            print(f"🔧 Fixed function (removed duplicates):\n{generated_code}")
    
    # Validate generated code
    is_valid, error_msg = validate_generated_code(generated_code, function_name)
    if not is_valid:
        print(f"❌ Validation failed: {error_msg}")
        print(f"   Generated code:\n{generated_code}")
        raise HTTPException(status_code=400, detail=f"Invalid generated code: {error_msg}")
    
    # Extract function body (the template expects just the body, indented)
    function_body = generated_code
    if f"def {function_name}" in generated_code:
        # Extract body from function definition
        lines = generated_code.split('\n')
        body_started = False
        body_lines = []
        in_docstring = False
        docstring_delimiter = None
        
        for line in lines:
            if f"def {function_name}" in line:
                body_started = True
                continue
            
            if body_started:
                stripped = line.lstrip()
                
                # Skip empty lines
                if not stripped:
                    body_lines.append('')
                    continue
                
                # Handle docstrings (skip them as they're already in the template)
                if not in_docstring:
                    # Check if this line starts a docstring
                    if stripped.startswith('"""') or stripped.startswith("'''"):
                        in_docstring = True
                        docstring_delimiter = '"""' if stripped.startswith('"""') else "'''"
                        # Check if docstring closes on the same line
                        if stripped.count(docstring_delimiter) >= 2:
                            in_docstring = False
                        continue
                else:
                    # We're inside a docstring, check if this line closes it
                    if docstring_delimiter in stripped:
                        in_docstring = False
                    continue
                
                # Add to body lines (we'll normalize indentation in next step)
                body_lines.append(line)
        
        if body_lines:
            function_body = '\n'.join(body_lines)
            print(f"📦 Extracted function body (raw):\n{function_body}")
    
    # Normalize indentation: find minimum indent and re-indent relative to it
    # This fixes cases where Gemini generates code with incorrect base indentation
    lines = function_body.split('\n')
    
    # First pass: find minimum indentation (ignoring empty lines)
    min_indent = None
    for line in lines:
        stripped = line.lstrip()
        if stripped:  # Ignore empty lines
            current_indent = len(line) - len(stripped)
            if min_indent is None or current_indent < min_indent:
                min_indent = current_indent
    
    # If no minimum found (all lines empty), default to 0
    if min_indent is None:
        min_indent = 0
    
    print(f"🔍 Detected minimum indentation: {min_indent} spaces")
    
    # Check if code has any control flow structures (if/for/while/try/with)
    # If not, all lines should be at base level (4 spaces)
    control_flow_keywords = ['if ', 'for ', 'while ', 'try:', 'except', 'else:', 'elif ', 'with ', 'def ']
    has_control_flow = any(
        any(keyword in line for keyword in control_flow_keywords)
        for line in lines if line.strip()
    )
    
    print(f"🔍 Has control flow structures: {has_control_flow}")
    
    # Second pass: normalize all lines
    final_lines = []
    for line in lines:
        stripped = line.lstrip()
        
        if not stripped:
            # Empty line
            final_lines.append('')
            continue
        
        # Calculate current indentation
        current_indent = len(line) - len(stripped)
        
        if not has_control_flow:
            # No control flow - all lines should be at base level (4 spaces)
            # This fixes Gemini's incorrect indentation
            new_indent = 4
        elif current_indent == min_indent:
            # This is a base-level line, normalize to exactly 4 spaces
            new_indent = 4
        else:
            # This line has more indentation than minimum (nested block)
            # Preserve relative indentation
            relative_indent = current_indent - min_indent
            new_indent = 4 + relative_indent
        
        final_lines.append(' ' * new_indent + stripped)
    
    indented_code = '\n'.join(final_lines)
    print(f"✅ Final indented code:\n{indented_code}")
    
    # Generate full script from template
    # Derive file_type and conversion_type from template_id
    file_type = request.file_type  # Default from request
    conversion_type = None
    
    if request.template_id:
        # Map template_id to file_type and conversion_type
        template_file_type_map = {
            "csv_etl": "csv",
            "xlsx_etl": "xlsx",
            "xlsx_to_csv": None,  # Uses conversion_type instead
            "csv_to_xlsx": None   # Uses conversion_type instead
        }
        template_conversion_type_map = {
            "xlsx_to_csv": "xlsx_to_csv",
            "csv_to_xlsx": "csv_to_xlsx"
        }
        file_type = template_file_type_map.get(request.template_id) or file_type
        conversion_type = template_conversion_type_map.get(request.template_id)
        print(f"📄 Template {request.template_id} -> file_type={file_type}, conversion_type={conversion_type}")
    elif script_type == "format_conversion":
        if "csv to xlsx" in request.user_input.lower():
            conversion_type = "csv_to_xlsx"
        elif "xlsx to csv" in request.user_input.lower():
            conversion_type = "xlsx_to_csv"
    
    script_content = TemplateEngine.generate_script(
        script_type,
        file_type,
        indented_code,
        conversion_type
    )
    
    # Write to _pending folder
    pending_dir = Path(settings.PENDING_PATH) / script_type
    pending_dir.mkdir(parents=True, exist_ok=True)
    
    script_filename = f"generated_{script_type}_{hash(request.user_input)}.py"
    script_path = pending_dir / script_filename
    script_path.write_text(script_content)
    
    # Get config and usage instructions
    config_content, usage_instructions = _get_config_and_instructions(script_type, conversion_type)
    
    return ScriptResponse(
        script_type=script_type,
        script_content=script_content,
        reused=False,
        repo_path=str(script_path.relative_to(settings.GITHUB_REPO_PATH)),
        config_content=config_content,
        usage_instructions=usage_instructions
    )


@router.post("/preview", response_model=PreviewResponse)
async def preview_transformation(
    file: UploadFile = File(...),
    function_code: str = Form(...),
    start_row: int = Form(0),
    sample_size: Optional[int] = Form(None)
):
    """
    Preview transformation on uploaded sample data.
    
    Args:
        file: CSV or XLSX file to preview
        function_code: Generated function body code
        start_row: Row to start sampling from (0-based)
        sample_size: Number of rows to sample (default from config)
    
    Returns:
        Before/after data comparison
    """
    start_time = time.time()
    
    # Validate file size
    file.file.seek(0, 2)  # Seek to end
    file_size_mb = file.file.tell() / (1024 * 1024)
    file.file.seek(0)  # Reset to start
    
    if file_size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File size ({file_size_mb:.1f}MB) exceeds maximum allowed size ({settings.MAX_UPLOAD_SIZE_MB}MB)"
        )
    
    # Read sample data
    df_before = preview_service.read_sample_data(file, start_row, sample_size)
    
    # Execute transformation
    df_after, warnings = preview_service.execute_transformation(df_before, function_code)
    
    # Calculate execution time
    execution_time_ms = (time.time() - start_time) * 1000
    
    # Convert to JSON
    before_json = preview_service.dataframe_to_json(df_before)
    after_json = preview_service.dataframe_to_json(df_after)
    
    return PreviewResponse(
        before_data=before_json['data'],
        after_data=after_json['data'],
        before_columns=before_json['columns'],
        after_columns=after_json['columns'],
        rows_processed=len(df_before),
        execution_time_ms=execution_time_ms,
        warnings=warnings if warnings else None
    )


class ExportRequest(BaseModel):
    """Export script request."""
    script_content: str
    user_input: str
    file_type: Optional[str] = None
    config_content: Optional[str] = None


@router.post("/export")
async def export_script(request: ExportRequest):
    """
    Export generated script as a downloadable Python file.
    If config is provided, returns a ZIP with both script and config.
    
    Args:
        request: Export request with script content and metadata
    
    Returns:
        Python file or ZIP archive with script and config
    """
    from app.utils.export_helpers import generate_python_file
    from fastapi.responses import Response
    from datetime import datetime
    import zipfile
    import io
    
    # Generate the Python file content
    python_content = generate_python_file(
        script_content=request.script_content,
        user_input=request.user_input,
        file_type=request.file_type
    )
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # If config exists, create a ZIP with both files
    if request.config_content:
        # Create ZIP in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add Python script
            zip_file.writestr(f"script_engine_{timestamp}.py", python_content)
            # Add config file
            zip_file.writestr("config.json", request.config_content)
        
        zip_buffer.seek(0)
        filename = f"script_engine_{timestamp}.zip"
        
        return Response(
            content=zip_buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    else:
        # Return just the Python file
        filename = f"script_engine_{timestamp}.py"
        
        return Response(
            content=python_content,
            media_type="text/x-python",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )


@router.post("/search", response_model=SearchResponse)
async def search_scripts(
    request: SearchRequest,
    db: Session = Depends(get_db)
):
    """
    Search for similar approved scripts.
    
    Args:
        request: Search query and limit
        db: Database session
    
    Returns:
        List of matching scripts with similarity scores
    """
    from app.services.search_service import SearchService
    
    search_service = SearchService()
    
    # Build intent summary from query
    intent_summary = await search_service.build_intent_summary(request.query, None)
    
    # Search for similar scripts (lowering threshold for search)
    similar_scripts = await search_service.search_all_similar(
        db,
        request.query,
        intent_summary,
        limit=request.limit
    )
    
    results = []
    for script in similar_scripts:
        results.append(SearchResult(
            repo_path=script.get("repo_path", ""),
            similarity=script.get("similarity", 0.0),
            script_type=script.get("script_type", "unknown"),
            description=script.get("description")
        ))
    
    return SearchResponse(
        results=results,
        total=len(results)
    )
