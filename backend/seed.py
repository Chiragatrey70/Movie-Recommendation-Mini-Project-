import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import exc
import models  # Import our models
import database  # Import our database setup
import os

# --- THIS IS THE NEW FIX ---
# Get the absolute path to the 'backend' directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Get the absolute path to the parent (root) directory
ROOT_DIR = os.path.dirname(BASE_DIR)

# Define file paths relative to the 'backend' folder
MOVIES_CSV = os.path.join(BASE_DIR, 'movies.csv')
RATINGS_CSV = os.path.join(BASE_DIR, 'ratings.csv')
# Define the database path in the ROOT folder
DATABASE_FILE = os.path.join(ROOT_DIR, 'movies.db')
# --- END OF FIX ---

# Get the database engine and session maker
engine = database.engine
SessionLocal = database.SessionLocal

# ... (rest of the file is identical) ...

def clean_title(title):
    """
    Cleans the movie title, extracts year if present.
    Example: "Toy Story (1995)" -> title="Toy Story", year=1995
    Example: "Grumpier Old Men (1995)" -> title="Grumpier Old Men", year=1995
    Example: "Heat (1995)" -> title="Heat", year=1995
    """
    import re
    year_match = re.search(r'\((\d{4})\)$', title)
    year = None
    if year_match:
        year = int(year_match.group(1))
        # Remove the year part from the title string
        title = title[:year_match.start()].strip()
    return title, year

def seed_database():
    """
    Loads data from MovieLens CSVs into the SQLite database.
    """
    
    # Drop and recreate all tables
    print("Dropping all existing tables...")
    models.Base.metadata.drop_all(bind=engine)
    print("Creating new database tables...")
    models.Base.metadata.create_all(bind=engine)

    db: Session = SessionLocal()
    
    try:
        # --- Load Movies ---
        print(f"Loading movies from {MOVIES_CSV}...")
        movies_df = pd.read_csv(MOVIES_CSV)
        movie_count = 0
        for _, row in movies_df.iterrows():
            title, year = clean_title(row['title'])
            
            # Handle the (no genres listed) case
            genres = row['genres'] if row['genres'] != '(no genres listed)' else None
            
            movie = models.Movie(
                id=int(row['movieId']),
                title=title,
                release_year=year,
                genres=genres
                # Description will be null as it's not in the CSV
            )
            db.add(movie)
            movie_count += 1
        
        # Commit all movies at once
        db.commit()
        print(f"Successfully processed and added {movie_count} movies.")
        
        # --- Load Ratings (and Users) ---
        print(f"Loading ratings from {RATINGS_CSV}...")
        ratings_df = pd.read_csv(RATINGS_CSV)
        
        # Get all unique user IDs from the ratings file
        user_ids = ratings_df['userId'].unique()
        user_count = 0
        # Create user objects for all users
        for user_id in user_ids:
            user = models.User(
                id=int(user_id)
                # username, email, password will be null
            )
            db.add(user)
            user_count += 1
            
        # Commit all users at once
        db.commit()
        print(f"Successfully added {user_count} users.")
        
        # Now add all ratings
        rating_count = 0
        for _, row in ratings_df.iterrows():
            rating = models.Rating(
                user_id=int(row['userId']),
                movie_id=int(row['movieId']),
                score=float(row['rating'])
                # timestamp is ignored
            )
            db.add(rating)
            rating_count += 1
            
            # Commit in batches of 10,000 for performance
            if rating_count % 10000 == 0:
                db.commit()
                print(f"Committed {rating_count} ratings...")
        
        # Commit any remaining ratings
        db.commit()
        print(f"Successfully processed and added {rating_count} ratings.")
        
        print("\n--- Database seeding complete! ---")
        
    except FileNotFoundError as e:
        db.rollback()
        print(f"\n--- ERROR ---")
        print(f"Could not find file: {e.filename}")
        print("Please make sure 'movies.csv' and 'ratings.csv' are in the 'backend' folder.")
    except exc.IntegrityError as e:
        db.rollback()
        print(f"\n--- ERROR ---")
        print(f"An integrity error occurred (e.g., duplicate key): {e}")
    except Exception as e:
        db.rollback()
        print(f"\n--- ERROR ---")
        print(f"An unexpected error occurred: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    # Check if DB file exists and ask for confirmation
    if os.path.exists(DATABASE_FILE):
        print(f"WARNING: Database file '{DATABASE_FILE}' already exists.")
        confirm = input("This will DELETE all existing data. Continue? (y/n): ")
        if confirm.lower() != 'y':
            print("Seeding aborted.")
            exit()
    
    seed_database()

