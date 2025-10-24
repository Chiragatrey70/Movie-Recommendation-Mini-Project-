import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

# --- NEW AUTH IMPORTS ---
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
import auth # Our new auth.py file
# -------------------------

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
    pass # user_id will come from the logged-in user, not the request body

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
    poster_url: Optional[str] = None

class MovieResponse(MovieBase):
    id: int

    class Config:
        from_attributes = True

# For User
class UserBase(BaseModel):
    username: str
    email: str

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int

    class Config:
        from_attributes = True

# --- FastAPI App ---

app = FastAPI(
    title="Movie Recommendation API",
    description="Full-stack API with authentication, real data, and TMDB posters.",
    version="6.1.0" # Added password length check
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
    return {"message": "Welcome to the Movie Recommendation API (v6.1)"}

# --- NEW AUTH ENDPOINTS ---

@app.post("/register/", response_model=UserResponse, summary="Register a new user")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    # Check if user already exists
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already taken")

    # --- ADDED PASSWORD LENGTH CHECK ---
    # Bcrypt has a maximum password length of 72 bytes
    if len(user.password.encode('utf-8')) > 72:
        raise HTTPException(
            status_code=400,
            detail="Password is too long. Maximum 72 characters allowed."
        )
    # ------------------------------------

    # Get the next available user ID
    max_id_result = db.query(models.User.id).order_by(models.User.id.desc()).first()
    # The MovieLens dataset users are 1-610. We'll start new users from 1000.
    new_id = (max_id_result[0] if max_id_result and max_id_result[0] > 1000 else 1000) + 1

    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(
        id=new_id,
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/token/", response_model=auth.Token, summary="Login and get an access token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    # Note: OAuth2PasswordRequestForm uses "username", but our app uses email to log in
    # So we'll treat the "username" field from the form as the user's email.
    user = db.query(models.User).filter(models.User.email == form_data.username).first()

    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    # The 'sub' (subject) of the token will be the user's ID
    access_token = auth.create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- UPDATED/PROTECTED ENDPOINTS ---

@app.get("/users/me", response_model=UserResponse, summary="Get current logged-in user's details")
async def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    # If the token is valid, get_current_user will return the user object.
    # If the token is invalid, it will automatically raise a 401 error.
    return current_user

@app.get("/movies/", response_model=List[MovieResponse], summary="Get Movies (Public)")
def get_movies(
    search: Optional[str] = Query(None, description="Search term to filter movies by title"),
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    # This endpoint can remain public for anyone to search movies
    query = db.query(models.Movie)
    if search:
        query = query.filter(models.Movie.title.ilike(f"%{search}%"))
    movies = query.offset(skip).limit(limit).all()
    return movies

@app.get("/movies/{movie_id}", response_model=MovieResponse, summary="Get Movie by ID (Public)")
def get_movie_by_id(movie_id: int, db: Session = Depends(get_db)):
    # This endpoint can also remain public
    movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie

@app.post("/ratings/", response_model=RatingResponse, summary="Rate a Movie (Protected)")
def create_or_update_rating(
    rating: RatingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user) # <-- PROTECTED!
):
    # current_user is now reliably the logged-in user from their token
    movie = db.query(models.Movie).filter(models.Movie.id == rating.movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    db_rating = db.query(models.Rating).filter(
        models.Rating.user_id == current_user.id, # <-- Use current_user.id
        models.Rating.movie_id == rating.movie_id
    ).first()

    rating_data = rating.dict()
    rating_data['user_id'] = current_user.id # <-- Set user_id from token

    if db_rating:
        print(f"Updating rating for user {current_user.id} on movie {rating.movie_id}")
        db_rating.score = rating.score
    else:
        print(f"Creating new rating for user {current_user.id} on movie {rating.movie_id}")
        db_rating = models.Rating(**rating_data)
        db.add(db_rating)

    db.commit()
    db.refresh(db_rating)

    # Queue model retraining to happen in the background
    print("Rating submitted. Queuing model retrain in background.")
    background_tasks.add_task(ml_engine.train_collaborative_model, db)

    return db_rating

@app.get("/recommendations/", response_model=List[MovieResponse], summary="Get Hybrid Recommendations (Protected)")
def get_recommendations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user) # <-- PROTECTED!
):
    user_id = current_user.id # <-- Get user_id from token
    recommended_movie_ids = ml_engine.get_hybrid_recommendations(user_id, db, num_recs=10)

    if not recommended_movie_ids:
        # Fallback: if no recs, return popular movies the user hasn't rated
        print(f"ML engine returned no recs for user {user_id}. Falling back to simple list.")
        rated_movie_ids_query = db.query(models.Rating.movie_id).filter(models.Rating.user_id == user_id)
        rated_movie_ids = {r[0] for r in rated_movie_ids_query.all()}

        # This is a simple fallback, a real app might use "most popular"
        all_movies = db.query(models.Movie).filter(models.Movie.id.notin_(rated_movie_ids)).limit(10).all()
        return all_movies

    # Fetch the full movie objects for the recommended IDs
    recommended_movies = db.query(models.Movie).filter(models.Movie.id.in_(recommended_movie_ids)).all()

    # Preserve the order from the recommendation engine
    movie_map = {movie.id: movie for movie in recommended_movies}
    ordered_recs = [movie_map[movie_id] for movie_id in recommended_movie_ids if movie_id in movie_map]

    return ordered_recs

@app.get("/users/me/ratings", response_model=List[UserRatingResponse], summary="Get All Ratings for Current User (Protected)")
def get_user_ratings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user) # <-- PROTECTED!
):
    # This replaces the old /users/{user_id}/ratings
    ratings = db.query(models.Rating).filter(models.Rating.user_id == current_user.id).all()
    return ratings

