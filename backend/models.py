from sqlalchemy import Column, Integer, String, Float, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import relationship
from database import Base # Import Base from our database.py

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True, autoincrement=False) 
    
    # --- UPDATED FOR AUTH ---
    # These fields are no longer optional
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    # -------------------------

    ratings = relationship("Rating", back_populates="user")

class Movie(Base):
    __tablename__ = "movies"
    id = Column(Integer, primary_key=True, index=True, autoincrement=False)
    title = Column(String, index=True)
    description = Column(Text, nullable=True)
    release_year = Column(Integer, nullable=True)
    genres = Column(String, nullable=True)
    poster_url = Column(String, nullable=True) 

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

