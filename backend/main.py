import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks, status # Added status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm # For login form
from sqlalchemy.orm import Session, joinedload # <-- Added joinedload
from sqlalchemy import desc, func, select # Added func, select
from typing import List, Optional
import os
from datetime import datetime # <-- Added datetime
from pydantic import BaseModel as PydanticBaseModel # <-- Use Pydantic BaseModel directly

# --- Import project modules ---
import ml_engine
import models
import auth
# Removed 'import schemas' as we define them here
from database import engine, SessionLocal, get_db, Base # Use items from database.py


# --- Pydantic Schemas (API Validation) ---
# Use Pydantic's BaseModel directly instead of a separate schemas.py
class BaseModel(PydanticBaseModel):
    class Config:
        from_attributes = True # Default config for all schemas

class RatingBase(BaseModel):
    movie_id: int
    score: float

class RatingCreate(RatingBase):
    pass # user_id will come from the logged-in user

class RatingResponse(RatingBase):
    id: int
    user_id: int
    # class Config: # Config inherited from BaseModel
    #     from_attributes = True

class MovieBase(BaseModel):
    title: str
    description: Optional[str] = None
    release_year: Optional[int] = None
    genres: Optional[str] = None
    poster_url: Optional[str] = None # Added poster_url

class MovieResponse(MovieBase):
    id: int
    # Temporarily remove ratings from MovieResponse to avoid potential deep nesting issues
    # ratings: List[RatingResponse] = []
    # class Config: # Config inherited from BaseModel
    #     from_attributes = True

class UserBase(BaseModel):
    username: str
    email: str

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    # class Config: # Config inherited from BaseModel
    #     from_attributes = True

# --- NEW Watchlist Schemas ---
class WatchlistItemBase(BaseModel):
    movie_id: int

class WatchlistItemCreate(WatchlistItemBase):
   pass # user_id comes from logged-in user

class WatchlistItemResponse(WatchlistItemBase):
    id: int
    user_id: int
    added_at: datetime # Added from models
    movie: MovieResponse # Include movie details in response

    # class Config: # Config inherited from BaseModel
    #     from_attributes = True

# --- FastAPI App ---

