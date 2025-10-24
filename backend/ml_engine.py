import pandas as pd
from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from surprise import Dataset, Reader, SVD
from surprise.model_selection import train_test_split
import models # <-- CHANGED THIS LINE
from typing import List

# --- Content-Based Filtering ---

def get_content_recommendations(movie_id: int, db: Session, num_recs: int = 10) -> List[int]:
    """
    Generates content-based recommendations for a given movie.
    Based on movie 'genres' and 'description'.
    """
    try:
        movies = db.query(models.Movie).all() # Use models.Movie
        if not movies:
            return []
        
        movie_data = []
        for movie in movies:
            movie_data.append({
                'id': movie.id,
                'text_features': f"{movie.title} {movie.genres} {movie.description}"
            })
        
        df = pd.DataFrame(movie_data)
        
        if movie_id not in df['id'].values:
            print(f"Movie ID {movie_id} not found in database for content filtering.")
            return []

        tfidf = TfidfVectorizer(stop_words='english')
        tfidf_matrix = tfidf.fit_transform(df['text_features'])
        cosine_sim = cosine_similarity(tfidf_matrix, tfidf_matrix)
        idx = df.index[df['id'] == movie_id].tolist()[0]
        sim_scores = list(enumerate(cosine_sim[idx]))
        sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)
        sim_scores = sim_scores[1:num_recs+1]
        movie_indices = [i[0] for i in sim_scores]
        recommended_movie_ids = df['id'].iloc[movie_indices].tolist()

        return recommended_movie_ids

    except Exception as e:
        print(f"Error in content-based recommendations: {e}")
        return []

# --- Collaborative Filtering ---

svd_algo = None

def train_collaborative_model(db: Session):
    """
    Trains the SVD collaborative filtering model on all ratings in the DB.
    """
    global svd_algo
    print("Training collaborative filtering model...")
    
    ratings_query = db.query(models.Rating).all() # Use models.Rating
    if not ratings_query:
        print("No ratings found in DB to train model.")
        svd_algo = None
        return

    ratings_data = {
        'user_id': [r.user_id for r in ratings_query],
        'movie_id': [r.movie_id for r in ratings_query],
        'score': [r.score for r in ratings_query]
    }
    df = pd.DataFrame(ratings_data)
    reader = Reader(rating_scale=(0.5, 5.0))
    data = Dataset.load_from_df(df[['user_id', 'movie_id', 'score']], reader)
    svd_algo = SVD(n_factors=50, n_epochs=20, lr_all=0.005, reg_all=0.02)
    trainset = data.build_full_trainset()
    svd_algo.fit(trainset)
    print("Model training complete.")


def get_collaborative_recommendations(user_id: int, db: Session, num_recs: int = 10) -> List[int]:
    """
    Generates collaborative filtering recommendations for a given user.
    """
    global svd_algo
    if svd_algo is None:
        print("Collaborative model is not trained. Training now...")
        train_collaborative_model(db)
        if svd_algo is None:
            print("Model training failed, cannot provide collaborative recommendations.")
            return []

    try:
        all_movies = db.query(models.Movie.id).all() # Use models.Movie
        all_movie_ids = {movie.id for movie in all_movies}

        rated_movies = db.query(models.Rating.movie_id).filter(models.Rating.user_id == user_id).all() # Use models.Rating
        rated_movie_ids = {rating.movie_id for rating in rated_movies}

        movies_to_predict = list(all_movie_ids - rated_movie_ids)
        
        if not movies_to_predict:
            print("User has rated all movies, or no movies to predict.")
            return []

        predictions = []
        for movie_id in movies_to_predict:
            pred = svd_algo.predict(uid=str(user_id), iid=str(movie_id))
            predictions.append((movie_id, pred.est))

        predictions.sort(key=lambda x: x[1], reverse=True)
        recommended_movie_ids = [movie_id for movie_id, score in predictions[:num_recs]]
        
        return recommended_movie_ids

    except Exception as e:
        print(f"Error in collaborative recommendations: {e}")
        return []

# --- Hybrid Recommendations ---

def get_hybrid_recommendations(user_id: int, db: Session, num_recs: int = 10) -> List[int]:
    """
    Generates hybrid recommendations by combining content-based and collaborative filtering.
    """
    collab_recs = get_collaborative_recommendations(user_id, db, num_recs)
    content_recs = []
    
    top_rating = db.query(models.Rating).filter(models.Rating.user_id == user_id).order_by(models.Rating.score.desc()).first() # Use models.Rating
    
    if top_rating:
        print(f"Getting content recs based on user's top movie (ID: {top_rating.movie_id})")
        content_recs = get_content_recommendations(top_rating.movie_id, db, num_recs)
    
    hybrid_recs = []
    
    for rec_id in collab_recs:
        if rec_id not in hybrid_recs:
            hybrid_recs.append(rec_id)
    
    for rec_id in content_recs:
        if rec_id not in hybrid_recs and len(hybrid_recs) < num_recs:
            hybrid_recs.append(rec_id)

    if len(hybrid_recs) < num_recs:
        all_recs = collab_recs + content_recs
        for rec_id in all_recs:
             if rec_id not in hybrid_recs and len(hybrid_recs) < num_recs:
                hybrid_recs.append(rec_id)

    print(f"Generated {len(hybrid_recs)} hybrid recommendations.")
    return hybrid_recs[:num_recs]

