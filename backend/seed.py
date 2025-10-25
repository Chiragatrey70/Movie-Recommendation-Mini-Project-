import pandas as pd
from sqlalchemy.orm import Session
from database import engine, Base, SessionLocal # Use items from database.py
from models import User, Movie, Rating # Use models from models.py
import os
import requests
import time
import sys # For flushing output

# --- Configuration ---

# ACTION REQUIRED -- Paste your TMDB API Key here.
# Get it from: https://www.themoviedb.org/settings/api
TMDB_API_KEY = "3de8877220bd5e628fd99d45595d" # <-- PASTE YOUR KEY HERE (ensure no extra spaces)

# --- ADD DEBUG LINE ---
print(f"DEBUG: Read TMDB_API_KEY as: '{TMDB_API_KEY}'") # <-- Add this print statement
# --- END ADDITION ---


TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500" # Base URL for poster images

# --- Define file paths (Looking in the ROOT folder) ---
# Get the parent directory (root movie-recommender folder)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Go two levels up if seed.py is in backend/

# Define paths relative to the ROOT directory
DB_FILE = os.path.join(ROOT_DIR, "movies.db") # Database in the root
RATINGS_CSV = os.path.join(ROOT_DIR, "backend", "ratings.csv") # CSVs are still in backend/
MOVIES_CSV = os.path.join(ROOT_DIR, "backend", "movies.csv")
LINKS_CSV = os.path.join(ROOT_DIR, "backend", "links.csv")

# --- Helper Function to Get Movie Details from TMDB ---
def get_movie_details(tmdb_id, api_key):
    """Fetches movie details (including poster path) from TMDB API."""
    if pd.isna(tmdb_id):
        return None, None # Return None for both if tmdb_id is missing

    # Ensure tmdb_id is a valid integer before making the API call
    try:
        tmdb_id_int = int(tmdb_id)
    except (ValueError, TypeError):
        print(f"Warning: Invalid tmdbId '{tmdb_id}'. Skipping.")
        return None, None

    url = f"{TMDB_BASE_URL}/movie/{tmdb_id_int}?api_key={api_key}"
    try:
        response = requests.get(url)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        data = response.json()
        poster_path = data.get('poster_path')
        description = data.get('overview', '') # Get description (overview)
        return poster_path, description
    except requests.exceptions.HTTPError as e:
         # Specifically handle 404 Not Found without printing a scary error
         if e.response.status_code == 404:
             print(f"Info: Movie with tmdbId {tmdb_id_int} not found on TMDB. Skipping poster/description.")
             return None, None
         else:
            print(f"HTTP Error fetching data for tmdbId {tmdb_id_int}: {e}")
            return None, None # Return None on other HTTP errors
    except requests.exceptions.RequestException as e:
        print(f"Network Error fetching data for tmdbId {tmdb_id_int}: {e}")
        return None, None # Return None on network errors
    except Exception as e:
        print(f"An unexpected error occurred for tmdbId {tmdb_id_int}: {e}")
        return None, None


