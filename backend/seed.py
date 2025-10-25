import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, DATABASE_URL, create_tables # Use DB URL from database.py
from models import User, Movie, Rating, WatchlistItem # Use models from models.py

import os
import requests
import time
import sys # For flushing output
from datetime import datetime
from dotenv import load_dotenv # Import load_dotenv

# Load environment variables from .env file (optional, good for local dev)
load_dotenv()

# --- Configuration ---
# --- Read TMDB API Key from Environment Variable ---
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
if TMDB_API_KEY is None:
    # Fallback for local development if needed, but ideally set in .env
    TMDB_API_KEY = "3d6e88772209e5b056e87d99b455595d" # <-- PASTE YOUR KEY HERE FOR LOCAL FALLBACK
    print("WARNING: TMDB_API_KEY not found in environment. Using fallback value in seed.py. Set TMDB_API_KEY environment variable for deployment.")

# ----------------------------------------------------

# --- ADD DEBUG LINE ---
# print(f"DEBUG: Read TMDB_API_KEY as: '{TMDB_API_KEY}'")
# --- END ADDITION ---


TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500" # Base URL for posters

# --- Define file paths (Looking in the root folder) ---
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Project Root

# CSV file paths expected to be in the backend directory
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
MOVIES_CSV = os.path.join(BACKEND_DIR, "movies.csv")
RATINGS_CSV = os.path.join(BACKEND_DIR, "ratings.csv")
LINKS_CSV = os.path.join(BACKEND_DIR, "links.csv")


# --- Database Connection (Using DATABASE_URL from database.py) ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Helper Function for TMDB API ---
def get_movie_details(tmdb_id):
    """Fetches movie details (poster path) from TMDB API."""
    if not TMDB_API_KEY or not TMDB_API_KEY.strip():
        # This check might be redundant now if the getenv fails earlier, but safe to keep
        print("ERROR: TMDB_API_KEY is missing or invalid.")
        return None

    if not tmdb_id:
        return None

    api_url = f"{TMDB_BASE_URL}/movie/{tmdb_id}?api_key={TMDB_API_KEY}"
    try:
        response = requests.get(api_url)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        data = response.json()
        # Also fetch description if available
        description = data.get('overview')
        poster_path = data.get('poster_path')
        return poster_path, description # Return both
    except requests.exceptions.HTTPError as http_err:
         # Specifically catch HTTP errors (like 401, 404)
         print(f"HTTP error fetching data for tmdbId {tmdb_id}: {http_err} - URL: {api_url}")
         return None, None # Return None for both if error
    except requests.exceptions.RequestException as e:
        print(f"Request error fetching data for tmdbId {tmdb_id}: {e}")
        return None, None
    except Exception as e:
        print(f"An unexpected error occurred for tmdbId {tmdb_id}: {e}")
        return None, None

