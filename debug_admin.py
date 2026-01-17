"""
Script to check which schema the user exists in and create if missing.
This helps debug schema mismatch issues between environments.
"""
from app.database import SessionLocal, User, engine
from app.utils.auth import get_password_hash
from app.config import settings
from sqlalchemy import text

def check_and_create_admin():
    """Check for admin user in all schemas and create if missing."""
    db = SessionLocal()
    
    try:
        print("=" * 80)
        print("ADMIN USER DEBUG")
        print("=" * 80)
        print(f"Current schema setting: {settings.POSTGRES_SCHEMA}")
        print()
        
        # Check what schemas exist
        print("Checking existing schemas...")
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name NOT IN ('pg_catalog', 'information_schema')
                ORDER BY schema_name
            """))
            schemas = [row[0] for row in result]
            print(f"Available schemas: {', '.join(schemas)}")
            print()
        
        # Check for users table in each schema
        print("Checking for users table in each schema...")
        for schema in schemas:
            with engine.connect() as conn:
                result = conn.execute(text(f"""
                    SELECT COUNT(*) 
                    FROM information_schema.tables 
                    WHERE table_schema = '{schema}' 
                    AND table_name = 'users'
                """))
                count = result.scalar()
                if count > 0:
                    print(f"  ✓ users table exists in '{schema}' schema")
                    
                    # Check for admin user in this schema
                    result = conn.execute(text(f"""
                        SELECT email, created_at 
                        FROM {schema}.users 
                        WHERE email = 'admin@scriptengine.com'
                    """))
                    user = result.first()
                    if user:
                        print(f"    ✓ Admin user found! Created at: {user[1]}")
                    else:
                        print(f"    ✗ Admin user NOT found in this schema")
                else:
                    print(f"  ✗ users table does NOT exist in '{schema}' schema")
        
        print()
        print(f"Attempting to create/verify admin in '{settings.POSTGRES_SCHEMA}' schema...")
        
        # Try to create admin in the configured schema
        existing_user = db.query(User).filter(User.email == "admin@scriptengine.com").first()
        if existing_user:
            print(f"✓ Admin user already exists in '{settings.POSTGRES_SCHEMA}' schema!")
            print(f"  Email: {existing_user.email}")
            print(f"  Created: {existing_user.created_at}")
        else:
            print(f"✗ Admin user NOT found in '{settings.POSTGRES_SCHEMA}' schema")
            print("  Creating admin user...")
            admin = User(
                email="admin@scriptengine.com",
                hashed_password=get_password_hash("Jagat123@")
            )
            db.add(admin)
            db.commit()
            print("✓ Admin user created successfully!")
            print("  Email: admin@scriptengine.com")
            print("  Password: Jagat123@")
        
        print("=" * 80)
        
    except Exception as e:
        print(f"✗ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    check_and_create_admin()
