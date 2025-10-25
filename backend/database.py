import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv # Import load_dotenv

# Load environment variables from .env file (optional, good for local dev)
load_dotenv()

# --- Read Database URL from Environment Variable ---
# Use os.getenv to read the variable. Provide a default fallback for local dev
# if the Render variable isn't set.
# IMPORTANT: Ensure your LOCAL .env file OR database.py still has your LOCAL connection string
# for local testing. The Render environment variable will override this in deployment.

DATABASE_URL = os.getenv(
    "DATABASE_URL", # Render will set this automatically from your linked DB
    "postgresql://postgres:vcaaaa030516@localhost:5432/movierec_db" # Fallback for local
)
# ----------------------------------------------------

# Ensure you replace YOUR_LOCAL_USERNAME/PASSWORD in the fallback above
# if you still want to run locally sometimes.

if DATABASE_URL is None:
    raise ValueError("DATABASE_URL environment variable is not set and no fallback provided.")

# Modify the engine creation slightly if the Render DB URL uses postgres:// instead of postgresql://
# Render's URLs often start with postgres://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    print("Creating database tables if they don't exist...")
    try:
        # Import models here locally to ensure Base is populated before create_all
        import models
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully (or already exist).")
    except Exception as e:
        print(f"Error creating tables: {e}")
        raise

