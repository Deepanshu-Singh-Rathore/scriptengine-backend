# Approved Scripts Repository

This repository contains approved, reusable ETL and format-conversion scripts.

## Structure

```
approved-scripts/
├── _pending/                 # AI-generated, NOT reusable
│   ├── conversion/
│   ├── etl/
│   └── format_conversion/
│
├── conversion/               # approved conversion scripts
│   ├── csv/
│   │   ├── example_script.py
│   │   └── metadata.json
│   └── xlsx/
│
├── etl/                      # approved ETL pipeline scripts
│   ├── multi_format_etl/
│   │   ├── script.py
│   │   ├── metadata.json
│   │   └── config.json.example
│   └── csv_etl/
│
└── format_conversion/        # approved format conversion scripts
    ├── csv_to_xlsx/
    │   ├── example_script.py
    │   └── metadata.json
    └── xlsx_to_csv/
```

## Rules

- Tool reads everything in approved folders
- Tool reuses only approved folders (not `_pending`)
- `_pending` is never indexed
- Support team manually moves scripts out of `_pending` after approval
- Multiple scripts can exist in each category folder

## Metadata Format

Each script folder should contain:
- `*.py` - The script file (can be named `script.py`, `example_script.py`, etc.)
- `metadata.json` - Script metadata for search and reuse
- `config.json.example` (optional) - Example configuration file

### Metadata Structure

```json
{
  "script_type": "etl|conversion|format_conversion",
  "source_format": "csv|xlsx|multi|...",
  "target_format": "csv|xlsx|...",
  "domain": "domain_name",
  "intent": ["intent1", "intent2", ...],
  "description": "Description of what the script does",
  "tags": ["tag1", "tag2", ...],
  "repo_path": "relative/path/to/script.py",
  "config_path": "relative/path/to/config.json.example",
  "version": "1.0.0"
}
```

## Adding New Scripts

1. Create a new folder under the appropriate category:
   - `conversion/` - for data transformation within same format
   - `etl/` - for full ETL pipelines with GCS operations
   - `format_conversion/` - for converting between file formats

2. Place your script file in the folder

3. Create `metadata.json` with script metadata

4. Optionally create `config.json.example` showing expected configuration

5. Run the ingestion pipeline to index the script in the database