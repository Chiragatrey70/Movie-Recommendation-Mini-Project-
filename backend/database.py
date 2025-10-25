import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv # Import load_dotenv

# Load environment variables from .env file (optional, good for local dev)
# Make sure this runs before accessing environment variables
# Looks for .env in the parent directory relative to this file (database.py)
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(dotenv_path):
    print(f"Loading environment variables from: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path)
else:
    print(f".env file not found at {dotenv_path}, relying on system environment variables.")


# --- Read Database URL from Environment Variable ---
# Use os.getenv to read the variable. Render MUST provide this variable in deployment.
DATABASE_URL = os.getenv("DATABASE_URL")

# Check if DATABASE_URL was successfully loaded
if DATABASE_URL is None:
     # Raise an error if the essential DATABASE_URL is missing.
     raise ValueError("DATABASE_URL environment variable is not set. Ensure it is set in your environment (e.g., .env file or Render service config). Cannot connect to the database.")

print(f"DATABASE_URL loaded: {'postgresql://.../...@...' if DATABASE_URL.startswith('postgresql') else DATABASE_URL}") # Mask credentials in log

# --- SQLAlchemy Engine Setup ---
# Note: connect_args={"check_same_thread": False} is ONLY for SQLite. Remove it for PostgreSQL.
if DATABASE_URL.startswith("postgresql"):
    # For PostgreSQL, no extra connect_args needed typically
    engine = create_engine(DATABASE_URL)
    print("Connecting to PostgreSQL database.")
elif DATABASE_URL.startswith("sqlite"):
    # Handle SQLite connection if used as a fallback (ensure path is correct relative to project root)
    # The path in .env should be relative like 'sqlite:///movies.db'
    # db_path = os.path.join(os.path.dirname(__file__), '..', DATABASE_URL.split("///")[1]) # Path relative to root
    # engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    # Simpler if DATABASE_URL is just `sqlite:///movies.db` and run from root:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    print(f"Connecting to SQLite database at: {DATABASE_URL}")
else:
    raise ValueError(f"Unsupported database type in DATABASE_URL: {DATABASE_URL}")


# SessionLocal is used to create database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for SQLAlchemy models (defined in models.py)
Base = declarative_base()

# --- Dependency to get DB session ---
def get_db():
    """FastAPI dependency that provides a SQLAlchemy database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()