# --- Seeding Function ---
def seed_database():
    """Reads CSVs and populates the database."""

    # Check for API Key (using .strip() for robustness)
    if not TMDB_API_KEY or not TMDB_API_KEY.strip(): # <-- ADDED .strip()
        print("\nERROR: Please paste your TMDB API key into the \"TMDB_API_KEY\" variable in seed.py\n")
        return # Stop execution if key is missing or only whitespace

    # Check if DB file exists and ask for confirmation
    if os.path.exists(DB_FILE):
        print(f"WARNING: Database file '{DB_FILE}' already exists.")
        confirm = input("This will delete all existing data. Continue? (y/n): ")
        if confirm.lower() != 'y':
            print("Seeding aborted.")
            exit()
        else:
            print("Deleting existing database...")
            try:
                os.remove(DB_FILE)
            except OSError as e:
                print(f"Error removing database file: {e}. Please close any programs using it and try again.")
                exit()


    print("Creating database tables...")
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Error creating database tables: {e}")
        exit()

    db: Session = SessionLocal()

    try:
        # --- Load Links First ---
        print(f"Loading links from {LINKS_CSV}")
        try:
            links_df = pd.read_csv(LINKS_CSV)
            # Ensure tmdbId is treated numerically, errors coerced to NaN
            links_df['tmdbId'] = pd.to_numeric(links_df['tmdbId'], errors='coerce')
        except FileNotFoundError:
            print(f"ERROR: Links file not found at {LINKS_CSV}")
            return
        except Exception as e:
            print(f"Error reading links file: {e}")
            return

        # --- Load Movies ---
        print(f"Loading movies from {MOVIES_CSV}")
        try:
            movies_df = pd.read_csv(MOVIES_CSV)
        except FileNotFoundError:
            print(f"ERROR: Movies file not found at {MOVIES_CSV}")
            return
        except Exception as e:
            print(f"Error reading movies file: {e}")
            return

        # Merge movies with links to get tmdbId
        movies_df = pd.merge(movies_df, links_df[['movieId', 'tmdbId']], on='movieId', how='left')

        movie_count = 0
        movies_to_add = []
        total_movies = len(movies_df)

        print(f"Fetching details for {total_movies} movies from TMDB (this will take several minutes)...")
        for index, row in movies_df.iterrows():
            # Extract year from title, handle potential errors
            title_year = str(row.get('title', '')).strip() # Ensure title is a string
            release_year = None
            title = title_year
            if title_year.endswith(')') and '(' in title_year:
                year_part = title_year[title_year.rfind('(')+1:-1]
                if year_part.isdigit() and len(year_part) == 4 :
                    try:
                        release_year = int(year_part)
                        # Find the last opening parenthesis for the year part to remove it
                        title = title_year[:title_year.rfind('(')].strip()
                    except ValueError:
                        # Keep original title if year parsing fails
                        pass # title remains title_year

            # Fetch poster path and description from TMDB
            tmdb_id = row.get('tmdbId') # Use .get() for safety
            poster_path, description = get_movie_details(tmdb_id, TMDB_API_KEY)

            # --- Data Validation before creating Movie object ---
            try:
                movie_id = int(row['movieId'])
                movie_genres = str(row.get('genres', '')) # Ensure genres is string

                movie = Movie(
                    id=movie_id,
                    title=title,
                    description=description,
                    release_year=release_year,
                    genres=movie_genres,
                    poster_url=poster_path
                )
                movies_to_add.append(movie)
                movie_count += 1
            except (ValueError, TypeError) as ve:
                print(f"\nWarning: Skipping movie at index {index} due to invalid data (movieId/genres): {ve}. Row: {row.to_dict()}")
                continue # Skip this movie


            # Print progress every 100 movies
            if (index + 1) % 100 == 0 or (index + 1) == total_movies:
                # Use sys.stdout.write and \r to overwrite the line
                sys.stdout.write(f"\rProcessed {index + 1}/{total_movies} movies...")
                sys.stdout.flush() # Ensure it's displayed immediately

            # Add API rate limiting delay
            time.sleep(0.05) # ~20 requests per second max

        print("\nCommitting movies to database...") # Newline after progress indicator
        if movies_to_add:
            db.add_all(movies_to_add)
            db.commit()
        print(f"Successfully processed and added {movie_count} movies.")


        # --- Load Ratings (and create Users) ---
        print(f"Loading ratings from {RATINGS_CSV}")
        try:
            ratings_df = pd.read_csv(RATINGS_CSV)
            # Validate essential columns exist
            if not {'userId', 'movieId', 'rating'}.issubset(ratings_df.columns):
                 raise ValueError("Ratings CSV must contain 'userId', 'movieId', and 'rating' columns.")
        except FileNotFoundError:
            print(f"ERROR: Ratings file not found at {RATINGS_CSV}")
            return
        except ValueError as ve:
            print(f"ERROR: Invalid ratings file format: {ve}")
            return
        except Exception as e:
            print(f"Error reading ratings file: {e}")
            return


        # Get unique user IDs from the ratings file
        user_ids = ratings_df['userId'].unique()
        user_count = 0
        print(f"Creating {len(user_ids)} users...")
        users_to_add = []
        valid_user_ids = set()
        for user_id_raw in user_ids:
            try:
                user_id = int(user_id_raw)
                 # Create dummy users based on ratings data
                user = User(
                    id=user_id,
                    username=f"user_{user_id}",
                    email=f"user_{user_id}@movierec.com",
                    hashed_password="dummy_password" # Not used for seeding, real app needs proper hashing
                )
                users_to_add.append(user)
                valid_user_ids.add(user_id) # Keep track of users successfully created
                user_count += 1
            except (ValueError, TypeError):
                 print(f"\nWarning: Skipping user creation for invalid userId '{user_id_raw}' found in ratings.")
                 continue # Skip invalid user ID

        if users_to_add:
            db.add_all(users_to_add)
            db.commit() # Commit users first
        print(f"Successfully processed and added {user_count} users.")


        print("Adding ratings (this may take a moment)...")
        ratings_to_add = []
        batch_size = 10000 # Commit ratings in batches
        total_ratings_added = 0
        skipped_ratings = 0

        # --- Efficiently check movie existence ---
        print("Fetching existing movie IDs from database...")
        existing_movie_ids = {m.id for m in db.query(Movie.id).all()}
        print(f"Found {len(existing_movie_ids)} movies in database.")

        print("Processing and adding ratings...")
        for index, row in ratings_df.iterrows():
            try:
                user_id = int(row['userId'])
                movie_id = int(row['movieId'])
                score = float(row['rating'])

                # --- Data Validation ---
                # Check if user was successfully created
                if user_id not in valid_user_ids:
                    skipped_ratings += 1
                    continue # Skip rating if user ID was invalid

                # Check if movie exists in our database
                if movie_id not in existing_movie_ids:
                    skipped_ratings += 1
                    # print(f"\nWarning: Skipping rating for non-existent movie ID {movie_id} at index {index}.")
                    continue # Skip rating if movie ID doesn't exist

                if not (0.5 <= score <= 5.0):
                     raise ValueError("Rating score must be between 0.5 and 5.0")
                # --- End Validation ---

                rating = Rating(
                    user_id=user_id,
                    movie_id=movie_id,
                    score=score
                )
                ratings_to_add.append(rating)
                total_ratings_added += 1

                # Commit in batches
                if len(ratings_to_add) >= batch_size:
                    db.add_all(ratings_to_add)
                    db.commit()
                    # Progress indication
                    current_total = total_ratings_added + skipped_ratings
                    sys.stdout.write(f"\rProcessed {current_total}/{len(ratings_df)} ratings (Added: {total_ratings_added}, Skipped: {skipped_ratings})...")
                    sys.stdout.flush()
                    ratings_to_add = [] # Clear the batch

            except (ValueError, TypeError) as ve:
                print(f"\nWarning: Skipping rating at index {index} due to invalid data: {ve}. Row: {row.to_dict()}")
                skipped_ratings += 1
                continue # Skip this rating

        # Commit any remaining ratings
        if ratings_to_add:
            db.add_all(ratings_to_add)
            db.commit()

        # Final progress update
        current_total = total_ratings_added + skipped_ratings
        sys.stdout.write(f"\rProcessed {current_total}/{len(ratings_df)} ratings (Added: {total_ratings_added}, Skipped: {skipped_ratings})...\n")
        sys.stdout.flush()

        print(f"\nSuccessfully processed {len(ratings_df)} rating entries.")
        print(f"Added {total_ratings_added} valid ratings.")
        if skipped_ratings > 0:
            print(f"Skipped {skipped_ratings} ratings due to invalid user/movie IDs or data errors.")


    except Exception as e:
        db.rollback() # Rollback changes if any error occurs
        print(f"\nAn error occurred during seeding: {e}")
        import traceback
        traceback.print_exc() # Print detailed traceback
    finally:
        db.close()
        print("Database session closed.")

# --- Main Execution ---
if __name__ == "__main__":
    seed_database()
    print("\nDatabase seeding complete!")

