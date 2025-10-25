import os
from datetime import datetime, timedelta, timezone # Ensure timezone is imported
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from pydantic import BaseModel # <-- ADDED THIS IMPORT

# Assuming models.py and database.py are in the same directory
import models
from database import get_db

# --- Configuration ---
# Generate a secret key: openssl rand -hex 32
SECRET_KEY = os.environ.get("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7") # Use env var or a default
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 # Token validity period

# --- Password Hashing ---
# Use Argon2 as primary, keep bcrypt for compatibility if needed
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")

# --- OAuth2 Scheme ---
# This tells FastAPI where to look for the token (in the Authorization header)
# tokenUrl="token" means the client should request a token from the /token endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# --- Password Verification ---
def verify_password(plain_password, hashed_password):
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        print(f"Error verifying password: {e}") # Log error
        return False


# --- Password Hashing ---
def get_password_hash(password):
    try:
        return pwd_context.hash(password)
    except Exception as e:
        print(f"Error hashing password: {e}") # Log error
        # Re-raise or handle appropriately, maybe raise HTTPException?
        # For now, re-raising to make error visible during development
        raise


# --- Token Creation ---
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# --- User Authentication ---
def authenticate_user(db: Session, email: str, password: str):
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# --- Pydantic model for Token Data (Payload) ---
class TokenData(BaseModel): # Now BaseModel is defined
    user_id: Optional[int] = None


# --- Dependency to Get Current User ---
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("sub") # Assuming user ID stored in 'sub' claim
        if user_id_str is None:
            raise credentials_exception
        # Attempt to convert user_id from string to int
        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
             raise credentials_exception

        token_data = TokenData(user_id=user_id)

    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == token_data.user_id).first()
    if user is None:
        raise credentials_exception
    return user


# --- Dependency for Active User (Optional - can just use get_current_user) ---
# This is often used if you have an 'is_active' flag on the User model
async def get_current_active_user(current_user: models.User = Depends(get_current_user)):
    # Add any checks here if needed (e.g., if not current_user.is_active:)
    # For now, just return the user obtained from get_current_user
    return current_user

# --- Pydantic model for Token Response ---
class Token(BaseModel): # Now BaseModel is defined
    access_token: str
    token_type: str

# Removed the fallback BaseModel definition as we now import it correctly

