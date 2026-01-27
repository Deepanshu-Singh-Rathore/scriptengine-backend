"""
Script generation and management endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, List, Tuple
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

# Constants for markdown code fence removal
MARKDOWN_PYTHON_FENCE = '```python'
MARKDOWN_FENCE_END = '```'


class ScriptRequest(BaseModel):
    """Script generation request."""
    user_input: str
    template_id: Optional[str] = None  # Manual template selection
    schema_info: Optional[Dict] = None
    file_type: Optional[str] = None


class SearchRequest(BaseModel):
    """Search approved scripts request."""
    query: str
    script_type: Optional[str] = None  # Filter by script type directly
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


def _classify_script_type(request: ScriptRequest) -> str:
    """Classify script type from request template_id or user input."""
    if request.template_id:
        template_to_script_type = {
            "csv_etl": "conversion",
            "xlsx_etl": "conversion",
            "xlsx_to_csv": "format_conversion",
            "csv_to_xlsx": "format_conversion"
        }
        script_type = template_to_script_type.get(request.template_id, "conversion")
        print(f"📋 Using selected template: {request.template_id} -> {script_type}")
    else:
        script_type = IntentClassifier.classify(request.user_input)
        print(f"📋 Classified intent as: {script_type} for input: '{request.user_input}'")
    return script_type


async def _try_reuse_existing_script(
    db: Session,
    request: ScriptRequest,
    script_type: str
) -> Optional[ScriptResponse]:
    """Search for and return an existing similar script if found."""
    search_service = SearchService()
    intent_summary = search_service.build_intent_summary(
        request.user_input,
        request.schema_info
    )
    
    similar_script = await search_service.search_similar(
        db,
        request.user_input,
        intent_summary,
        script_type
    )
    
    if similar_script:
        print(f"🔍 Search result: Found match with {similar_script['similarity']:.2%} similarity (threshold: 80%)")
    else:
        print("🔍 Search result: No match found (threshold: 80%)")
        return None
    
    # Read script from repo
    repo_base = Path(settings.GITHUB_REPO_PATH)
    if not repo_base.is_absolute():
        backend_dir = Path(__file__).parent.parent.parent
        repo_base = backend_dir.parent / repo_base
    
    script_path = repo_base / similar_script["repo_path"]
    
    if not script_path.exists():
        print(f"Warning: Script file not found at {script_path}")
        return None
    
    script_content = script_path.read_text()
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


def _is_function_end(line: str, stripped: str) -> bool:
    """Check if a line marks the end of a function definition."""
    # Non-empty line at column 0 (no indentation) ends the function
    if stripped and not line.startswith(' ') and not line.startswith('\t'):
        return True
    # New def/class at column 0 ends the function
    if stripped.startswith('def ') or stripped.startswith('class '):
        indent_level = len(line) - len(line.lstrip())
        if indent_level == 0:
            return True
    return False


def _process_function_lines(lines: list, function_name: str) -> list:
    """Process lines and extract those belonging to the function."""
    function_lines = []
    in_function = False
    
    for line in lines:
        stripped = line.strip()
        
        # Skip leading empty lines before function starts
        if not in_function and not stripped:
            continue
        
        # Start capturing at function definition
        if f"def {function_name}(" in line:
            in_function = True
            function_lines.append(line)
            continue
        
        # Once in function, check for end or add line
        if in_function:
            if _is_function_end(line, stripped):
                break
            function_lines.append(line)
    
    return function_lines


def _extract_function_from_code(generated_code: str, function_name: str) -> str:
    """Extract the function definition from generated code."""
    function_start = generated_code.find(f"def {function_name}(")
    if function_start == -1:
        print("⚠️ Warning: Could not find function definition, using full generated code")
        return generated_code.replace(MARKDOWN_PYTHON_FENCE, '').replace(MARKDOWN_FENCE_END, '').strip()
    
    function_code = generated_code[function_start:]
    function_code = function_code.replace(MARKDOWN_PYTHON_FENCE, '').replace(MARKDOWN_FENCE_END, '').strip()
    
    lines = function_code.split('\n')
    function_lines = _process_function_lines(lines, function_name)
    
    result = '\n'.join(function_lines).strip()
    print(f"🧹 Extracted function:\n{result}")
    return result


def _remove_imports(generated_code: str) -> str:
    """Remove import statements from generated code."""
    lines = generated_code.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if not (stripped.startswith('import ') or stripped.startswith('from ')):
            cleaned_lines.append(line)
    return '\n'.join(cleaned_lines)


def _is_docstring_start(stripped: str) -> bool:
    """Check if a line starts a docstring."""
    return stripped.startswith('"""') or stripped.startswith("'''")