app = FastAPI(
    title="Movie Recommendation API",
    description="Final Version: Includes Auth, Genre Filter, Watchlist, Cold Start.",
    version="3.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for simplicity (adjust for production)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Startup Event ---
@app.on_event("startup")
def on_startup():
    print("Running startup event...")
    # Check if DB exists before creating tables (idempotent)
    # Base.metadata.create_all(bind=engine) # create_all is called by seed script now

    db = SessionLocal()
    try:
        # Check if movies table is populated as a proxy for seeding
        movie_count_query = select(func.count(models.Movie.id))
        movie_count = db.execute(movie_count_query).scalar_one_or_none()

        if movie_count is None or movie_count == 0:
             print("-" * 50)
             print("WARNING: Database appears empty or tables missing.")
             print("Please run the seeder script to populate the database:")
             print("python backend/seed.py")
             print("-" * 50)
             # Optionally exit or prevent training if DB is empty
             # return
        else:
            print(f"Database already populated with {movie_count} movies.")

        # Train the ML model on startup (only if DB seems populated)
        if movie_count and movie_count > 0: # <-- Only train if movies exist
            print("Training collaborative filtering model...")
            ml_engine.train_collaborative_model(db)
        else:
            print("Skipping model training as database is empty.")


    except Exception as e:
        print(f"Error during startup or model training: {e}")
        # Consider logging the full traceback here
        import traceback
        traceback.print_exc()
    finally:
        db.close()
        print("Startup complete.")


# --- API Endpoints ---

@app.get("/", summary="Root")
def read_root():
    return {"message": "Welcome to the Movie Recommendation API (Final Version)"}

# --- Authentication Endpoints ---

@app.post("/register/", response_model=UserResponse, summary="Register a new user")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    # Check if user already exists
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # Check password length (using auth module if preferred, or keep here)
    # Assuming auth.py might have validation logic, otherwise keep checks here
    if hasattr(auth, 'validate_password'): # Example if validation moved to auth.py
        is_valid, message = auth.validate_password(user.password)
        if not is_valid:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    else: # Keep validation here if not moved
        if len(user.password) > 72 and "bcrypt" in auth.pwd_context.schemes: # Check only if bcrypt is primary
             # This check might be less relevant if Argon2 is primary
             print("Warning: Password exceeds 72 chars, bcrypt might truncate/error if used.")
             # Consider if Argon2 (default now) makes this check unnecessary
        if len(user.password) < 4:
             raise HTTPException(
                 status_code=status.HTTP_400_BAD_REQUEST,
                 detail="Password is too short. Minimum 4 characters required."
             )


    # Hash password and create user
    try:
        hashed_password = auth.get_password_hash(user.password)
        # Determine the next available user ID (since autoincrement=False)
        max_id_query = select(func.max(models.User.id))
        max_id = db.execute(max_id_query).scalar_one_or_none()
        next_id = (max_id or 0) + 1

        new_user = models.User(
            id=next_id,
            username=user.username,
            email=user.email,
            hashed_password=hashed_password
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except Exception as e:
        db.rollback()
        print(f"Error creating user: {e}") # Log the specific error
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create user.")


@app.post("/token/", response_model=auth.Token, summary="Login and get an access token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Authenticate using email (form_data.username contains the email)
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(data={"sub": str(user.id)}) # Use user ID as subject
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me/", response_model=UserResponse, summary="Get current user details")
async def read_users_me(current_user: models.User = Depends(auth.get_current_active_user)):
    # Return user details based on the UserResponse schema
    return UserResponse(id=current_user.id, username=current_user.username, email=current_user.email)


# --- Movie Endpoints ---

@app.get("/movies/", response_model=List[MovieResponse], summary="Get Movies (with Search and Genre Filter)")
def get_movies(
    search: Optional[str] = Query(None, description="Search term to filter movies by title"),
    genre: Optional[str] = Query(None, description="Genre to filter movies by"), # Added genre filter
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    query = db.query(models.Movie)
    if search:
        # Ensure search is case-insensitive
        query = query.filter(models.Movie.title.ilike(f"%{search}%"))
    if genre:
        # Ensure genre search is case-insensitive and handles pipe (|) separated values
        query = query.filter(models.Movie.genres.ilike(f"%{genre}%"))

    movies = query.offset(skip).limit(limit).all()
    # Convert SQLAlchemy models to Pydantic models for response
    return [MovieResponse.model_validate(movie) for movie in movies]


@app.get("/movies/{movie_id}", response_model=MovieResponse, summary="Get Movie by ID")
def get_movie_by_id(movie_id: int, db: Session = Depends(get_db)):
    movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    # Convert SQLAlchemy model to Pydantic model
    return MovieResponse.model_validate(movie)


# --- Rating Endpoints ---

@app.post("/ratings/", response_model=RatingResponse, summary="Rate a Movie (updates if exists)")
def create_or_update_rating(
    rating: RatingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user) # Require login
):
    user_id = current_user.id # Get user_id from logged-in user

    # Check if movie exists
    movie = db.query(models.Movie).filter(models.Movie.id == rating.movie_id).first()
    if not movie:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")

    # Validate score range
    if not (0.5 <= rating.score <= 5.0):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Score must be between 0.5 and 5.0")


    # Check if rating already exists for this user and movie
    db_rating = db.query(models.Rating).filter(
        models.Rating.user_id == user_id,
        models.Rating.movie_id == rating.movie_id
    ).first()

    if db_rating:
        # Update existing rating
        db_rating.score = rating.score
        print(f"Updating rating for user {user_id}, movie {rating.movie_id} to {rating.score}")
    else:
        # Create new rating
        db_rating = models.Rating(
            user_id=user_id,
            movie_id=rating.movie_id,
            score=rating.score
        )
        db.add(db_rating)
        print(f"Creating new rating for user {user_id}, movie {rating.movie_id} with score {rating.score}")

    try:
        db.commit()
        db.refresh(db_rating)

        # Retrain the model in the background
        print("Rating submitted. Queuing model retrain in background.")
        # Ensure db session passed to background task is handled correctly
        # Option 1: Pass necessary data instead of the session (safer)
        # Option 2: Ensure background task creates its own session (more robust)
        # Sticking with passing db for now, assuming SessionLocal manages scope appropriately
        background_tasks.add_task(ml_engine.train_collaborative_model, SessionLocal()) # Pass a new session

        # Convert to Pydantic model for response
        return RatingResponse.model_validate(db_rating)
    except Exception as e:
        db.rollback()
        print(f"Error saving rating: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not save rating.")


@app.get("/users/me/ratings", response_model=List[RatingResponse], summary="Get Current User's Ratings")
def get_user_ratings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user) # Require login
):
    """
    Retrieves all movie ratings submitted by the currently logged-in user.
    """
    ratings = db.query(models.Rating).filter(models.Rating.user_id == current_user.id).all()
    # Convert list of SQLAlchemy models to list of Pydantic models
    return [RatingResponse.model_validate(rating) for rating in ratings]



# --- Recommendation Endpoint ---

@app.get("/recommendations/", response_model=List[MovieResponse], summary="Get Hybrid Recommendations for Current User")
def get_recommendations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user) # Require login
):
    """
    Get hybrid recommendations for the currently logged-in user.
    Applies cold-start logic for new users.
    """
    user_id = current_user.id

    # --- Cold Start Logic ---
    min_ratings_threshold = 5
    # Efficiently count ratings for the user
    user_rating_count = db.query(models.Rating).filter(models.Rating.user_id == user_id).count()


    recommendations = []
    recommended_movie_ids = []

    if user_rating_count < min_ratings_threshold:
        print(f"User {user_id} has {user_rating_count} ratings. Applying cold start logic (popular movies).")

        # Get IDs of movies already rated by the user
        rated_movie_ids_query = select(models.Rating.movie_id).filter(models.Rating.user_id == user_id)
        rated_movie_ids_result = db.execute(rated_movie_ids_query).scalars().all()
        rated_movie_ids = set(rated_movie_ids_result)

        # Find top N movies by number of ratings (excluding already rated ones)
        popular_movies_query = (
            select(models.Rating.movie_id, func.count(models.Rating.id).label('rating_count'))
            .group_by(models.Rating.movie_id)
            .order_by(desc('rating_count'))
            .limit(20) # Get more than needed initially
        )
        popular_movies_result = db.execute(popular_movies_query).all()

        # Filter out already rated movies and take top N
        for movie_id_tuple in popular_movies_result: # Result might be tuples
             movie_id = movie_id_tuple[0] # Extract movie_id
             if movie_id not in rated_movie_ids and len(recommended_movie_ids) < 10:
                recommended_movie_ids.append(movie_id)


        print(f"Cold start recommendations: {recommended_movie_ids}")

    else:
        # --- Hybrid ML Logic (for users with enough ratings) ---
        print(f"User {user_id} has {user_rating_count} ratings. Using hybrid ML engine.")
        # Ensure a new session is used for the potentially long-running ML task if needed
        # Or confirm SessionLocal scope handling is sufficient
        recommended_movie_ids = ml_engine.get_hybrid_recommendations(user_id, db, num_recs=10)


        if not recommended_movie_ids:
            # Fallback within hybrid logic (should be rare now with cold start)
            print(f"ML engine returned no recs for user {user_id}. Falling back to popular movies (alternative fallback).")
            # Reuse cold start logic as fallback
            rated_movie_ids_query = select(models.Rating.movie_id).filter(models.Rating.user_id == user_id)
            rated_movie_ids_result = db.execute(rated_movie_ids_query).scalars().all()
            rated_movie_ids = set(rated_movie_ids_result)
            popular_movies_query = (
                select(models.Rating.movie_id, func.count(models.Rating.id).label('rating_count'))
                .group_by(models.Rating.movie_id)
                .order_by(desc('rating_count'))
                .limit(20)
            )
            popular_movies_result = db.execute(popular_movies_query).all()
            for movie_id_tuple in popular_movies_result:
                 movie_id = movie_id_tuple[0]
                 if movie_id not in rated_movie_ids and len(recommended_movie_ids) < 10:
                    recommended_movie_ids.append(movie_id)


    # --- Fetch Movie Objects for Recommended IDs ---
    if recommended_movie_ids:
        # Fetch the full movie objects for the recommended IDs
        recommended_movies = db.query(models.Movie).filter(models.Movie.id.in_(recommended_movie_ids)).all()

        # Preserve the order from the recommendation engine/popularity list
        movie_map = {movie.id: movie for movie in recommended_movies}
        ordered_recs = [movie_map[movie_id] for movie_id in recommended_movie_ids if movie_id in movie_map]
        recommendations = ordered_recs
    else:
        print(f"No recommendations generated for user {user_id} (neither cold start nor ML). Returning empty list.")
        recommendations = []

    # Convert list of SQLAlchemy models to list of Pydantic models
    return [MovieResponse.model_validate(movie) for movie in recommendations]


