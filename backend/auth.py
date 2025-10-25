import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from pydantic import BaseModel

# --- NEW TOP-LEVEL IMPORTS ---
import models # Import models module at the top
from database import get_db # Import get_db dependency function at the top
# --- END NEW IMPORTS ---

# --- Configuration ---
# Load JWT settings from Environment Variables
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256") # Default algorithm if not set
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")) # Default 30 mins

if SECRET_KEY is None:
    # In production, this should absolutely be set. For local dev, provide a fallback ONLY if needed.
    # raise ValueError("SECRET_KEY environment variable is not set. Cannot run without it.")
    print("WARNING: SECRET_KEY environment variable not set. Using a default NON-SECURE key for local dev ONLY.")
    SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7" # Example ONLY, generate your own!

# Password Hashing Setup (Using Argon2 first, fallback to bcrypt)
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")

# OAuth2 Scheme Setup (Defines how clients send the token)
# tokenUrl="token" means the client should POST to the /token endpoint to get a token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Password Utilities ---

def verify_password(plain_password, hashed_password):
    """Checks if the plain password matches the stored hash."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        print(f"Error verifying password: {e}") # Log error
        return False

def get_password_hash(password):
    """Generates a secure hash for a given password."""
    return pwd_context.hash(password)

# --- JWT Token Utilities ---

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Creates a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- Pydantic Models for Token Data ---
class Token(BaseModel): # Now BaseModel is defined via import
    access_token: str
    token_type: str

class TokenData(BaseModel): # Now BaseModel is defined via import
    user_id: Optional[int] = None # Changed from username to user_id for DB lookup

# --- Dependency Functions (Used by API endpoints) ---

# MODIFICATION: Changed Depends("database.get_db") to Depends(get_db)
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """
    Dependency to get the current user from the token.
    Decodes token, validates user_id, fetches user from DB.
    """
    # REMOVED: Local imports are no longer needed here
    # import models
    # from database import get_db

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("sub") # "sub" is the standard claim for subject (user identifier)
        if user_id_str is None:
            raise credentials_exception
        token_data = TokenData(user_id=int(user_id_str)) # Validate and convert user_id
    except JWTError:
        raise credentials_exception
    except (ValueError, TypeError): # Handle case where user_id isn't an int
         raise credentials_exception

    # Use the models module imported at the top level
    user = db.query(models.User).filter(models.User.id == token_data.user_id).first()
    if user is None:
        raise credentials_exception
    return user

# MODIFICATION: Imported models at top, so type hint models.User should work directly
async def get_current_active_user(current_user: models.User = Depends(get_current_user)):
    """
    Placeholder dependency - in a real app, you might check if user.is_active.
    For now, it just ensures the user was successfully retrieved by get_current_user.
    """
    # if current_user.disabled: # Example check
    #     raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

# --- Authentication Logic ---

# MODIFICATION: Removed local import models
def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
    """
    Authenticates a user by email and password.
    Returns the user object if authentication succeeds, otherwise returns None.
    """
    # Use the models module imported at the top level
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

