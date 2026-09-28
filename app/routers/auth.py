"""
Authentication endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from app.database import get_db, User
from app.utils.auth import verify_password, get_password_hash, create_access_token

router = APIRouter()


class LoginRequest(BaseModel):
    """Login request model."""
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    """Register request model."""
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Login and registration response model."""
    access_token: str
    token_type: str = "bearer"
    email: str


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register(credentials: RegisterRequest, db: Session = Depends(get_db)):
    """
    Register endpoint - create a new user account and return JWT token.
    """
    if len(credentials.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long."
        )

    # Check if user already exists
    existing_user = db.query(User).filter(User.email == credentials.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists."
        )

    # Hash password and save new user
    hashed_password = get_password_hash(credentials.password)
    user = User(
        email=credentials.email,
        hashed_password=hashed_password
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Automatically generate access token upon signup
    access_token = create_access_token(data={"sub": user.email, "user_id": str(user.id)})

    return LoginResponse(
        access_token=access_token,
        email=user.email
    )


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """
    Login endpoint - authenticate user and return JWT token.
    """
    # Find user by email
    user = db.query(User).filter(User.email == credentials.email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify password
    if not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": user.email, "user_id": str(user.id)})
    
    return LoginResponse(
        access_token=access_token,
        email=user.email
    )
