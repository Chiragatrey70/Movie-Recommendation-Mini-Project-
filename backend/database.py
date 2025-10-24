import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# --- THIS IS THE NEW FIX ---
# Get the absolute path to the 'backend' directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Get the absolute path to the parent (root) directory
ROOT_DIR = os.path.dirname(BASE_DIR)
# Create the absolute path to our database file in the ROOT folder
DATABASE_PATH = os.path.join(ROOT_DIR, "movies.db")
# Define the absolute database URL
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
# --- END OF FIX ---

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

