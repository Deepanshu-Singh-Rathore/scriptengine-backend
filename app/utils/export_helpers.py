"""
Export utilities for generating downloadable script files.
"""
from datetime import datetime


def generate_python_file(script_content: str, user_input: str, file_type: str = None) -> str:
    """
    Generate a standalone Python script with proper headers and CLI support.
    
    Args:
        script_content: The transformation function code
        user_input: User's original request
        file_type: Type of file (csv, xlsx, etc.)
    
    Returns:
        Complete Python script as string
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Extract just the function body if it includes the def line
    lines = script_content.strip().split('\n')
    function_body = []
    in_function = False
    
    for line in lines:
        if line.strip().startswith('def ') and ('transform' in line or 'convert' in line):
            in_function = True
            function_body.append(line)
        elif in_function:
            function_body.append(line)
    
    # If we found a function, use it; otherwise use the whole content
    if function_body:
        function_code = '\n'.join(function_body)
    else:
        # Wrap the content in a function if it's not already
        function_code = f"def transform(df):\n    {script_content.replace(chr(10), chr(10) + '    ')}\n    return df"
    
    file_type_str = f" ({file_type.upper()})" if file_type else ""
    
    template = f'''"""
Script Engine - Generated Transformation Script
Generated: {timestamp}
User Request: {user_input}
File Type{file_type_str}

Usage:
    python script.py input.csv output.csv
    
    Or import in your own script:
    from script import transform
    df = transform(your_dataframe)
"""

import pandas as pd
import numpy as np
import sys
from datetime import datetime


{function_code}


def main():
    """Command-line interface for the transformation."""
    if len(sys.argv) != 3:
        print("Usage: python script.py input.csv output.csv")
        print("\\nExample:")
        print("  python script.py data.csv transformed_data.csv")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    try:
        # Read input file
        print(f"Reading {{input_file}}...")
        if input_file.endswith('.csv'):
            df = pd.read_csv(input_file)
        elif input_file.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(input_file)
        else:
            print("Error: Unsupported file format. Use .csv or .xlsx")
            sys.exit(1)
        
        print(f"Loaded {{len(df)}} rows")
        
        # Apply transformation
        print("Applying transformation...")
        result = transform(df)
        
        # Save output
        print(f"Saving to {{output_file}}...")
        if output_file.endswith('.csv'):
            result.to_csv(output_file, index=False)
        elif output_file.endswith(('.xlsx', '.xls')):
            result.to_excel(output_file, index=False)
        else:
            print("Error: Unsupported output format. Use .csv or .xlsx")
            sys.exit(1)
        
        print(f"✓ Success! Processed {{len(result)}} rows")
        print(f"✓ Output saved to {{output_file}}")
        
    except FileNotFoundError:
        print(f"Error: File '{{input_file}}' not found")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {{str(e)}}")
        sys.exit(1)


if __name__ == "__main__":
    main()
'''
    
    return template
