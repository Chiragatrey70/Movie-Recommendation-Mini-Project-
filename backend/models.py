from sqlalchemy import Column, Integer, String, Float, ForeignKey, UniqueConstraint, DateTime # Added DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func # Added func for default timestamp
from database import Base # Keep this import

# --- Existing Models ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True, autoincrement=False) # Keep autoincrement=False
    username = Column(String, unique=True, index=True, nullable=False) # Make required
    email = Column(String, unique=True, index=True, nullable=False) # Make required
    hashed_password = Column(String, nullable=False) # Make required

    ratings = relationship("Rating", back_populates="user", cascade="all, delete-orphan")
    watchlist_items = relationship("WatchlistItem", back_populates="user", cascade="all, delete-orphan") # <-- ADDED relationship

class Movie(Base):
    __tablename__ = "movies"
    id = Column(Integer, primary_key=True, index=True, autoincrement=False) # Keep autoincrement=False
    title = Column(String, index=True, nullable=False) # Make required
    description = Column(String, nullable=True) # Allow null
    release_year = Column(Integer, nullable=True) # Allow null
    genres = Column(String, nullable=True) # Allow null
    poster_url = Column(String, nullable=True) # Allow null

    ratings = relationship("Rating", back_populates="movie", cascade="all, delete-orphan")
    watchlist_items = relationship("WatchlistItem", back_populates="movie", cascade="all, delete-orphan") # <-- ADDED relationship

class Rating(Base):
    __tablename__ = "ratings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False)
    score = Column(Float, index=True, nullable=False)

    user = relationship("User", back_populates="ratings")
    movie = relationship("Movie", back_populates="ratings")

    __table_args__ = (UniqueConstraint('user_id', 'movie_id', name='_user_movie_rating_uc'),)


# --- NEW Watchlist Model ---
class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False)
    added_at = Column(DateTime(timezone=True), server_default=func.now()) # Track when it was added

    user = relationship("User", back_populates="watchlist_items")
    movie = relationship("Movie", back_populates="watchlist_items")

    __table_args__ = (UniqueConstraint('user_id', 'movie_id', name='_user_movie_watchlist_uc'),) # Ensure user can only add a movie once

