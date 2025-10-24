import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import os

# Import all our custom modules
import ml_engine
import models
import database

# Get the database setup components
Base = database.Base
engine = database.engine
get_db = database.get_db

# --- Pydantic Schemas (API Validation) ---

class RatingBase(BaseModel):
    movie_id: int
    score: float

class RatingCreate(RatingBase):
    user_id: int 

class RatingResponse(RatingBase):
    id: int
    user_id: int
    
    class Config:
        from_attributes = True

class UserRatingResponse(BaseModel):
    movie_id: int
    score: float

    class Config:
        from_attributes = True

# For Movie
class MovieBase(BaseModel):
    title: str
    description: Optional[str] = None
    release_year: Optional[int] = None
    genres: Optional[str] = None
    poster_url: Optional[str] = None # <-- ADDED THIS

class MovieResponse(MovieBase):
    id: int
    
    class Config:
        from_attributes = True

# For User
class UserBase(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None

class UserCreate(UserBase):
    id: Optional[int] = None
    password: str = "default"

class UserResponse(UserBase):
    id: int
    
    class Config:
        from_attributes = True

# --- FastAPI App ---

app = FastAPI(
    title="Movie Recommendation API",
    description="Full-stack API with real data, TMDB posters, and background model training.",
    version="5.0.0" # Poster version!
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)

# --- Startup Event ---
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    
    db = next(get_db())
    try:
        movie_count = db.query(models.Movie).count()
        if movie_count == 0:
            print("--------------------------------------------------")
            print("WARNING: Database is empty.")
            print("Run the seeder script to populate the database:")
            print("python backend/seed.py")
            print("--------------------------------------------------")
        else:
            print(f"Database already populated with {movie_count} movies.")
        
        print("Training collaborative filtering model...")
        ml_engine.train_collaborative_model(db)

    except Exception as e:
        print(f"Error during startup: {e}")
    finally:
        db.close()

# --- API Endpoints ---

@app.get("/", summary="Root")
def read_root():
    return {"message": "Welcome to the Movie Recommendation API (v5.0)"}

@app.post("/users/", response_model=UserResponse, summary="Create User")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    if user.id:
         db_user = db.query(models.User).filter(models.User.id == user.id).first()
         if db_user:
             raise HTTPException(status_code=400, detail="User ID already exists")
    else:
        max_id = db.query(models.User.id).order_by(models.User.id.desc()).first()
        new_id = (max_id[0] if max_id else 0) + 1
        user.id = new_id
    
    new_user = models.User(
        id=user.id, 
        username=user.username or f"user{user.id}", 
        email=user.email, 
        hashed_password=f"hashed_{user.password}"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.get("/movies/", response_model=List[MovieResponse], summary="Get Movies")
def get_movies(
    search: Optional[str] = Query(None, description="Search term to filter movies by title"),
    skip: int = 0, 
    limit: int = 20, 
    db: Session = Depends(get_db)
):
    query = db.query(models.Movie)
    if search:
        query = query.filter(models.Movie.title.ilike(f"%{search}%"))
    movies = query.offset(skip).limit(limit).all()
    return movies

@app.get("/movies/{movie_id}", response_model=MovieResponse, summary="Get Movie by ID")
def get_movie_by_id(movie_id: int, db: Session = Depends(get_db)):
    movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie

@app.post("/ratings/", response_model=RatingResponse, summary="Rate a Movie")
def create_or_update_rating(
    rating: RatingCreate, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.id == rating.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    movie = db.query(models.Movie).filter(models.Movie.id == rating.movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    db_rating = db.query(models.Rating).filter(
        models.Rating.user_id == rating.user_id,
        models.Rating.movie_id == rating.movie_id
    ).first()

    if db_rating:
        print(f"Updating rating for user {rating.user_id} on movie {rating.movie_id}")
        db_rating.score = rating.score
    else:
        print(f"Creating new rating for user {rating.user_id} on movie {rating.movie_id}")
        db_rating = models.Rating(**rating.dict())
        db.add(db_rating)
    
    db.commit()
    db.refresh(db_rating)
    
    print("Rating submitted. Queuing model retrain in background.")
    background_tasks.add_task(ml_engine.train_collaborative_model, db)

    return db_rating

@app.get("/recommendations/{user_id}", response_model=List[MovieResponse], summary="Get Hybrid Recommendations")
def get_recommendations(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    recommended_movie_ids = ml_engine.get_hybrid_recommendations(user_id, db, num_recs=10)
    
    if not recommended_movie_ids:
        print(f"ML engine returned no recs for user {user_id}. Falling back to simple list.")
        rated_movie_ids_query = db.query(models.Rating.movie_id).filter(models.Rating.user_id == user_id)
        rated_movie_ids = {r[0] for r in rated_movie_ids_query.all()}
        
        all_movies = db.query(models.Movie).filter(models.Movie.id.notin_(rated_movie_ids)).limit(10).all()
        return all_movies

    recommended_movies = db.query(models.Movie).filter(models.Movie.id.in_(recommended_movie_ids)).all()
    
    movie_map = {movie.id: movie for movie in recommended_movies}
    ordered_recs = [movie_map[movie_id] for movie_id in recommended_movie_ids if movie_id in movie_map]
    
    return ordered_recs

@app.get("/users/{user_id}/ratings", response_model=List[UserRatingResponse], summary="Get All Ratings for a User")
def get_user_ratings(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    ratings = db.query(models.Rating).filter(models.Rating.user_id == user_id).all()
    return ratings