def _is_new_definition_at_root(line: str, stripped: str) -> bool:
    """Check if line is a new def/class at root indentation level."""
    if not stripped:
        return False
    if line.startswith(' ') or line.startswith('\t'):
        return False
    return stripped.startswith('def ') or stripped.startswith('class ')


def _clean_duplicate_docstrings(generated_code: str, function_name: str) -> str:
    """Remove duplicate docstrings from function definition."""
    if f"def {function_name}(" not in generated_code:
        return generated_code
    
    lines = generated_code.split('\n')
    cleaned_function_lines = []
    in_function = False
    docstring_count = 0
    
    for line in lines:
        stripped = line.strip()
        
        # Handle function definition start
        if f"def {function_name}(" in line:
            in_function = True
            cleaned_function_lines.append(line)
            continue
        
        if not in_function:
            continue
        
        # Handle docstrings - keep only the first one
        if _is_docstring_start(stripped):
            docstring_count += 1
            if docstring_count <= 1:
                cleaned_function_lines.append(line)
            continue
        
        cleaned_function_lines.append(line)
        
        # Stop at new definition at root level
        if _is_new_definition_at_root(line, stripped):
            break
    
    if cleaned_function_lines:
        result = '\n'.join(cleaned_function_lines)
        print(f"🔧 Fixed function (removed duplicates):\n{result}")
        return result
    return generated_code


class _DocstringTracker:
    """Track docstring state while parsing function bodies."""
    
    def __init__(self):
        self.in_docstring = False
        self.delimiter = None
    
    def check_docstring_start(self, stripped: str) -> bool:
        """Check if line starts a docstring. Returns True if line should be skipped."""
        if self.in_docstring:
            return False
        if not (stripped.startswith('"""') or stripped.startswith("'''")):
            return False
        
        self.in_docstring = True
        self.delimiter = '"""' if stripped.startswith('"""') else "'''"
        # Check for single-line docstring
        if stripped.count(self.delimiter) >= 2:
            self.in_docstring = False
        return True
    
    def check_docstring_end(self, stripped: str) -> bool:
        """Check if line ends a docstring. Returns True if line should be skipped."""
        if not self.in_docstring:
            return False
        if self.delimiter in stripped:
            self.in_docstring = False
        return True


def _process_function_body_line(
    line: str,
    tracker: _DocstringTracker
) -> tuple[bool, str]:
    """
    Process a single line when extracting function body.
    
    Returns:
        (should_add, content): Whether to add line and what content to add
    """
    stripped = line.lstrip()
    
    # Empty lines are preserved
    if not stripped:
        return True, ''
    
    # Skip docstring lines
    if tracker.check_docstring_start(stripped):
        return False, ''
    if tracker.check_docstring_end(stripped):
        return False, ''
    
    return True, line


def _extract_function_body(generated_code: str, function_name: str) -> str:
    """Extract the body of a function, excluding docstrings."""
    if f"def {function_name}" not in generated_code:
        return generated_code
    
    lines = generated_code.split('\n')
    body_lines = []
    body_started = False
    tracker = _DocstringTracker()
    
    for line in lines:
        # Find function definition to start capturing
        if not body_started:
            if f"def {function_name}" in line:
                body_started = True
            continue
        
        should_add, content = _process_function_body_line(line, tracker)
        if should_add:
            body_lines.append(content)
    
    if body_lines:
        result = '\n'.join(body_lines)
        print(f"📦 Extracted function body (raw):\n{result}")
        return result
    return generated_code


def _normalize_indentation(function_body: str) -> str:
    """Normalize indentation to consistent 4-space indentation."""
    lines = function_body.split('\n')
    
    # Find minimum indentation (ignoring empty lines)
    min_indent = None
    for line in lines:
        stripped = line.lstrip()
        if stripped:
            current_indent = len(line) - len(stripped)
            if min_indent is None or current_indent < min_indent:
                min_indent = current_indent
    
    if min_indent is None:
        min_indent = 0
    
    print(f"🔍 Detected minimum indentation: {min_indent} spaces")
    
    # Check for control flow structures
    control_flow_keywords = ['if ', 'for ', 'while ', 'try:', 'except', 'else:', 'elif ', 'with ', 'def ']
    has_control_flow = any(
        any(keyword in line for keyword in control_flow_keywords)
        for line in lines if line.strip()
    )
    
    print(f"🔍 Has control flow structures: {has_control_flow}")
    
    # Normalize all lines
    final_lines = []
    for line in lines:
        stripped = line.lstrip()
        
        if not stripped:
            final_lines.append('')
            continue
        
        current_indent = len(line) - len(stripped)
        
        if not has_control_flow:
            new_indent = 4
        elif current_indent == min_indent:
            new_indent = 4
        else:
            relative_indent = current_indent - min_indent
            new_indent = 4 + relative_indent
        
        final_lines.append(' ' * new_indent + stripped)
    
    result = '\n'.join(final_lines)
    print(f"✅ Final indented code:\n{result}")
    return result


