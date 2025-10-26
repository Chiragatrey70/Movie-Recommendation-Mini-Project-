import pandas as pd
import sqlalchemy
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Float, ForeignKey, DateTime, UniqueConstraint, inspect, text
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
# Use DB URL from database.py logic (reads from env var)
from database import DATABASE_URL, engine as db_engine, Base, SessionLocal, get_db
# Use models from models.py
import models
# Use the hashing function defined within seed.py itself
# from auth import get_password_hash # Removed import from auth
import os
import requests
import time
import sys # For flushing output
from datetime import datetime, timezone # Added timezone
from dotenv import load_dotenv # Import load_dotenv
from passlib.context import CryptContext # Import for password hashing helper

# --- Configuration ---
# Load environment variables first (looks for .env in parent dir)
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)

# Read TMDB API Key from Environment Variable
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"

# --- Define file paths (Looking in the root folder) ---
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Project Root
DB_FILE = DATABASE_URL # Use the URL loaded by database.py
RATINGS_CSV = os.path.join(ROOT_DIR, "backend", "ratings.csv") # Path relative to project root
MOVIES_CSV = os.path.join(ROOT_DIR, "backend", "movies.csv") # Path relative to project root
LINKS_CSV = os.path.join(ROOT_DIR, "backend", "links.csv") # Path relative to project root

# --- Helper Function for TMDB API ---
def get_movie_details(tmdb_id):
    """Fetches movie details from TMDB API."""
    if not tmdb_id or not TMDB_API_KEY:
        return None
    try:
        url = f"{TMDB_BASE_URL}/movie/{tmdb_id}?api_key={TMDB_API_KEY}"
        response = requests.get(url)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        data = response.json()
        poster_path = data.get('poster_path')
        return poster_path
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for tmdbId {tmdb_id}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error processing tmdbId {tmdb_id}: {e}")
        return None

# --- Password Hashing Helper (Copied from auth.py to avoid import issues) ---
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")
def get_password_hash(password):
    if len(password.encode('utf-8')) > 1024:
         raise ValueError("Password is too long.")
    return pwd_context.hash(password)
# --- End Helper ---

