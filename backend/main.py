import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
import sqlalchemy # Import sqlalchemy for exc
from sqlalchemy import create_engine, text # Added text
from sqlalchemy.orm import sessionmaker, relationship, Session, joinedload # Added joinedload
from pydantic import BaseModel, HttpUrl
from typing import List, Optional
from datetime import datetime, timedelta, timezone # Added timezone
import os
import time # Added time
import sys # Added sys for exit

# Use DB URL from database.py logic (reads from env var)
# Ensure database.py loads .env correctly using load_dotenv from dotenv
from database import DATABASE_URL, engine as db_engine, Base, SessionLocal, get_db
import models # Use models from models.py
import auth # Use auth logic from auth.py
import ml_engine # Use ML logic from ml_engine.py

# --- Pydantic Schemas (API Validation) ---

# --- Movie Schemas ---
class MovieBase(BaseModel):
    title: str
    description: Optional[str] = None
    release_year: Optional[int] = None
    genres: Optional[str] = None
    poster_url: Optional[str] = None # Added poster_url

class MovieResponse(MovieBase):
    id: int
    # ratings: List['RatingResponse'] = [] # Comment out to prevent deep nesting issues if needed
    class Config:
        from_attributes = True

# --- Rating Schemas ---
class RatingBase(BaseModel):
    movie_id: int
    score: float # Expecting 0.5 to 5.0

class RatingCreate(RatingBase):
    # user_id will come from the authenticated user
    pass

class RatingResponse(RatingBase):
    id: int
    user_id: int
    class Config:
        from_attributes = True

# --- User Schemas ---
class UserBase(BaseModel):
    username: str
    email: str

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    # ratings: List[RatingResponse] = [] # Avoid including potentially large lists by default
    class Config:
        from_attributes = True

# --- Watchlist Schemas ---
class WatchlistItemBase(BaseModel):
     movie_id: int

class WatchlistItemCreate(WatchlistItemBase):
     pass # user_id comes from authenticated user

class WatchlistItemResponse(BaseModel):
     id: int
     user_id: int
     movie_id: int
     added_at: datetime # Use datetime type
     movie: MovieResponse # Include full movie details

     class Config:
         from_attributes = True


# --- FastAPI App ---
print("--- Initializing FastAPI App ---")
app = FastAPI(
    title="Movie Recommendation API",
    description="Full-stack app with ML, Auth, Watchlist, Posters, Genres",
    version="3.0.0"
)

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
    """
    Check if DB is populated, train ML model.
    TEMPORARY: Run seeder if DB is empty.
    """
    print("Running startup event...")
    db: Optional[Session] = None # Initialize db to None
    try:
        # Create tables if they don't exist
        print("Ensuring database tables exist...")
        Base.metadata.create_all(bind=db_engine)
        print("Tables checked/created.")

        db = SessionLocal() # Get a new session

        # Check if the 'movies' table is empty
        movie_count_query = text("SELECT count(id) FROM movies")
        movie_count = db.execute(movie_count_query).scalar_one_or_none() or 0
        print(f"Movie count in database: {movie_count}")

        if movie_count == 0:
            print("-" * 50)
            print("WARNING: Database appears to be empty.")
            # --- TEMPORARY SEED LOGIC (UNCOMMENTED FOR RENDER SEEDING) ---
            print("Attempting to run the seeder script...")
            print("This will take a long time and the server will be unresponsive.")
            print("-" * 50)
            sys.stdout.flush() # Ensure messages are printed before long task
            try:
                # IMPORTANT: Import seeder function *inside* here
                from seed import seed_database
                seed_database() # Run the full seeding process
                print("-" * 50)
                print("Seeding process attempted. Restarting ML model training check.")
                print("-" * 50)
                sys.stdout.flush()
                # Re-check count after seeding
                # Ensure db session is still valid or get a new one if needed
                if not db.is_active:
                    db = SessionLocal()
                movie_count = db.execute(movie_count_query).scalar_one_or_none() or 0
                print(f"Movie count after seeding attempt: {movie_count}")

            except ImportError:
                print(f"\n" + "="*20 + " ERROR DURING SEEDING IMPORT " + "="*20)
                print("Could not import the seeder function. Make sure seed.py exists.")
                print("="*60 + "\n")
                sys.stdout.flush()
            except Exception as seed_error:
                print(f"\n" + "="*20 + " ERROR DURING SEEDING EXECUTION " + "="*20)
                print(f"An error occurred while trying to run the seeder: {seed_error}")
                print("The database might be partially seeded or still empty.")
                print("Please check the seeder script and logs.")
                print("="*60 + "\n")
                sys.stdout.flush()
                # Allow server to continue starting even if seeding fails
            # --- END TEMPORARY SEED LOGIC ---
        else:
            print(f"Database already populated with {movie_count} movies.")

        # --- Train the ML model on startup (only if DB has data) ---
        # Make sure we have a valid session before training
        if movie_count > 0:
            if not db or not db.is_active:
                 db = SessionLocal() # Get a fresh session if needed

            print("Attempting to train collaborative filtering model...")
            sys.stdout.flush()
            start_time = time.time()
            # Ensure the background task wrapper exists and is called correctly
            # NOTE: Running train_collaborative_model directly during startup might block
            # If training takes too long, Render might kill the process before it finishes seeding/training.
            # Consider if the background task wrapper can be used even in startup.
            # For simplicity now, call directly, but be aware of timeout risks.
            try:
                # ml_engine.train_collaborative_model_task() # Call the wrapper task - Needs careful session handling
                ml_engine.train_collaborative_model(db) # Call directly for now
                end_time = time.time()
                print(f"Model training complete. Time taken: {end_time - start_time:.2f} seconds")
            except Exception as train_error:
                print(f"ERROR during model training: {train_error}")

        else:
            print("Skipping model training as database is empty.")


        print("Startup logic finished.")
        sys.stdout.flush()

    except sqlalchemy.exc.OperationalError as db_conn_err:
        print(f"\n" + "="*20 + " DATABASE CONNECTION ERROR DURING STARTUP " + "="*20)
        print(f"Could not connect to the database: {db_conn_err}")
        print("Please check DATABASE_URL environment variable and ensure the database server is running.")
        print("="*70 + "\n")
        sys.stdout.flush()
        # Decide if the app should exit or try to continue (might fail later)
        # For Render, it might keep restarting, so allowing to proceed might be okay.
    except Exception as e:
        # Catch other errors during DB connection or initial query
        print(f"\n" + "="*20 + " UNEXPECTED ERROR DURING STARTUP " + "="*20)
        print(f"An unexpected error occurred during application startup: {e}")
        print("="*60 + "\n")
        sys.stdout.flush()
    finally:
        if db and db.is_active: # Ensure db session is closed if opened and active
            db.close()
        print("Startup event finished.")
        sys.stdout.flush()


