from sqlalchemy import Column, Integer, String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base # <-- CHANGED THIS LINE

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    ratings = relationship("Rating", back_populates="user")

class Movie(Base):
    __tablename__ = "movies"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    release_year = Column(Integer)
    genres = Column(String)
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

