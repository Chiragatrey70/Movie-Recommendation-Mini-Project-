from sqlalchemy import Column, Integer, String, Float, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import relationship
from database import Base # Import Base from our database.py

class User(Base):
    __tablename__ = "users"
    # Set autoincrement=False so we can use the real IDs from the CSV
    id = Column(Integer, primary_key=True, index=True, autoincrement=False) 
    username = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=True)
    ratings = relationship("Rating", back_populates="user")

class Movie(Base):
    __tablename__ = "movies"
    # Set autoincrement=False so we can use the real IDs from the CSV
    id = Column(Integer, primary_key=True, index=True, autoincrement=False)
    title = Column(String, index=True)
    description = Column(Text, nullable=True)
    release_year = Column(Integer, nullable=True)
    genres = Column(String, nullable=True)
    
    # --- NEW COLUMN ---
    poster_url = Column(String, nullable=True) # Will store the URL to the movie poster

    ratings = relationship("Rating", back_populates="movie")

class Rating(Base):
    __tablename__ = "ratings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    movie_id = Column(Integer, ForeignKey("movies.id"))
    score = Column(Float, index=True)
    user = relationship("User", back_populates="ratings")
    movie = relationship("Movie", back_populates="ratings")
    __table_args__ = (UniqueConstraint('user_id', 'movie_id', name='_user_movie_uc'),)

