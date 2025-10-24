from sqlalchemy import Column, Integer, String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base # Import Base from our database.py

class User(Base):
    __tablename__ = "users"
    
    # We set autoincrement=False so we can use the IDs from the CSV
    id = Column(Integer, primary_key=True, index=True, autoincrement=False)
    
    # We don't have this data in the CSV, so we'll make them nullable
    # In a real app, you'd have a proper registration flow
    username = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=True)
    
    ratings = relationship("Rating", back_populates="user")

class Movie(Base):
    __tablename__ = "movies"
    
    # We set autoincrement=False so we can use the IDs from the CSV
    id = Column(Integer, primary_key=True, index=True, autoincrement=False)
    
    title = Column(String, index=True)
    # Description isn't in movies.csv, so we'll make it nullable
    description = Column(String, nullable=True) 
    # Release Year isn't in movies.csv, so we'll make it nullable
    release_year = Column(Integer, nullable=True)
    genres = Column(String)
    
    ratings = relationship("Rating", back_populates="movie")

class Rating(Base):
    __tablename__ = "ratings"
    
    # We DO want new ratings to autoincrement, so we leave this as default
    id = Column(Integer, primary_key=True, index=True)
    
    user_id = Column(Integer, ForeignKey("users.id"))
    movie_id = Column(Integer, ForeignKey("movies.id"))
    score = Column(Float, index=True)
    
    user = relationship("User", back_populates="ratings")
    movie = relationship("Movie", back_populates="ratings")
    
    __table_args__ = (UniqueConstraint('user_id', 'movie_id', name='_user_movie_uc'),)

