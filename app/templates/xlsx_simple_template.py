import pandas as pd

def read_xlsx():
    df = pd.read_excel('input.xlsx')
    return df

def convert(df):
{{ function_code }}
    return df

def write_xlsx(df):
    df.to_excel('output.xlsx', index=False)

def preview(df_before, df_after):
    print(f"Rows: {len(df_before)} -> {len(df_after)}")
    print(f"Columns: {list(df_before.columns)} -> {list(df_after.columns)}")

def main():
    df = read_xlsx()
    df_before = df.copy()
    df = convert(df)
    write_xlsx(df)
    preview(df_before, df)

if __name__ == "__main__":
    main()
