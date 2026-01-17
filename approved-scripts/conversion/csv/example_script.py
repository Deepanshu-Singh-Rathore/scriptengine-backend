import pandas as pd

def read_csv():
    df = pd.read_csv('input.csv')
    return df

def convert(df):
    # Normalize column names
    df.columns = df.columns.str.strip().str.lower()
    
    # Handle null values
    df = df.fillna('')
    
    # Type casting for numeric columns
    numeric_cols = df.select_dtypes(include=['object']).columns
    for col in numeric_cols:
        try:
            df[col] = pd.to_numeric(df[col], errors='ignore')
        except:
            pass
    
    return df

def write_csv(df):
    df.to_csv('output.csv', index=False)

def preview(df_before, df_after):
    print(f"Rows: {len(df_before)} -> {len(df_after)}")
    print(f"Columns: {list(df_before.columns)} -> {list(df_after.columns)}")

def main():
    df = read_csv()
    df_before = df.copy()
    df = convert(df)
    write_csv(df)
    preview(df_before, df)

if __name__ == "__main__":
    main()