# --- API Endpoints ---

@app.get("/", summary="Root")
def read_root():
    return {"message": "Welcome to the MovieRec API v3"}

# --- Authentication Endpoints ---

@app.post("/register/", response_model=UserResponse, status_code=status.HTTP_201_CREATED, summary="Register a new user")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    """Registers a new user in the database."""
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    if len(user.password.encode('utf-8')) > 1024:
         print(f"Registration failed for {user.email}: Password too long.")
         raise HTTPException(status_code=400, detail="Password is too long.")

    try:
        hashed_password = auth.get_password_hash(user.password)
    except ValueError as ve:
        print(f"Password hashing failed for {user.email}: {ve}")
        raise HTTPException(status_code=400, detail=f"Invalid password: {ve}")
    except Exception as e:
        print(f"Unexpected error hashing password for {user.email}: {e}")
        raise HTTPException(status_code=500, detail="Error processing password.")

    new_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        print(f"User registered successfully: ID={new_user.id}, Email={new_user.email}")
        return UserResponse.model_validate(new_user)
    except sqlalchemy.exc.IntegrityError as e:
        db.rollback()
        print(f"Database integrity error during registration for {user.email}: {e}")
        error_info = str(e.orig) if hasattr(e, 'orig') else str(e)
        if "users_email_key" in error_info or "UNIQUE constraint failed: users.email" in error_info:
             raise HTTPException(status_code=400, detail="Email already registered.")
        elif "users_username_key" in error_info or "UNIQUE constraint failed: users.username" in error_info:
             raise HTTPException(status_code=400, detail="Username already taken.")
        else:
             raise HTTPException(status_code=500, detail="Database error during registration.")
    except Exception as e:
        db.rollback()
        print(f"Unexpected database error during registration for {user.email}: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred during registration.")