# --- NEW Watchlist Endpoints ---

@app.post("/watchlist/", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED, summary="Add Movie to Watchlist")
def add_to_watchlist(
    item: WatchlistItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    user_id = current_user.id
    movie_id = item.movie_id

    # Check if movie exists
    movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")

    # Check if item already exists in watchlist
    db_item = db.query(models.WatchlistItem).filter(
        models.WatchlistItem.user_id == user_id,
        models.WatchlistItem.movie_id == movie_id
    ).first()

    if db_item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Movie already in watchlist"
        )

    # Create new watchlist item
    new_item = models.WatchlistItem(user_id=user_id, movie_id=movie_id)
    try:
        db.add(new_item)
        db.commit()
        db.refresh(new_item)
        # Eager load the movie relationship for the response using joinedload after refresh
        # This requires querying again or careful session management.
        # Simpler: Query again with joinedload
        new_item_with_movie = db.query(models.WatchlistItem)\
                                .options(joinedload(models.WatchlistItem.movie))\
                                .filter(models.WatchlistItem.id == new_item.id)\
                                .first()

        if not new_item_with_movie: # Should not happen, but safety check
             raise HTTPException(status_code=500, detail="Failed to retrieve watchlist item after creation.")

        # Convert to Pydantic model for response
        return WatchlistItemResponse.model_validate(new_item_with_movie)

    except Exception as e:
        db.rollback()
        print(f"Error adding to watchlist: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not add item to watchlist.")


