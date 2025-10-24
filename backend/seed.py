import pandas as pd
from sqlalchemy.orm import Session
from database import engine, Base, SessionLocal
from models import User, Movie, Rating
import os
import requests
import time

# --- ACTION REQUIRED ---
# Make sure your TMDB API Key is pasted here.
TMDB_API_KEY = "3d6e88772209e5b056e87d99b455595d" 
# ---------------------

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"

# Define file paths (looking in the root folder)
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(os.path.dirname(ROOT_DIR), "movies.db")
RATINGS_CSV = os.path.join(ROOT_DIR, "ratings.csv")
MOVIES_CSV = os.path.join(ROOT_DIR, "movies.csv")
LINKS_CSV = os.path.join(ROOT_DIR, "links.csv")

def get_movie_details(tmdb_id):
    """Fetches movie details from TMDB, including the poster path."""
    if pd.isna(tmdb_id):
        return None, None # No TMDB ID

    try:
        url = f"{TMDB_BASE_URL}/movie/{int(tmdb_id)}?api_key={TMDB_API_KEY}"
        response = requests.get(url)
        response.raise_for_status() # Raise an error for bad responses (4xx, 5xx)
        
        data = response.json()
        poster_path = data.get('poster_path')
        description = data.get('overview')
        
        full_poster_url = f"{TMDB_POSTER_BASE_URL}{poster_path}" if poster_path else None
        
        return full_poster_url, description

    except requests.exceptions.RequestException as e:
        # Don't print an error for 404, it just means the movie isn't in TMDB
        if e.response.status_code != 404:
            print(f"Error fetching data for tmdbId {tmdb_id}: {e}")
        return None, None
    except Exception as e:
        print(f"Error processing tmdbId {tmdb_id}: {e}")
        return None, None


def seed_database():
    print("Starting database seeding process...")
    
    # Recreate all tables
    print("Dropping and recreating all database tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    
    try:
        # --- Load Movies ---
        print(f"Loading movies from {MOVIES_CSV}")
        print(f"Loading links from {LINKS_CSV}")
        
        movies_df = pd.read_csv(MOVIES_CSV)
        links_df = pd.read_csv(LINKS_CSV)

        movies_df = pd.merge(movies_df, links_df, on='movieId', how='left')
        
        movie_count = 0
        for index, row in movies_df.iterrows():
            title = row['title'].strip()
            release_year = None
            if title.endswith(')'):
                try:
                    year_str = title[-5:-1]
                    if year_str.isdigit():
                        release_year = int(year_str)
                        title = title[:-7].strip() 
                except:
                    pass 
            
            tmdb_id = row.get('tmdbId') 
            poster_url, description = get_movie_details(tmdb_id)
            
            movie = Movie(
                id=int(row['movieId']),
                title=title,
                release_year=release_year,
                genres=row['genres'],
                description=description,
                poster_url=poster_url
            )
            db.add(movie)
            movie_count += 1

            if movie_count % 100 == 0:
                print(f"Processed {movie_count} movies...")
                
            time.sleep(0.05) 

        print(f"Committing {movie_count} movies to database...")
        db.commit()
        print(f"Successfully processed and added {movie_count} movies.")
        
        # --- Load Ratings (and Users) ---
        print(f"Loading ratings from {RATINGS_CSV}")
        ratings_df = pd.read_csv(RATINGS_CSV)
        
        user_ids = ratings_df['userId'].unique()
        user_count = 0
        for user_id in user_ids:
            new_user = User(
                id=int(user_id),
                username=f"user_{int(user_id)}",
                email=f"user{int(user_id)}@movierec.com",
                hashed_password="default_hash" 
            )
            db.add(new_user)
            user_count += 1
        
        print(f"Committing {user_count} users...")
        db.commit()
        print(f"Successfully processed and added {user_count} users.")

        print("Adding ratings (this may take a moment)...")
        rating_count = 0
        for index, row in ratings_df.iterrows():
            #
            # --- THIS IS THE FIX ---
            #
            rating = Rating(
                user_id=int(row['userId']),
                movie_id=int(row['movieId']),
                score=float(row['rating']) # <-- WAS 'score', NOW 'rating'
            )
            db.add(rating)
            rating_count += 1
            
            if rating_count % 10000 == 0:
                print(f"Committed {rating_count} ratings...")
                db.commit()

        print(f"Committing final batch of ratings...")
        db.commit()
        print(f"Successfully processed and added {rating_count} ratings.")

        print("\nDatabase seeding complete!")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    if not TMDB_API_KEY or TMDB_API_KEY == "3d6e88772209e5b056e87d99b455595d":
        print("="*50)
        print("ERROR: Please paste your TMDB API key into the 'TMDB_API_KEY' variable in seed.py")
        print("="*50)
    else:
        if os.path.exists(DB_FILE):
            print(f"WARNING: Database file '{DB_FILE}' already exists.")
            confirm = input("This will DELETE all existing data. Continue? (y/n): ")
            if confirm.lower() != 'y':
                print("Seeding aborted.")
                exit()
        
        seed_database()

