import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc # Keep these imports
from pydantic import BaseModel
from typing import List, Optional

from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
import auth # Our auth.py file

import ml_engine
import models
import database

# Get the database setup components
Base = database.Base
engine = database.engine
get_db = database.get_db

# --- Pydantic Schemas (API Validation) ---
# (Schemas remain the same - no changes needed here)
class RatingBase(BaseModel):
    movie_id: int
    score: float

class RatingCreate(RatingBase):
    pass

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
    description="Full-stack API with authentication, real data, posters, cold-start fix, and genre filtering.",
    version="8.0.0" # Genre Filter Added!
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
    return {"message": "Welcome to the Movie Recommendation API (v8.0)"}

# --- AUTH ENDPOINTS ---
# (Register and Token endpoints remain the same)
@app.post("/register/", response_model=UserResponse, summary="Register a new user")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already taken")

    if len(user.password) > 128: # Arbitrary reasonable limit for Argon2
         raise HTTPException(
             status_code=400,
             detail="Password is too long. Maximum 128 characters allowed."
         )

    max_id_result = db.query(models.User.id).order_by(models.User.id.desc()).first()
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
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- PROTECTED USER ENDPOINTS ---
@app.get("/users/me", response_model=UserResponse, summary="Get current logged-in user's details")
async def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

@app.get("/users/me/ratings", response_model=List[UserRatingResponse], summary="Get All Ratings for Current User (Protected)")
def get_user_ratings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    ratings = db.query(models.Rating).filter(models.Rating.user_id == current_user.id).all()
    return ratings

# --- UPDATED MOVIES ENDPOINT ---
@app.get("/movies/", response_model=List[MovieResponse], summary="Get Movies (Public, with Genre Filter)")
def get_movies(
    search: Optional[str] = Query(None, description="Search term to filter movies by title"),
    genre: Optional[str] = Query(None, description="Genre to filter movies by (e.g., Action, Comedy)"), # <-- NEW PARAMETER
    skip: int = 0,
    limit: int = 20, # Keep limit for pagination later
    db: Session = Depends(get_db)
):
    query = db.query(models.Movie)
    if search:
        # Using ilike for case-insensitive search
        query = query.filter(models.Movie.title.ilike(f"%{search}%"))

    # --- NEW GENRE FILTER LOGIC ---
    if genre:
        # Using ilike for case-insensitive genre matching
        # This will match if the genre string appears anywhere in the genres column
        # e.g., genre="Action" matches "Action|Adventure|Sci-Fi"
        query = query.filter(models.Movie.genres.ilike(f"%{genre}%"))
    # --- END NEW LOGIC ---

    movies = query.offset(skip).limit(limit).all()
    return movies
# --- END UPDATED ENDPOINT ---

@app.get("/movies/{movie_id}", response_model=MovieResponse, summary="Get Movie by ID (Public)")
def get_movie_by_id(movie_id: int, db: Session = Depends(get_db)):
    # (This endpoint remains the same)
    movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie

# --- PROTECTED RATINGS & RECOMMENDATIONS ---
@app.post("/ratings/", response_model=RatingResponse, summary="Rate a Movie (Protected)")
def create_or_update_rating(
    rating: RatingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # (This endpoint remains the same)
    movie = db.query(models.Movie).filter(models.Movie.id == rating.movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    db_rating = db.query(models.Rating).filter(
        models.Rating.user_id == current_user.id,
        models.Rating.movie_id == rating.movie_id
    ).first()

    rating_data = rating.dict()
    rating_data['user_id'] = current_user.id

    if db_rating:
        print(f"Updating rating for user {current_user.id} on movie {rating.movie_id}")
        db_rating.score = rating.score
    else:
        print(f"Creating new rating for user {current_user.id} on movie {rating.movie_id}")
        db_rating = models.Rating(**rating_data)
        db.add(db_rating)

    db.commit()
    db.refresh(db_rating)

    print("Rating submitted. Queuing model retrain in background.")
    background_tasks.add_task(ml_engine.train_collaborative_model, db)

    return db_rating

@app.get("/recommendations/", response_model=List[MovieResponse], summary="Get Recommendations (Protected, handles Cold Start)")
def get_recommendations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # (This endpoint remains the same)
    user_id = current_user.id
    COLD_START_THRESHOLD = 5
    user_rating_count = db.query(models.Rating).filter(models.Rating.user_id == user_id).count()
    print(f"User {user_id} has {user_rating_count} ratings.")

    if user_rating_count < COLD_START_THRESHOLD:
        print(f"User {user_id} is a new user (cold start). Recommending popular movies.")
        rated_movie_ids_query = db.query(models.Rating.movie_id).filter(models.Rating.user_id == user_id)
        rated_movie_ids = {r[0] for r in rated_movie_ids_query.all()}
        top_rated_movies_query = (
            db.query(models.Movie, func.count(models.Rating.id).label('rating_count'))
            .join(models.Rating, models.Movie.id == models.Rating.movie_id)
            .group_by(models.Movie.id).order_by(desc('rating_count')).limit(20)
        )
        popular_recommendations = [
            movie for movie, count in top_rated_movies_query.all()
            if movie.id not in rated_movie_ids
        ][:10]
        print(f"Returning {len(popular_recommendations)} popular movie recommendations for cold start.")
        return popular_recommendations
    else:
        print(f"User {user_id} has enough ratings. Using hybrid ML engine.")
        recommended_movie_ids = ml_engine.get_hybrid_recommendations(user_id, db, num_recs=10)
        if not recommended_movie_ids:
            print(f"ML engine returned no recs for user {user_id}. Falling back to popular list.")
            rated_movie_ids_query = db.query(models.Rating.movie_id).filter(models.Rating.user_id == user_id)
            rated_movie_ids = {r[0] for r in rated_movie_ids_query.all()}
            top_rated_movies_query = (
                db.query(models.Movie, func.count(models.Rating.id).label('rating_count'))
                .join(models.Rating, models.Movie.id == models.Rating.movie_id)
                .group_by(models.Movie.id).order_by(desc('rating_count')).limit(20)
            )
            fallback_recs = [ movie for movie, count in top_rated_movies_query.all() if movie.id not in rated_movie_ids ][:10]
            return fallback_recs

        recommended_movies = db.query(models.Movie).filter(models.Movie.id.in_(recommended_movie_ids)).all()
        movie_map = {movie.id: movie for movie in recommended_movies}
        ordered_recs = [movie_map[movie_id] for movie_id in recommended_movie_ids if movie_id in movie_map]
        print(f"Returning {len(ordered_recs)} hybrid ML recommendations.")
        return ordered_recs