@app.delete("/watchlist/{movie_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove Movie from Watchlist")
def remove_from_watchlist(
    movie_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    user_id = current_user.id

    # Find the item in the watchlist
    db_item = db.query(models.WatchlistItem).filter(
        models.WatchlistItem.user_id == user_id,
        models.WatchlistItem.movie_id == movie_id
    ).first()

    if not db_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found in watchlist"
        )

    try:
        db.delete(db_item)
        db.commit()
        # No content to return for 204
        return None # Explicitly return None
    except Exception as e:
        db.rollback()
        print(f"Error removing from watchlist: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not remove item from watchlist.")


@app.get("/users/me/watchlist", response_model=List[WatchlistItemResponse], summary="Get Current User's Watchlist")
def get_user_watchlist(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """
    Retrieves all movies in the currently logged-in user's watchlist.
    """
    # Eager load the 'movie' relationship to include movie details in the response
    watchlist_items = db.query(models.WatchlistItem)\
                        .filter(models.WatchlistItem.user_id == current_user.id)\
                        .options(joinedload(models.WatchlistItem.movie))\
                        .order_by(desc(models.WatchlistItem.added_at))\
                        .all()
    # Convert list of SQLAlchemy models to list of Pydantic models
    return [WatchlistItemResponse.model_validate(item) for item in watchlist_items]



# --- Run the App ---
# (Removed the __main__ block as uvicorn is run from the command line)
# Example: python -m uvicorn main:app --reload --port 8000

