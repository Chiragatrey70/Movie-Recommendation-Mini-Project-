from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = "sqlite:///./movies.db"

# We'll remove this line now, so our DB and ratings persist
# if os.path.exists("movies.db"):
#     os.remove("movies.db")

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# models.py will import this Base
Base = declarative_base()

# main.py will import this function
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