# --- Main Seeding Function ---
def seed_database():
    """Drops existing tables, recreates them, reads CSV files and populates the database."""
    print("\n--- Starting Database Seeding ---")

    # Check for API Key
    if not TMDB_API_KEY or not TMDB_API_KEY.strip():
         print("ERROR: TMDB_API_KEY environment variable not found or empty.")
         sys.exit(1) # Exit if key is missing

    # --- Confirmation Prompt ---
    is_interactive = sys.stdout.isatty()
    confirm = 'y'
    if is_interactive:
        print(f"\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(f"!! WARNING: This script WILL FIRST DROP ALL EXISTING TABLES (movies, users, ratings, watchlistitems) !!")
        print(f"!! in the database: {'postgresql://.../...@...' if DATABASE_URL.startswith('postgresql') else DATABASE_URL}")
        print(f"!! Then it will recreate them and populate data.")
        print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        confirm = input("ARE YOU SURE YOU WANT TO CONTINUE? (y/n): ").lower()

    if confirm != 'y':
        print("Seeding aborted.")
        return
    # --- End Confirmation ---

    # Get a database engine (needed for drop_all/create_all)
    engine = db_engine # Use the engine imported from database.py

    try:
        # --- MODIFICATION START: Drop existing tables ---
        print("\nDropping existing tables (if they exist)...")
        sys.stdout.flush()
        # Reflect metadata to ensure drop_all knows about tables, even if Base is slightly different
        meta = MetaData()
        meta.reflect(bind=engine)
        meta.drop_all(bind=engine)
        # Base.metadata.drop_all(bind=engine) # Alternative if reflection fails
        print("Existing tables dropped.")
        sys.stdout.flush()
        # --- MODIFICATION END ---

        print("\nCreating database tables...")
        sys.stdout.flush()
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully.")
        sys.stdout.flush()

    except Exception as e:
        print(f"\nERROR during table setup (drop/create): {e}")
        print("Cannot proceed with seeding.")
        sys.stdout.flush()
        sys.exit(1)


    # Get a database session for adding data
    db: Session = SessionLocal()

    try:
        # --- Load Links ---
        print(f"\nLoading links from {LINKS_CSV}...")
        sys.stdout.flush()
        try:
            links_df = pd.read_csv(LINKS_CSV)
            links_df = links_df[pd.to_numeric(links_df['tmdbId'], errors='coerce').notnull()]
            links_df['tmdbId'] = links_df['tmdbId'].astype(int)
            movie_to_tmdb_map = pd.Series(links_df.tmdbId.values, index=links_df.movieId).to_dict()
            print(f"Loaded {len(movie_to_tmdb_map)} movie links.")
            sys.stdout.flush()
        except FileNotFoundError:
            print(f"ERROR: links.csv not found at {LINKS_CSV}.")
            db.close()
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: Failed to load or process links.csv: {e}")
            db.close()
            sys.exit(1)

        # --- Load Movies ---
        print(f"\nLoading movies from {MOVIES_CSV}...")
        sys.stdout.flush()
        try:
            movies_df = pd.read_csv(MOVIES_CSV)
            print(f"Fetching details for {len(movies_df)} movies from TMDB (this will take several minutes)...")
            sys.stdout.flush()
        except FileNotFoundError:
            print(f"ERROR: movies.csv not found at {MOVIES_CSV}.")
            db.close()
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: Failed to load or process movies.csv: {e}")
            db.close()
            sys.exit(1)

        movies_to_add = []
        processed_movie_ids = set()
        start_time = time.time()
        api_call_count = 0

        # No need to check existing movies as we dropped tables
        # existing_movie_ids = set()
        # print(f"Database starts with 0 movies.")

        for index, row in movies_df.iterrows():
            try: # Add try block for processing each movie row
                movie_id = int(row['movieId'])
            except (ValueError, TypeError):
                print(f"Skipping movie at index {index}: Invalid movieId.")
                continue


            tmdb_id = movie_to_tmdb_map.get(movie_id)
            poster_url = None
            if tmdb_id:
                poster_url = get_movie_details(tmdb_id)
                api_call_count += 1
                time.sleep(0.05)

            title = row.get('title', '').strip()
            year_str = ''.join(filter(str.isdigit, title[-5:]))
            release_year = int(year_str) if year_str.isdigit() and len(year_str) == 4 else None
            if release_year and title.endswith(f" ({release_year})"):
                 title = title[:-len(f" ({release_year})")].strip()
            elif '(' in title and ')' in title and title[-1] == ')':
                 potential_year_part = title[title.rfind('('):]
                 if len(potential_year_part) > 2 and potential_year_part[1:-1].replace('-','').isdigit():
                      title = title[:title.rfind('(')].strip()

            if not title:
                 print(f"Skipping movie with ID {movie_id} due to missing title.")
                 continue

            movie = models.Movie(
                id=movie_id,
                title=title if title else "Unknown Title",
                genres=row.get('genres') if pd.notna(row.get('genres')) else "N/A",
                description=None,
                release_year=release_year,
                poster_url=poster_url
            )
            movies_to_add.append(movie)
            processed_movie_ids.add(movie_id)

            if (index + 1) % 100 == 0 or index == len(movies_df) - 1:
                elapsed_time = time.time() - start_time
                print(f"Processed {index + 1}/{len(movies_df)} movies... ({elapsed_time:.2f} seconds elapsed, {api_call_count} API calls)")
                sys.stdout.flush()

        if movies_to_add:
            try:
                # Add movies one by one for resilience
                added_count = 0
                for movie_obj in movies_to_add:
                    try:
                        db.add(movie_obj)
                        db.flush()
                        added_count += 1
                    except sqlalchemy.exc.IntegrityError: # Should not happen with drop_all
                        db.rollback()
                        print(f"Skipping duplicate movie ID during add: {movie_obj.id}")
                    except Exception as e_inner:
                        db.rollback()
                        print(f"Error adding movie ID {movie_obj.id}: {e_inner}. Skipping.")
                db.commit()
                print(f"Successfully added {added_count} new movies.")
                sys.stdout.flush()
            except Exception as e:
                 print(f"\nERROR during final movie commit: {e}. Rolling back.")
                 db.rollback()
        else:
            print("No movies processed to add.")


        # --- Load Users ---
        print(f"\nLoading ratings from {RATINGS_CSV} to find users...")
        sys.stdout.flush()
        try:
            ratings_df = pd.read_csv(RATINGS_CSV)
            ratings_df = ratings_df[pd.to_numeric(ratings_df['userId'], errors='coerce').notnull()]
            ratings_df['userId'] = ratings_df['userId'].astype(int)
            user_ids = ratings_df['userId'].unique()
            print(f"Found {len(user_ids)} unique users. Creating user objects...")
            sys.stdout.flush()
        except FileNotFoundError:
            print(f"ERROR: ratings.csv not found at {RATINGS_CSV}.")
            db.close()
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: Failed to load or process ratings.csv for users: {e}")
            db.close()
            sys.exit(1)

        users_to_add = []
        processed_user_ids = set()

        # No need to check existing users
        # existing_user_ids = set()
        # print(f"Database starts with 0 users.")

        for user_id in user_ids:
             user_id_int = int(user_id)
             try:
                 hashed_password = get_password_hash("password123")
                 user = models.User(
                     id=user_id_int,
                     username=f"user_{user_id_int}",
                     email=f"user_{user_id_int}@example.com",
                     hashed_password=hashed_password
                 )
                 users_to_add.append(user)
                 processed_user_ids.add(user_id_int)
             except Exception as e_hash:
                 print(f"Error creating user {user_id_int}: {e_hash}. Skipping.")

        if users_to_add:
             try:
                 db.add_all(users_to_add)
                 db.commit()
                 print(f"Successfully processed and added {len(users_to_add)} new users.")
                 sys.stdout.flush()
             except Exception as e: # Catch broader errors as duplicates shouldn't happen
                 print(f"\nERROR during user batch commit: {e}. Rolling back batch.")
                 db.rollback()
                 processed_user_ids = set() # Reset processed users on failure
        else:
             print("No users processed to add.")


        # --- Load Ratings ---
        print(f"\nAdding ratings (this may take a moment)...")
        sys.stdout.flush()
        ratings_count = 0
        added_ratings_count = 0
        batch_size = 10000
        ratings_to_add = []
        start_time = time.time()

        for index, row in ratings_df.iterrows():
            try:
                user_id = int(row['userId'])
                movie_id = int(row['movieId'])
                rating_score = float(row['rating'])
            except (ValueError, TypeError):
                # print(f"Skipping rating at index {index}: Invalid data types.") # Can be noisy
                continue

            # Check if user and movie were successfully added earlier
            if user_id not in processed_user_ids:
                continue
            if movie_id not in processed_movie_ids:
                continue

            if not (0.5 <= rating_score <= 5.0):
                # print(f"Skipping rating for user {user_id}, movie {movie_id}: Invalid score {rating_score}") # Can be noisy
                continue

            rating = models.Rating(
                user_id=user_id,
                movie_id=movie_id,
                score=rating_score
            )
            ratings_to_add.append(rating)
            ratings_count += 1

            # Commit in batches
            if ratings_count % batch_size == 0 or index == len(ratings_df) - 1:
                batch_start_index = index - len(ratings_to_add) + 1
                try:
                    db.add_all(ratings_to_add)
                    db.commit()
                    added_ratings_count += len(ratings_to_add)
                    elapsed_time = time.time() - start_time
                    print(f"Committed batch ending at index {index}. Total ratings added: {added_ratings_count}. ({elapsed_time:.2f} seconds elapsed)")
                    sys.stdout.flush()
                    ratings_to_add = []
                except Exception as e: # Catch broader errors as duplicates shouldn't happen
                     db.rollback()
                     print(f"\nERROR during rating batch commit (index ~{batch_start_index}-{index}): {e}. Rolling back and skipping batch.")
                     ratings_to_add = []

        # Final check (should be empty)
        if ratings_to_add:
             print("Attempting to commit final small batch...")
             try:
                 db.add_all(ratings_to_add)
                 db.commit()
                 added_ratings_count += len(ratings_to_add)
                 print(f"Committed final batch of {len(ratings_to_add)} ratings. Total added: {added_ratings_count}.")
                 sys.stdout.flush()
             except Exception as e:
                 print(f"\nERROR during final rating batch commit: {e}. Rolling back.")
                 db.rollback()


        total_time = time.time() - start_time
        print(f"\nSuccessfully processed {ratings_count} ratings and added {added_ratings_count} unique ratings in {total_time:.2f} seconds.")
        sys.stdout.flush()

        print("\nDatabase seeding complete!")
        sys.stdout.flush()

    except Exception as e:
        print(f"\nAn unexpected error occurred during seeding after table setup: {e}")
        try:
            db.rollback()
        except:
            pass
        sys.stdout.flush()
    finally:
        try:
            db.close()
            print("Database session closed.")
        except:
             pass
        sys.stdout.flush()

# --- Run the Seeder ---
if __name__ == "__main__":
    seed_database()


