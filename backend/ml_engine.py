import pandas as pd
from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from surprise import Dataset, Reader, SVD
from surprise.model_selection import train_test_split
import models # <-- Absolute import
from typing import List
import time # For potential rate limiting if needed in future API calls
import traceback # Keep traceback for error reporting

# --- Content-Based Filtering ---

def get_content_recommendations(movie_id: int, db: Session, num_recs: int = 10) -> List[int]:
    """
    Generates content-based recommendations for a given movie.
    Based on movie 'genres' and 'description'.
    """
    try:
        movies = db.query(models.Movie).all()
        if not movies:
            return []

        movie_data = []
        for movie in movies:
            text_features = f"{movie.title or ''} {movie.genres or ''} {movie.description or ''}"
            movie_data.append({
                'id': movie.id,
                'text_features': text_features.strip()
            })

        df = pd.DataFrame(movie_data)

        if movie_id not in df['id'].values:
            print(f"Content-Based: Movie ID {movie_id} not found.") # Keep essential warnings
            return []

        try:
            idx = df.index[df['id'] == movie_id].tolist()[0]
        except IndexError:
             print(f"Content-Based: Could not find index for movie_id {movie_id}.") # Keep essential warnings
             return []

        tfidf = TfidfVectorizer(stop_words='english')
        df['text_features'] = df['text_features'].fillna('')
        tfidf_matrix = tfidf.fit_transform(df['text_features'])
        cosine_sim = cosine_similarity(tfidf_matrix, tfidf_matrix)

        sim_scores = list(enumerate(cosine_sim[idx]))
        sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)
        sim_scores = sim_scores[1:num_recs+1]
        movie_indices = [i[0] for i in sim_scores]
        recommended_movie_ids = df['id'].iloc[movie_indices].tolist()

        return recommended_movie_ids

    except Exception as e:
        print(f"Content-Based: Error during recommendations: {e}")
        traceback.print_exc() # Keep full traceback for errors
        return []


# --- Collaborative Filtering ---

svd_algo = None

def train_collaborative_model(db: Session):
    """
    Trains the SVD collaborative filtering model on all ratings in the DB.
    """
    global svd_algo
    print("Training collaborative filtering model...") # Keep essential status messages
    start_time = time.time()

    ratings_query = db.query(models.Rating).all()
    if not ratings_query:
        print("Collaborative: No ratings found in DB to train model.") # Keep essential warnings
        svd_algo = None
        return

    ratings_data = {
        'user_id': [r.user_id for r in ratings_query],
        'movie_id': [r.movie_id for r in ratings_query],
        'score': [r.score for r in ratings_query]
    }
    df = pd.DataFrame(ratings_data)

    if df.empty or not all(col in df.columns for col in ['user_id', 'movie_id', 'score']):
         print("Collaborative: DataFrame is empty or missing required columns.") # Keep essential warnings
         svd_algo = None
         return

    reader = Reader(rating_scale=(0.5, 5.0))
    try:
        data = Dataset.load_from_df(df[['user_id', 'movie_id', 'score']], reader)
    except ValueError as e:
        print(f"Collaborative: Error loading data into Surprise Dataset: {e}") # Keep essential errors
        svd_algo = None
        return

    svd_algo_instance = SVD(n_factors=100, n_epochs=30, lr_all=0.005, reg_all=0.04, random_state=42)

    try:
        trainset = data.build_full_trainset()
        svd_algo_instance.fit(trainset)
        svd_algo = svd_algo_instance
        end_time = time.time()
        print(f"Model training complete. Time taken: {end_time - start_time:.2f} seconds") # Keep essential status messages
    except Exception as e:
        print(f"Collaborative: Error during model training: {e}") # Keep essential errors
        traceback.print_exc()
        svd_algo = None


def get_collaborative_recommendations(user_id: int, db: Session, num_recs: int = 10) -> List[int]:
    """
    Generates collaborative filtering recommendations for a given user.
    """
    global svd_algo

    if svd_algo is None:
        print("Collaborative: Model not trained or training failed.") # Keep essential warnings
        return []

    try:
        trainset = svd_algo.trainset
        all_movie_inner_ids = trainset.all_items()
        all_movie_raw_ids = {trainset.to_raw_iid(inner_id) for inner_id in all_movie_inner_ids}

        try:
            user_inner_id = trainset.to_inner_uid(user_id)
            rated_inner_ids = {item_inner_id for (item_inner_id, _) in trainset.ur[user_inner_id]}
            rated_raw_ids = {trainset.to_raw_iid(inner_id) for inner_id in rated_inner_ids}
        except ValueError:
            print(f"Collaborative: User {user_id} not found in trainset.") # Keep essential warnings
            return []

        movies_to_predict_raw_ids = list(all_movie_raw_ids - rated_raw_ids)

        if not movies_to_predict_raw_ids:
            print(f"Collaborative: No unrated movies found for user {user_id}.") # Keep essential warnings
            return []

        predictions = []
        for raw_movie_id in movies_to_predict_raw_ids:
            pred = svd_algo.predict(uid=user_id, iid=raw_movie_id)
            predictions.append((int(raw_movie_id), pred.est))

        predictions.sort(key=lambda x: x[1], reverse=True)
        recommended_movie_ids = [movie_id for movie_id, score in predictions[:num_recs]]

        return recommended_movie_ids

    except Exception as e:
        print(f"Collaborative: Error during recommendations: {e}") # Keep essential errors
        traceback.print_exc()
        return []

# --- Hybrid Recommendations ---

def get_hybrid_recommendations(user_id: int, db: Session, num_recs: int = 10) -> List[int]:
    """
    Generates hybrid recommendations by combining content-based and collaborative filtering.
    """
    collab_recs = get_collaborative_recommendations(user_id, db, num_recs)
    content_recs = []
    top_rating = db.query(models.Rating).filter(models.Rating.user_id == user_id).order_by(models.Rating.score.desc()).first()

    if top_rating:
        content_recs = get_content_recommendations(top_rating.movie_id, db, num_recs)

    hybrid_recs_set = set()
    hybrid_recs_list = []

    for rec_id in collab_recs:
        if rec_id not in hybrid_recs_set:
            hybrid_recs_set.add(rec_id)
            hybrid_recs_list.append(rec_id)

    for rec_id in content_recs:
        if rec_id not in hybrid_recs_set and len(hybrid_recs_list) < num_recs:
            hybrid_recs_set.add(rec_id)
            hybrid_recs_list.append(rec_id)

    final_recs = hybrid_recs_list[:num_recs]
    # Keep one final print statement for confirmation in main.py logs
    # print(f"Generated {len(final_recs)} hybrid recommendations for user {user_id}.")
    return final_recs

