import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

# --- New Imports ---
# (Dots removed from these imports)
import ml_engine
import models  # Import from models.py
from database import SessionLocal, engine, get_db, Base  # Import from database.py

# --- Pydantic Schemas (API Validation) ---
# These stay the same
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

class MovieBase(BaseModel):
    title: str
    description: str
    release_year: int
    genres: str

class MovieResponse(MovieBase):
    id: int
    ratings: List[RatingResponse] = []
    class Config:
        from_attributes = True

class UserBase(BaseModel):
    username: str
    email: str

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    ratings: List[RatingResponse] = []
    class Config:
        from_attributes = True

# --- FastAPI App ---
app = FastAPI(
    title="Movie Recommendation API",
    description="Day 2: ML Engine Integrated (Refactored).",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Mock Data Seeding ---
def populate_database(db: Session):
    if db.query(models.Movie).count() == 0:
        mock_movies = [
            models.Movie(title="Inception", description="A thief who steals corporate secrets through use of dream-sharing technology...", release_year=2010, genres="Sci-Fi,Thriller,Action"),
            models.Movie(title="The Shawshank Redemption", description="Two imprisoned men bond over a number of years, finding solace...", release_year=1994, genres="Drama"),
            models.Movie(title="The Dark Knight", description="When the menace known as the Joker emerges...", release_year=2008, genres="Action,Crime,Drama"),
            models.Movie(title="Pulp Fiction", description="The lives of two mob hitmen, a boxer, a gangster's wife...", release_year=1994, genres="Crime,Drama"),
            models.Movie(title="Forrest Gump", description="The presidencies of Kennedy and Johnson, the Vietnam War...", release_year=1994, genres="Drama,Romance"),
            models.Movie(title="The Matrix", description="A computer hacker learns from mysterious rebels about the true nature of his reality...", release_year=1999, genres="Action,Sci-Fi"),
            models.Movie(title="Goodfellas", description="The story of Henry Hill and his life in the mob...", release_year=1990, genres="Biography,Crime,Drama"),
            models.Movie(title="Interstellar", description="A team of explorers travel through a wormhole in space...", release_year=2014, genres="Adventure,Drama,Sci-Fi"),
            models.Movie(title="Parasite", description="Greed and class discrimination threaten the newly formed symbiotic relationship...", release_year=2019, genres="Comedy,Drama,Thriller"),
            models.Movie(title="Spirited Away", description="During her family's move to the suburbs, a 10-year-old girl wanders into a world...", release_year=2001, genres="Animation,Adventure,Family"),
            models.Movie(title="The Grand Budapest Hotel", description="The adventures of Gustave H, a legendary concierge...", release_year=2014, genres="Adventure,Comedy,Crime"),
            models.Movie(title="Mad Max: Fury Road", description="In a post-apocalyptic wasteland, a woman rebels...", release_year=2015, genres="Action,Adventure,Sci-Fi"),
            models.Movie(title="Blade Runner 2049", description="Young Blade Runner K's discovery of a long-buried secret...", release_year=2017, genres="Action,Drama,Mystery"),
            models.Movie(title="Dune", description="Feature adaptation of Frank Herbert's science fiction novel...", release_year=2021, genres="Action,Adventure,Drama"),
            models.Movie(title="Oppenheimer", description="The story of American scientist J. Robert Oppenheimer...", release_year=2023, genres="Biography,Drama,History")
        ]
        db.add_all(mock_movies)
        
        mock_user = models.User(username="testuser", email="test@example.com", hashed_password="notarealhash")
        db.add(mock_user)
        db.commit() # Commit user first to get ID=1

        mock_ratings = [
            models.Rating(user_id=1, movie_id=1, score=5.0), # Likes Inception
            models.Rating(user_id=1, movie_id=3, score=5.0), # Likes Dark Knight
            models.Rating(user_id=1, movie_id=6, score=4.5), # Likes The Matrix
            models.Rating(user_id=1, movie_id=14, score=4.0), # Likes Dune
        ]
        db.add_all(mock_ratings)
        db.commit()
        print("Database populated with mock data.")
    else:
        print("Database already populated.")

# --- Startup Event ---
@app.on_event("startup")
def on_startup():
    models.Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        populate_database(db)
        ml_engine.train_collaborative_model(db)
    except Exception as e:
        print(f"Error on startup: {e}")
    finally:
        db.close()

# --- API Endpoints ---
@app.get("/", summary="Root")
def read_root():
    return {"message": "Welcome to the Movie Recommendation API (Day 2)"}

@app.post("/users/", response_model=UserResponse, summary="Create User")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    new_user = models.User(username=user.username, email=user.email, hashed_password=user.password)
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
        query = query.filter(models.Movie.title.contains(search))
    movies = query.offset(skip).limit(limit).all()
    return movies

@app.get("/movies/{movie_id}", response_model=MovieResponse, summary="Get Movie by ID")
def get_movie_by_id(movie_id: int, db: Session = Depends(get_db)):
    movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie

@app.post("/ratings/", response_model=RatingResponse, summary="Rate a Movie")
def create_or_update_rating(rating: RatingCreate, db: Session = Depends(get_db)):
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
        db_rating.score = rating.score
    else:
        db_rating = models.Rating(**rating.dict())
        db.add(db_rating)
    
    db.commit()
    db.refresh(db_rating)
    
    print("New rating added. Retraining model...")
    try:
        ml_engine.train_collaborative_model(db)
    except Exception as e:
        print(f"Error retraining model: {e}")

    return db_rating

@app.get("/recommendations/{user_id}", response_model=List[MovieResponse], summary="Get Hybrid Recommendations")
def get_recommendations(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    recommended_movie_ids = ml_engine.get_hybrid_recommendations(user_id, db, num_recs=10)
    
    if not recommended_movie_ids:
        print("ML engine returned no recs. Falling back to simple list.")
        rated_movie_ids = {r.movie_id for r in user.ratings}
        all_movies = db.query(models.Movie).all()
        recommendations = [movie for movie in all_movies if movie.id not in rated_movie_ids]
        return recommendations[:10]

    recommended_movies = db.query(models.Movie).filter(models.Movie.id.in_(recommended_movie_ids)).all()
    
    movie_map = {movie.id: movie for movie in recommended_movies}
    ordered_recs = [movie_map[movie_id] for movie_id in recommended_movie_ids if movie_id in movie_map]
    
    return ordered_recs

# --- Run the App ---
if __name__ == "__main__":
    print("--- Starting FastAPI Server (Day 2 - Refactored) ---")
    print("Access the API docs at http://127.0.0.1:8000/docs")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

