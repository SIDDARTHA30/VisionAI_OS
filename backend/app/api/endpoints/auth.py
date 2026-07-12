from datetime import datetime, timezone
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User, UserRole
from app.models.history import ActivityLog
from app.schemas.user import Token, UserCreate, UserResponse

router = APIRouter()
logger = logging.getLogger("auth_api")


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """User signup endpoint. Creates a new user if the email is not registered."""
    result = await db.execute(select(User).where(User.email == user_in.email))
    user = result.scalars().first()
    
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists."
        )

    # First user registered gets Admin role automatically
    users_count_result = await db.execute(select(User))
    users_count = len(users_count_result.scalars().all())
    assigned_role = UserRole.ADMIN if users_count == 0 else user_in.role

    hashed_password = get_password_hash(user_in.password)
    db_user = User(
        name=user_in.name,
        email=user_in.email,
        password_hash=hashed_password,
        role=assigned_role,
        is_active=True,
        is_verified=False
    )
    
    db.add(db_user)
    await db.flush()  # flush to get the id
    
    # Log user creation activity
    log = ActivityLog(
        user_id=db_user.id,
        action="signup",
        details=f"User registered with email: {db_user.email} and role: {db_user.role}"
    )
    db.add(log)
    await db.commit()
    await db.refresh(db_user)
    
    logger.info(f"Registered user: {db_user.email} as {db_user.role}")
    return db_user


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """OAuth2 password flow login endpoint. Verifies email/password and issues JWTs."""
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalars().first()
    
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password"
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )

    # Update last login time
    user.last_login = datetime.now(timezone.utc)
    
    # Log login activity
    log = ActivityLog(
        user_id=user.id,
        action="login",
        details="User logged in successfully"
    )
    db.add(log)
    await db.commit()

    # Generate tokens
    access_token = create_access_token(subject=user.email, role=user.role.value)
    refresh_token = create_refresh_token(subject=user.email)
    
    logger.info(f"User login success: {user.email}")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": user.role.value,
        "name": user.name
    }


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_token_str: str,
    db: AsyncSession = Depends(get_db)
):
    """Validate refresh token and issue a new access token."""
    payload_data = decode_token(refresh_token_str)
    if not payload_data or payload_data.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    email = payload_data.get("sub")
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    new_access_token = create_access_token(subject=user.email, role=user.role.value)
    new_refresh_token = create_refresh_token(subject=user.email)
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "role": user.role.value,
        "name": user.name
    }


@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Retrieve details of the currently logged-in user."""
    return current_user
