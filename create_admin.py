import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.database import SessionLocal, User, init_db
from app.utils.auth import get_password_hash

def create_admin_user():
    """Create the initial admin user."""
    init_db()
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