def _process_generated_code(generated_code: str, function_name: str) -> str:
    """Process LLM-generated code: extract, clean, and normalize."""
    print(f"📝 Generated code (full):\n{generated_code}")
    
    # Step 1: Extract function definition
    extracted = _extract_function_from_code(generated_code, function_name)
    
    # Step 2: Remove markdown fences and imports
    cleaned = extracted.replace(MARKDOWN_PYTHON_FENCE, '').replace(MARKDOWN_FENCE_END, '').strip()
    cleaned = _remove_imports(cleaned)
    
    # Step 3: Clean duplicate docstrings
    cleaned = _clean_duplicate_docstrings(cleaned, function_name)
    
    return cleaned


def _get_file_type_and_conversion(request: ScriptRequest, script_type: str) -> Tuple[Optional[str], Optional[str]]:
    """Derive file_type and conversion_type from request."""
    file_type = request.file_type
    conversion_type = None
    
    if request.template_id:
        template_file_type_map = {
            "csv_etl": "csv",
            "xlsx_etl": "xlsx",
            "xlsx_to_csv": None,
            "csv_to_xlsx": None
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
    
    return file_type, conversion_type


def _save_script_to_pending(script_content: str, script_type: str, user_input: str) -> Optional[Path]:
    """Save generated script to pending folder if storage is enabled."""
    if not settings.STORE_GENERATED_SCRIPTS:
        print("⏭️ Script storage disabled (STORE_GENERATED_SCRIPTS=false)")
        return None
    
    pending_dir = Path(settings.PENDING_PATH) / script_type
    pending_dir.mkdir(parents=True, exist_ok=True)
    
    script_filename = f"generated_{script_type}_{hash(user_input)}.py"
    script_path = pending_dir / script_filename
    script_path.write_text(script_content)
    print(f"💾 Script saved to: {script_path}")
    return script_path


@router.post("/generate", response_model=ScriptResponse)
async def generate_script(
    request: ScriptRequest,
    db: Session = Depends(get_db)
):
    """Generate or reuse a script."""
    # Classify script type
    script_type = _classify_script_type(request)
    
    # Try to reuse existing script
    reused_response = await _try_reuse_existing_script(db, request, script_type)
    if reused_response:
        return reused_response
    
    # Check if LLM generation is enabled
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
    
    # Process generated code
    cleaned_code = _process_generated_code(generated_code, function_name)
    
    # Validate generated code
    is_valid, error_msg = validate_generated_code(cleaned_code, function_name)
    if not is_valid:
        print(f"❌ Validation failed: {error_msg}")
        print(f"   Generated code:\n{cleaned_code}")
        raise HTTPException(status_code=400, detail=f"Invalid generated code: {error_msg}")
    
    # Extract function body and normalize indentation
    function_body = _extract_function_body(cleaned_code, function_name)
    indented_code = _normalize_indentation(function_body)
    
    # Get file type and conversion type
    file_type, conversion_type = _get_file_type_and_conversion(request, script_type)
    
    # Generate full script from template
    script_content = TemplateEngine.generate_script(
        script_type,
        file_type,
        indented_code,
        conversion_type
    )
    
    # Save to pending folder
    script_path = _save_script_to_pending(script_content, script_type, request.user_input)
    
    # Get config and usage instructions
    config_content, usage_instructions = _get_config_and_instructions(script_type, conversion_type)
    
    return ScriptResponse(
        script_type=script_type,
        script_content=script_content,
        reused=False,
        repo_path=str(script_path.relative_to(settings.GITHUB_REPO_PATH)) if script_path else None,
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
    intent_summary = search_service.build_intent_summary(request.query, None)
    
    # Search for similar scripts (filter by script_type if provided)
    similar_scripts = await search_service.search_all_similar(
        db,
        request.query,
        intent_summary,
        limit=request.limit,
        script_type=request.script_type  # Pass directly
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
