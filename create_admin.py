"""
Script to create initial admin user in the database.
Run this once after database initialization.
"""
from app.database import SessionLocal, User
from app.utils.auth import get_password_hash

def create_admin_user():
    """Create the initial admin user."""
    db = SessionLocal()
    try:
        # Check if admin already exists
        existing_user = db.query(User).filter(User.email == "admin@scriptengine.com").first()
        if existing_user:
            print("Admin user already exists!")
            return
        
        # Create admin user
        admin = User(
            email="admin@scriptengine.com",
            hashed_password=get_password_hash("Jagat123@")
        )
        db.add(admin)
        db.commit()
        print("✓ Admin user created successfully!")
        print("  Email: admin@scriptengine.com")
        print("  Password: Jagat123@")
    except Exception as e:
        print(f"✗ Error creating admin user: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_admin_user()
