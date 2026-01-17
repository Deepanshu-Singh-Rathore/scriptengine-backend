"""
Test Supabase database connection.
"""
import psycopg2
from dotenv import load_dotenv
import os

# Load environment variables from .env
load_dotenv()

# Fetch variables
USER = os.getenv("POSTGRES_USER", "postgres")
PASSWORD = os.getenv("POSTGRES_PASSWORD")
HOST = os.getenv("POSTGRES_HOST")
PORT = os.getenv("POSTGRES_PORT", "5432")
DBNAME = os.getenv("POSTGRES_DB", "postgres")

# Connect to the database
try:
    connection = psycopg2.connect(
        user=USER,
        password=PASSWORD,
        host=HOST,
        port=PORT,
        dbname=DBNAME
    )
    print("✓ Connection successful!")
    
    # Create a cursor to execute SQL queries
    cursor = connection.cursor()
    
    # Test query
    cursor.execute("SELECT NOW();")
    result = cursor.fetchone()
    print(f"✓ Current Time: {result[0]}")
    
    # Check if pgvector extension exists
    cursor.execute("SELECT * FROM pg_extension WHERE extname = 'vector';")
    vector_ext = cursor.fetchone()
    if vector_ext:
        print("✓ pgvector extension is installed")
    else:
        print("⚠ pgvector extension not found - you may need to enable it in Supabase")
    
    # List existing tables
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
    """)
    tables = cursor.fetchall()
    print(f"\n✓ Existing tables: {[t[0] for t in tables] if tables else 'None'}")

    # Close the cursor and connection
    cursor.close()
    connection.close()
    print("\n✓ Connection closed successfully")

except Exception as e:
    print(f"✗ Failed to connect: {e}")
