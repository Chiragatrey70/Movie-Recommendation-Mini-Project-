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
# --- ADD THIS IMPORT ---
from auth import get_password_hash # Import the hashing function
# --- END ADDITION ---
import os
import requests
import time
import sys # For flushing output
from datetime import datetime # For WatchlistItem timestamp
from dotenv import load_dotenv # Import load_dotenv

# --- Configuration ---
# Load environment variables first (looks for .env in parent dir)
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(dotenv_path):
    # print(f"Loading environment variables from: {dotenv_path}") # Optional debug print
    load_dotenv(dotenv_path=dotenv_path)
# else:
    # print(f".env file not found at {dotenv_path}, relying on system environment variables.") # Optional debug print

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
        # Return only the path, prepend base URL later if needed in frontend/backend response
        return poster_path
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for tmdbId {tmdb_id}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error processing tmdbId {tmdb_id}: {e}")
        return None

# --- Main Seeding Function ---
def seed_database():
    """Reads CSV files and populates the database."""
    print("\n--- Starting Database Seeding ---")

    # Check for API Key
    if not TMDB_API_KEY or not TMDB_API_KEY.strip():
         print("ERROR: TMDB_API_KEY environment variable not found or empty.")
         print("Please ensure it is set in your environment (e.g., .env file or Render service config).")
         sys.exit(1) # Exit if key is missing

    # --- Confirmation Prompt ---
    # Skip confirmation if running non-interactively (like Render Job)
    is_interactive = sys.stdout.isatty() # Check if running in an interactive terminal
    confirm = 'y' # Default to yes for non-interactive
    if is_interactive:
        print(f"\nWARNING: This script will connect to the database specified:")
        print(f"  DB URL: {'postgresql://.../...@...' if DATABASE_URL.startswith('postgresql') else DATABASE_URL}") # Mask credentials
        print(f"  It will CREATE tables if they don't exist, but WILL NOT delete existing data.")
        print(f"  If tables exist, it tries to add data, skipping duplicates based on constraints.")
        confirm = input("Continue? (y/n): ").lower()

    if confirm != 'y':
        print("Seeding aborted.")
        return
    # --- End Confirmation ---

    # Get a database session
    db: Session = SessionLocal()

    try:
        print("\nCreating database tables if they don't exist...")
        # Use the Base.metadata from models.py via the imported db_engine
        # Ensure all models are imported somewhere before calling create_all
        Base.metadata.create_all(bind=db_engine)
        print("Tables created successfully (or already exist).")
        sys.stdout.flush() # Ensure message is printed immediately

        # --- Load Links ---
        print(f"\nLoading links from {LINKS_CSV}...")
        sys.stdout.flush()
        try:
            links_df = pd.read_csv(LINKS_CSV)
            links_df = links_df[pd.to_numeric(links_df['tmdbId'], errors='coerce').notnull()] # Drop rows with invalid tmdbId
            links_df['tmdbId'] = links_df['tmdbId'].astype(int)
            # Create a dictionary for quick lookup: {movieId: tmdbId}
            movie_to_tmdb_map = pd.Series(links_df.tmdbId.values, index=links_df.movieId).to_dict()
            print(f"Loaded {len(movie_to_tmdb_map)} movie links.")
            sys.stdout.flush()
        except FileNotFoundError:
            print(f"ERROR: links.csv not found at {LINKS_CSV}. Cannot fetch posters.")
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
        processed_movie_ids = set() # Track IDs successfully added
        start_time = time.time()
        api_call_count = 0

        # Check existing movies to potentially skip adding duplicates
        existing_movie_ids = {m.id for m in db.query(models.Movie.id).all()}
        print(f"Found {len(existing_movie_ids)} existing movies in the database.")

        for index, row in movies_df.iterrows():
            movie_id = int(row['movieId']) # Ensure movie ID is integer

            # Skip if already exists in DB
            if movie_id in existing_movie_ids:
                processed_movie_ids.add(movie_id) # Add to processed list even if skipped
                continue

            tmdb_id = movie_to_tmdb_map.get(movie_id)
            poster_url = None
            if tmdb_id:
                poster_url = get_movie_details(tmdb_id)
                api_call_count += 1
                # Optional: Add small delay even on errors to prevent hammering API
                time.sleep(0.05) # Rate limiting

            # Basic data cleaning/validation
            title = row.get('title', '').strip()
            year_str = ''.join(filter(str.isdigit, title[-5:])) # Extract year digits from title like "(1995)"
            release_year = int(year_str) if year_str.isdigit() and len(year_str) == 4 else None
            # Robustly remove year suffix like (YYYY) or (YYYY-YYYY)
            if release_year and title.endswith(f" ({release_year})"):
                 title = title[:-len(f" ({release_year})")].strip()
            elif '(' in title and ')' in title and title[-1] == ')':
                 # Attempt to remove other potential year strings if format is less predictable
                 potential_year_part = title[title.rfind('('):]
                 if len(potential_year_part) > 2 and potential_year_part[1:-1].replace('-','').isdigit():
                      title = title[:title.rfind('(')].strip()


            # Ensure essential fields are present
            if not title:
                 print(f"Skipping movie with ID {movie_id} due to missing title.")
                 continue

            movie = models.Movie(
                id=movie_id,
                title=title if title else "Unknown Title", # Ensure title is not empty
                genres=row.get('genres') if pd.notna(row.get('genres')) else "N/A", # Handle NaN genres
                description=None, # MovieLens doesn't have description
                release_year=release_year,
                poster_url=poster_url
            )
            movies_to_add.append(movie)
            processed_movie_ids.add(movie_id) # Track successfully processed movie

            # Print progress periodically
            if (index + 1) % 100 == 0 or index == len(movies_df) - 1:
                elapsed_time = time.time() - start_time
                print(f"Processed {index + 1}/{len(movies_df)} movies... ({elapsed_time:.2f} seconds elapsed, {api_call_count} API calls)")
                sys.stdout.flush()

        if movies_to_add:
            try:
                # Attempt to add movies one by one for more granular error reporting
                added_count = 0
                for movie_obj in movies_to_add:
                    try:
                        db.add(movie_obj)
                        db.flush() # Try to flush to catch errors early
                        added_count += 1
                    except sqlalchemy.exc.IntegrityError:
                        db.rollback() # Rollback the single failed add
                        print(f"Skipping duplicate movie ID: {movie_obj.id}")
                    except Exception as e_inner:
                        db.rollback()
                        print(f"Error adding movie ID {movie_obj.id}: {e_inner}. Skipping.")
                db.commit() # Commit all successfully added movies in the batch
                print(f"Successfully added {added_count} new movies.")
                sys.stdout.flush()
            except Exception as e:
                 print(f"\nERROR during final movie commit: {e}. Rolling back.")
                 db.rollback()
        else:
            print("No new movies to add.")


        # --- Load Users ---
        print(f"\nLoading ratings from {RATINGS_CSV} to find users...")
        sys.stdout.flush()
        try:
            ratings_df = pd.read_csv(RATINGS_CSV)
            # Ensure userId is treated as integer, drop invalid ones
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
        processed_user_ids = set() # Track IDs successfully added

        # Check existing users
        existing_user_ids = {u.id for u in db.query(models.User.id).all()}
        print(f"Found {len(existing_user_ids)} existing users in the database.")

        for user_id in user_ids:
             user_id_int = int(user_id) # Ensure it's an integer
             if user_id_int in existing_user_ids:
                 processed_user_ids.add(user_id_int)
                 continue

             # Create placeholder users
             try:
                 # Use the imported get_password_hash function
                 hashed_password = get_password_hash("password123") # Example password
                 user = models.User(
                     id=user_id_int,
                     username=f"user_{user_id_int}",
                     email=f"user_{user_id_int}@example.com",
                     hashed_password=hashed_password
                 )
                 users_to_add.append(user)
                 processed_user_ids.add(user_id_int)
             except Exception as e_hash:
                 print(f"Error creating user {user_id_int} (password hashing failed?): {e_hash}. Skipping.")


        if users_to_add:
             try:
                 db.add_all(users_to_add)
                 db.commit()
                 print(f"Successfully processed and added {len(users_to_add)} new users.")
                 sys.stdout.flush()
             except sqlalchemy.exc.IntegrityError as e:
                 print(f"\nWARNING: IntegrityError during user batch insert (likely duplicates): {e}. Rolling back batch.")
                 db.rollback()
                 # Update processed_user_ids by re-querying after rollback if necessary
                 existing_user_ids_after_rollback = {u.id for u in db.query(models.User.id).all()}
                 processed_user_ids = existing_user_ids_after_rollback # Reset based on actual DB state
             except Exception as e:
                 print(f"\nERROR during user batch commit: {e}. Rolling back batch.")
                 db.rollback()
                 existing_user_ids_after_rollback = {u.id for u in db.query(models.User.id).all()}
                 processed_user_ids = existing_user_ids_after_rollback
        else:
             print("No new users to add.")


        # --- Load Ratings ---
        print(f"\nAdding ratings (this may take a moment)...")
        sys.stdout.flush()
        ratings_count = 0
        added_ratings_count = 0
        batch_size = 10000
        ratings_to_add = []
        start_time = time.time()

        # Ensure processed IDs are up-to-date after potential rollbacks
        processed_user_ids.update(existing_user_ids) # Make sure all existing users are considered processed

        for index, row in ratings_df.iterrows():
            try:
                # Ensure IDs are integers, skip row if conversion fails
                user_id = int(row['userId'])
                movie_id = int(row['movieId'])
                rating_score = float(row['rating']) # Use 'rating' column
            except (ValueError, TypeError):
                print(f"Skipping rating at index {index}: Invalid data types (userId/movieId/rating).")
                continue

            # Check if user and movie exist in our processed sets
            if user_id not in processed_user_ids:
                # print(f"Skipping rating: User {user_id} not found/added earlier.")
                continue
            if movie_id not in processed_movie_ids:
                # print(f"Skipping rating: Movie {movie_id} not found/added earlier.")
                continue

            # Validate score (adjust range if needed)
            if not (0.5 <= rating_score <= 5.0):
                print(f"Skipping rating for user {user_id}, movie {movie_id}: Invalid score {rating_score}")
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
                    ratings_to_add = [] # Clear the batch
                except sqlalchemy.exc.IntegrityError:
                     db.rollback() # Rollback the failed batch
                     print(f"\nWARNING: IntegrityError during rating batch insert (index ~{batch_start_index}-{index}). Likely duplicate user/movie rating. Skipping batch.")
                     # Attempt to add one by one to salvage some? (More complex, skipping for now)
                     ratings_to_add = [] # Clear the failed batch
                except Exception as e:
                     db.rollback()
                     print(f"\nERROR during rating batch commit (index ~{batch_start_index}-{index}): {e}. Rolling back and skipping batch.")
                     ratings_to_add = [] # Clear the failed batch

        # Final check for any remaining items (should be empty if last commit worked)
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
        print(f"\nAn unexpected error occurred during seeding: {e}")
        try:
            db.rollback() # Rollback any partial changes on unexpected errors
        except: # Handle case where db might not be valid
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
    # --- ADDED: Helper for password hashing (from auth.py) ---
    # This avoids circular import if auth.py also imports models
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")
    def get_password_hash(password):
        if len(password.encode('utf-8')) > 1024:
             raise ValueError("Password is too long.")
        return pwd_context.hash(password)
    # --- END HELPER ---

    seed_database()