@app.post("/token/", response_model=auth.Token, summary="Login and get an access token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Handles user login via form data and returns a JWT token."""
    print(f"Login attempt for username (email): {form_data.username}")
    user = auth.authenticate_user(db, email=form_data.username, password=form_data.password)
    if not user:
        print(f"Login failed for: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    print(f"Login successful for user ID: {user.id}")
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me/", response_model=UserResponse, summary="Get current user details")
async def read_users_me(current_user: models.User = Depends(auth.get_current_active_user)):
    """Returns the details of the currently authenticated user."""
    return UserResponse.model_validate(current_user)

# --- Movie Endpoints ---

@app.get("/movies/", response_model=List[MovieResponse], summary="Get Movies (with Search and Genre Filter)")
def get_movies(
    search: Optional[str] = Query(None, description="Search term for movie titles"),
    genre: Optional[str] = Query(None, description="Filter movies by genre"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Fetches a list of movies, optionally filtered by search term or genre."""
    try:
        query = db.query(models.Movie)
        if search:
            query = query.filter(models.Movie.title.ilike(f"%{search}%"))
        if genre:
            if hasattr(models.Movie, 'genres'):
                 query = query.filter(models.Movie.genres.ilike(f"%{genre}%"))
            else:
                 print("Warning: Movie model does not have 'genres' attribute for filtering.")

        query = query.order_by(models.Movie.release_year.desc().nullslast(), models.Movie.title)
        movies = query.offset(skip).limit(limit).all()
        return [MovieResponse.model_validate(movie) for movie in movies]
    except Exception as e:
         print(f"Error fetching movies: {e}")
         raise HTTPException(status_code=500, detail="Could not fetch movies.")


@app.get("/movies/{movie_id}", response_model=MovieResponse, summary="Get Movie by ID")
def get_movie_by_id(movie_id: int, db: Session = Depends(get_db)):
    """Fetches details for a single movie by its ID."""
    try:
        movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found")
        return MovieResponse.model_validate(movie)
    except Exception as e:
         print(f"Error fetching movie {movie_id}: {e}")
         raise HTTPException(status_code=500, detail="Could not fetch movie details.")

# --- Rating Endpoints ---

@app.post("/ratings/", response_model=RatingResponse, status_code=status.HTTP_201_CREATED, summary="Rate a Movie")
def create_or_update_rating(
    rating: RatingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Creates a new rating or updates an existing one for the current user."""
    movie = db.query(models.Movie).filter(models.Movie.id == rating.movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    if not (0.5 <= rating.score <= 5.0 and (rating.score * 2) % 1 == 0):
         raise HTTPException(status_code=400, detail="Invalid score: must be between 0.5 and 5.0 in 0.5 increments.")

    db_rating = db.query(models.Rating).filter(
        models.Rating.user_id == current_user.id,
        models.Rating.movie_id == rating.movie_id
    ).first()

    if db_rating:
        print(f"Updating rating for user {current_user.id}, movie {rating.movie_id} to {rating.score}")
        db_rating.score = rating.score
    else:
        print(f"Creating new rating for user {current_user.id}, movie {rating.movie_id} with score {rating.score}")
        db_rating = models.Rating(
            user_id=current_user.id,
            movie_id=rating.movie_id,
            score=rating.score
        )
        db.add(db_rating)

    try:
        db.commit()
        db.refresh(db_rating)

        print("Rating submitted. Queuing model retrain in background.")
        # Ensure the background task function handles its own DB session
        background_tasks.add_task(ml_engine.train_collaborative_model_task)

        return RatingResponse.model_validate(db_rating)

    except sqlalchemy.exc.IntegrityError as e:
         db.rollback()
         print(f"Error submitting rating (IntegrityError): {e}")
         raise HTTPException(status_code=500, detail="Database error processing rating.")
    except Exception as e:
         db.rollback()
         print(f"Error submitting rating (Exception): {e}")
         raise HTTPException(status_code=500, detail="Error processing rating.")


@app.get("/users/me/ratings", response_model=List[RatingResponse], summary="Get current user's ratings")
def get_user_ratings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Fetches all movie ratings submitted by the currently authenticated user."""
    try:
        ratings = db.query(models.Rating).filter(models.Rating.user_id == current_user.id).all()
        return [RatingResponse.model_validate(rating) for rating in ratings]
    except Exception as e:
         print(f"Error fetching ratings for user {current_user.id}: {e}")
         raise HTTPException(status_code=500, detail="Could not fetch user ratings.")


# --- Recommendation Endpoint ---

@app.get("/recommendations/", response_model=List[MovieResponse], summary="Get Hybrid Recommendations")
def get_recommendations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """
    Get hybrid recommendations for the current logged-in user.
    Uses cold-start strategy if user has few ratings.
    """
    user_id = current_user.id
    print(f"Getting recommendations for user_id: {user_id}")
    try:
        min_ratings_for_ml = 5
        user_rating_count = db.query(models.Rating).filter(models.Rating.user_id == user_id).count()
        print(f"User {user_id} has {user_rating_count} ratings.")

        if user_rating_count < min_ratings_for_ml:
            print(f"User {user_id} has fewer than {min_ratings_for_ml} ratings. Using cold-start (popular movies).")
            rated_movie_ids_query = db.query(models.Rating.movie_id).filter(models.Rating.user_id == user_id)
            rated_movie_ids = {row[0] for row in rated_movie_ids_query.all()}
            print(f"User {user_id} has rated movie IDs: {rated_movie_ids}")

            popular_movies_query = (
                db.query(models.Movie)
                .filter(models.Movie.id.notin_(rated_movie_ids))
                .order_by(models.Movie.id.desc())
                .limit(20)
            )
            recommendations = popular_movies_query.all()
            print(f"Cold start recommendations (first few IDs): {[m.id for m in recommendations[:5]]}")

        else:
            print(f"User {user_id} has enough ratings. Using hybrid ML engine.")
            recommended_movie_ids = ml_engine.get_hybrid_recommendations(user_id, db, num_recs=12)

            if not recommended_movie_ids:
                 print(f"ML engine returned no recs for user {user_id}. Falling back to simple list.")
                 rated_movie_ids_query = db.query(models.Rating.movie_id).filter(models.Rating.user_id == user_id)
                 rated_movie_ids = {row[0] for row in rated_movie_ids_query.all()}
                 fallback_movies = db.query(models.Movie).filter(models.Movie.id.notin_(rated_movie_ids)).order_by(models.Movie.id.desc()).limit(12).all()
                 recommendations = fallback_movies
            else:
                 recommended_movies = db.query(models.Movie).filter(models.Movie.id.in_(recommended_movie_ids)).all()
                 movie_map = {movie.id: movie for movie in recommended_movies}
                 ordered_recs = [movie_map[movie_id] for movie_id in recommended_movie_ids if movie_id in movie_map]
                 recommendations = ordered_recs
                 print(f"ML recommendations (first few IDs): {recommended_movie_ids[:5]}")

        final_recs = [MovieResponse.model_validate(movie) for movie in recommendations[:12]]
        print(f"Returning {len(final_recs)} recommendations.")
        return final_recs

    except Exception as e:
         print(f"Error getting recommendations for user {user_id}: {e}")
         raise HTTPException(status_code=500, detail="Could not generate recommendations.")


# --- Watchlist Endpoints ---

@app.post("/watchlist/", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED, summary="Add movie to watchlist")
def add_to_watchlist(
    item: WatchlistItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Adds a movie to the currently authenticated user's watchlist."""
    movie = db.query(models.Movie).filter(models.Movie.id == item.movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    existing_item = db.query(models.WatchlistItem).filter(
        models.WatchlistItem.user_id == current_user.id,
        models.WatchlistItem.movie_id == item.movie_id
    ).first()
    if existing_item:
        existing_item_with_movie = db.query(models.WatchlistItem).options(
            joinedload(models.WatchlistItem.movie)
        ).filter(models.WatchlistItem.id == existing_item.id).one()
        return WatchlistItemResponse.model_validate(existing_item_with_movie)

    db_item = models.WatchlistItem(user_id=current_user.id, movie_id=item.movie_id, added_at=datetime.now(timezone.utc))
    try:
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        db_item_with_movie = db.query(models.WatchlistItem).options(
            joinedload(models.WatchlistItem.movie)
        ).filter(models.WatchlistItem.id == db_item.id).one()
        return WatchlistItemResponse.model_validate(db_item_with_movie)
    except sqlalchemy.exc.IntegrityError as e:
         db.rollback()
         print(f"Watchlist add IntegrityError: {e}")
         existing_item = db.query(models.WatchlistItem).filter(
             models.WatchlistItem.user_id == current_user.id,
             models.WatchlistItem.movie_id == item.movie_id
         ).options(joinedload(models.WatchlistItem.movie)).first()
         if existing_item:
              return WatchlistItemResponse.model_validate(existing_item)
         else:
             raise HTTPException(status_code=500, detail="Database error adding to watchlist.")
    except Exception as e:
         db.rollback()
         print(f"Watchlist add Exception: {e}")
         raise HTTPException(status_code=500, detail="Error adding to watchlist.")


@app.delete("/watchlist/{movie_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove movie from watchlist")
def remove_from_watchlist(
    movie_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Removes a movie from the currently authenticated user's watchlist."""
    item = db.query(models.WatchlistItem).filter(
        models.WatchlistItem.user_id == current_user.id,
        models.WatchlistItem.movie_id == movie_id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Watchlist item not found")

    try:
        db.delete(item)
        db.commit()
        return None
    except Exception as e:
        db.rollback()
        print(f"Watchlist delete Exception: {e}")
        raise HTTPException(status_code=500, detail="Error removing from watchlist.")


@app.get("/users/me/watchlist", response_model=List[WatchlistItemResponse], summary="Get current user's watchlist")
def get_user_watchlist(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Fetches all movies in the currently authenticated user's watchlist."""
    try:
        watchlist_items = (
            db.query(models.WatchlistItem)
            .options(joinedload(models.WatchlistItem.movie))
            .filter(models.WatchlistItem.user_id == current_user.id)
            .order_by(models.WatchlistItem.added_at.desc())
            .all()
        )
        return [WatchlistItemResponse.model_validate(item) for item in watchlist_items]
    except Exception as e:
         print(f"Error fetching watchlist for user {current_user.id}: {e}")
         raise HTTPException(status_code=500, detail="Could not fetch watchlist.")

# --- (Removed the __main__ block as uvicorn is run from the command line) ---