# --- Main Seeding Function ---
def seed_database():
    """Reads CSVs, fetches poster URLs, and populates the database."""
    confirm = input(f"WARNING: This script will connect to the database specified in database.py ({DATABASE_URL}) and populate/overwrite data. Continue? (y/n): ")
    if confirm.lower() != 'y':
        print("Seeding aborted.")
        exit()

    # Create tables defined in models.py
    create_tables()

    db: Session = SessionLocal()
    movie_count = 0
    user_count = 0
    rating_count = 0

    try:
        # --- 1. Load Links (TMDB IDs) ---
        print(f"\nLoading links from {LINKS_CSV}...")
        try:
            links_df = pd.read_csv(LINKS_CSV)
            links_df['tmdbId'] = pd.to_numeric(links_df['tmdbId'], errors='coerce').fillna(0).astype(int)
            tmdb_id_map = links_df.set_index('movieId')['tmdbId'].to_dict()
            print(f"Loaded {len(tmdb_id_map)} movie links.")
        except FileNotFoundError:
            print(f"ERROR: {LINKS_CSV} not found. Cannot fetch posters/descriptions.")
            tmdb_id_map = {}
        except Exception as e:
            print(f"Error reading {LINKS_CSV}: {e}")
            db.rollback()
            return

        # --- 2. Load Movies ---
        print(f"\nLoading movies from {MOVIES_CSV}...")
        try:
            movies_df = pd.read_csv(MOVIES_CSV)
        except FileNotFoundError:
             print(f"ERROR: {MOVIES_CSV} not found. Aborting seeding.")
             return
        except Exception as e:
            print(f"Error reading {MOVIES_CSV}: {e}")
            db.rollback()
            return

        print(f"Fetching details for {len(movies_df)} movies from TMDB (this will take several minutes)...")
        movies_to_add = []
        start_time = time.time()
        api_errors = 0
        for index, row in movies_df.iterrows():
            movie_id = row['movieId']
            tmdb_id = tmdb_id_map.get(movie_id)
            poster_path = None
            description = None # Initialize description
            if tmdb_id and tmdb_id > 0: # Check for valid tmdb_id
                details = get_movie_details(tmdb_id)
                if details:
                     poster_path, description = details
                else:
                     api_errors += 1
                time.sleep(0.05) # Rate limit API calls

            # Extract year from title
            title_year = row['title'].strip()
            year = None
            title = title_year
            if title_year.endswith(')'):
                try:
                    year_str = title_year[-5:-1]
                    if year_str.isdigit():
                        year = int(year_str)
                        title = title_year[:-7].strip()
                except ValueError:
                    pass

            movie = Movie(
                id=movie_id,
                title=title,
                release_year=year,
                genres=row['genres'],
                description=description, # Add description
                poster_url=poster_path
            )
            movies_to_add.append(movie)
            movie_count += 1

            if (index + 1) % 100 == 0:
                elapsed = time.time() - start_time
                print(f"Processed {index + 1}/{len(movies_df)} movies... ({api_errors} API errors) ({elapsed:.2f} seconds elapsed)", end='\r')
                sys.stdout.flush()

        print(f"\nProcessed {len(movies_df)} movies ({api_errors} TMDB API errors encountered). Adding to database...")
        db.add_all(movies_to_add)
        db.commit()
        print(f"Successfully processed and added {movie_count} movies.")


        # --- 3. Load Users (from Ratings) ---
        print(f"\nLoading ratings from {RATINGS_CSV} to find users...")
        try:
            ratings_df = pd.read_csv(RATINGS_CSV)
        except FileNotFoundError:
             print(f"ERROR: {RATINGS_CSV} not found. Aborting seeding.")
             db.rollback()
             return
        except Exception as e:
            print(f"Error reading {RATINGS_CSV}: {e}")
            db.rollback()
            return

        user_ids = ratings_df['userId'].unique()
        users_to_add = []
        print(f"Found {len(user_ids)} unique users. Creating user objects...")
        for user_id in user_ids:
            user = User(
                id=int(user_id),
                username=f"user_{user_id}",
                email=f"user{user_id}@movielens.local",
                hashed_password="DUMMY_PASSWORD_NOT_USABLE" # Placeholder - users must register properly
            )
            users_to_add.append(user)
            user_count += 1

        db.add_all(users_to_add)
        db.commit()
        print(f"Successfully processed and added {user_count} users.")


        # --- 4. Load Ratings ---
        print(f"\nAdding ratings (this may take a moment)...")
        ratings_to_add = []
        processed_ratings = 0
        skipped_ratings = 0
        start_time = time.time()

        # --- Pre-fetch existing user and movie IDs for faster validation ---
        # This is more memory-intensive but faster than querying per rating
        existing_user_ids = {user.id for user in db.query(User.id).all()}
        existing_movie_ids = {movie.id for movie in db.query(Movie.id).all()}
        print(f"Pre-fetched {len(existing_user_ids)} user IDs and {len(existing_movie_ids)} movie IDs for validation.")
        # --------------------------------------------------------------------

        for index, row in ratings_df.iterrows():
            try:
                user_id = int(row['userId'])
                movie_id = int(row['movieId'])
                score = float(row['rating'])

                # --- Use pre-fetched sets for validation ---
                if user_id not in existing_user_ids:
                    # print(f"\nSkipping rating at index {index} because user_id {user_id} does not exist in users table.")
                    skipped_ratings += 1
                    continue
                if movie_id not in existing_movie_ids:
                    # print(f"\nSkipping rating at index {index} because movie_id {movie_id} does not exist in movies table.")
                    skipped_ratings += 1
                    continue
                # ----------------------------------------

                rating = Rating(
                    user_id=user_id,
                    movie_id=movie_id,
                    score=score
                )
                ratings_to_add.append(rating)
                processed_ratings += 1

                # Commit in batches
                if processed_ratings % 10000 == 0:
                    db.add_all(ratings_to_add)
                    db.commit()
                    ratings_to_add = []
                    elapsed = time.time() - start_time
                    print(f"Committed {processed_ratings} ratings... ({skipped_ratings} skipped) ({elapsed:.2f} seconds elapsed)", end='\r')
                    sys.stdout.flush()

            except ValueError as ve:
                # print(f"\nSkipping rating at index {index} due to invalid data type: {ve}. Row: {row.to_dict()}")
                skipped_ratings += 1
            except Exception as e:
                 # print(f"\nSkipping rating at index {index} due to unexpected error: {e}. Row: {row.to_dict()}")
                 db.rollback() # Rollback potentially bad batch
                 ratings_to_add = [] # Clear batch on error
                 skipped_ratings += 1


        # Commit any remaining ratings
        if ratings_to_add:
            try:
                db.add_all(ratings_to_add)
                db.commit()
            except Exception as e:
                print(f"\nError committing final batch of ratings: {e}")
                db.rollback()
                skipped_ratings += len(ratings_to_add) # Count these as skipped
                processed_ratings -= len(ratings_to_add) # Adjust count


        elapsed = time.time() - start_time
        print(f"\nSuccessfully processed {processed_ratings + skipped_ratings} ratings total.")
        print(f"Added {processed_ratings} valid ratings, skipped {skipped_ratings} ratings in {elapsed:.2f} seconds.")
        rating_count = processed_ratings


        print("\nDatabase seeding complete!")

    except Exception as e:
        print(f"\nAn error occurred during seeding: {e}")
        db.rollback()
    finally:
        db.close()

# --- Run the Seeder ---
if __name__ == "__main__":
    # Add python-dotenv requirement for seed script too
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("Loaded environment variables from .env file.")
    except ImportError:
        print("python-dotenv not installed, cannot load .env file for seed script. Ensure environment variables are set manually.")

    # Check for TMDB API Key *before* asking confirmation
    if not os.getenv("TMDB_API_KEY") and not TMDB_API_KEY: # Check env var first, then fallback
          print("\n" + "="*60)
          print("ERROR: TMDB_API_KEY is not set.")
          print("Please set the TMDB_API_KEY environment variable or")
          print("paste your key directly into the seed.py file.")
          print("Get a key from: https://www.themoviedb.org/settings/api")
          print("="*60 + "\n")
          exit(1) # Exit if key is missing

    seed_database()

