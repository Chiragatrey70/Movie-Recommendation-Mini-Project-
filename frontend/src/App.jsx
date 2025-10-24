import { useState, useEffect } from 'react';
import axios from 'axios';

// --- Constants ---
const API_URL = "http://127.0.0.1:8000";
const USER_ID = 1; // We'll hardcode user 1 for now

// --- Main App Component ---
export default function App() {
  const [recommendations, setRecommendations] = useState([]);
  const [userRatings, setUserRatings] = useState({}); // Stores ratings as { movie_id: score }
  const [selectedMovie, setSelectedMovie] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  // --- Data Fetching Hooks ---

  // Fetch initial data (recommendations and user ratings) on page load
  useEffect(() => {
    const fetchInitialData = async () => {
      try {
        setIsLoading(true);
        setErrorMessage("");
        
        // Fetch recommendations
        const recsResponse = await axios.get(`${API_URL}/recommendations/${USER_ID}`);
        setRecommendations(recsResponse.data);
        
        // Fetch user's past ratings
        const ratingsResponse = await axios.get(`${API_URL}/users/${USER_ID}/ratings`);
        // Convert array of {movie_id, score} to a fast-lookup map {movie_id: score}
        const ratingsMap = ratingsResponse.data.reduce((acc, rating) => {
          acc[rating.movie_id] = rating.score;
          return acc;
        }, {});
        setUserRatings(ratingsMap);

      } catch (err) {
        console.error("Error fetching initial data:", err);
        setErrorMessage("Could not fetch data. Is the backend server running?");
      } finally {
        setIsLoading(false);
      }
    };
    
    fetchInitialData();
  }, []);

  // Fetch search results when searchQuery changes
  useEffect(() => {
    if (searchQuery.trim() === "") {
      setSearchResults([]);
      return;
    }

    const fetchSearch = async () => {
      try {
        setErrorMessage("");
        const response = await axios.get(`${API_URL}/movies/`, {
          params: { search: searchQuery, limit: 10 }
        });
        setSearchResults(response.data);
      } catch (err) {
        console.error("Error searching movies:", err);
        setErrorMessage("Could not fetch search results.");
      }
    };

    // Debounce search
    const delayDebounceFn = setTimeout(() => {
      fetchSearch();
    }, 300);

    return () => clearTimeout(delayDebounceFn);
  }, [searchQuery]);

  // --- API Functions ---

  const handleRating = async (rating) => {
    setErrorMessage(""); // Clear old errors
    if (!selectedMovie) return;

    const newRating = {
      movie_id: selectedMovie.id,
      user_id: USER_ID,
      score: rating,
    };

    try {
      const response = await axios.post(`${API_URL}/ratings/`, newRating);
      console.log("Rating submitted:", response.data);
      
      // --- Update local state immediately ---
      setUserRatings(prevRatings => ({
        ...prevRatings,
        [selectedMovie.id]: rating,
      }));
      
      // Close modal and refresh recommendations after rating
      setSelectedMovie(null);
      
      // Give the background task a moment to start, then refetch
      setTimeout(() => {
        fetchRecommendations(); 
      }, 1000); // 1 second delay

    } catch (err) {
      console.error("Error submitting rating:", err);
      setErrorMessage("Could not submit rating.");
    }
  };
  
  const fetchRecommendations = async () => {
    try {
      // Don't set loading for a refresh
      setErrorMessage("");
      const response = await axios.get(`${API_URL}/recommendations/${USER_ID}`);
      setRecommendations(response.data);
    } catch (err) {
      console.error("Error fetching recommendations:", err);
      setErrorMessage("Could not fetch recommendations.");
    }
  };

  // --- Render Logic ---

  const moviesToShow = searchQuery.trim() ? searchResults : recommendations;
  const title = searchQuery.trim() ? "Search Results" : "Recommended For You";

  return (
    <div className="min-h-screen bg-gray-900 text-white font-sans">
      <Header searchQuery={searchQuery} setSearchQuery={setSearchQuery} />

      <main className="container mx-auto px-4 py-8">
        {errorMessage && <ErrorMessage message={errorMessage} />}
        
        <h2 className="text-3xl font-bold mb-6 flex items-center">
          <StarIcon /> {title}
        </h2>

        {isLoading ? (
          <LoadingSpinner />
        ) : (
          <MovieList movies={moviesToShow} onMovieSelect={setSelectedMovie} />
        )}
      </main>

      {selectedMovie && (
        <MovieModal
          movie={selectedMovie}
          onClose={() => setSelectedMovie(null)}
          onRate={handleRating}
          // Pass the existing rating into the modal
          existingRating={userRatings[selectedMovie.id] || 0}
        />
      )}
    </div>
  );
}

// --- Sub-Components ---

function Header({ searchQuery, setSearchQuery }) {
  return (
    <header className="bg-gray-800 shadow-lg sticky top-0 z-50">
      <nav className="container mx-auto px-4 py-4 flex justify-between items-center">
        <div className="text-2xl font-bold text-yellow-400 flex items-center">
          <LogoIcon />
          MovieRec
        </div>
        <div className="w-full max-w-xs">
          <div className="relative">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search for movies..."
              className="w-full bg-gray-700 text-white px-4 py-2 rounded-full focus:outline-none focus:ring-2 focus:ring-yellow-400"
            />
            <SearchIcon />
          </div>
        </div>
      </nav>
    </header>
  );
}

function MovieList({ movies, onMovieSelect }) {
  if (movies.length === 0) {
    return <p className="text-gray-400">No movies found.</p>;
  }
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-6">
      {movies.map(movie => (
        <MovieCard key={movie.id} movie={movie} onMovieSelect={onMovieSelect} />
      ))}
    </div>
  );
}

function MovieCard({ movie, onMovieSelect }) {
  // Extract just the first genre if it exists
  const mainGenre = movie.genres ? movie.genres.split('|')[0] : 'Movie';

  return (
    <div
      onClick={() => onMovieSelect(movie)}
      className="bg-gray-800 rounded-lg shadow-lg overflow-hidden cursor-pointer transform transition-transform duration-300 hover:scale-105 hover:shadow-yellow-400/20"
    >
      <div className="h-64 bg-gray-700 flex items-center justify-center overflow-hidden p-4">
        {/* Simple text fallback for movie 'poster' */}
        <span className="text-xl font-bold text-center px-2 text-yellow-400">{movie.title}</span>
      </div>
      <div className="p-4">
        <h3 className="font-bold text-lg truncate" title={movie.title}>{movie.title}</h3>
        <p className="text-gray-400 text-sm">{movie.release_year ? `${mainGenre} • ${movie.release_year}` : mainGenre}</p>
      </div>
    </div>
  );
}

function MovieModal({ movie, onClose, onRate, existingRating }) {
  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-lg shadow-2xl w-full max-w-lg relative"
           onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-3 right-3 text-gray-400 hover:text-white text-2xl"
        >
          &times;
        </button>
        
        <div className="p-8">
          <h2 className="text-3xl font-bold mb-2 text-yellow-400">{movie.title} ({movie.release_year})</h2>
          <p className="text-gray-400 mb-4">{movie.genres ? movie.genres.split('|').join(', ') : ''}</p>
          <p className="text-gray-300 mb-6">{movie.description || "No description available."}</p>
          
          <div className="bg-gray-700 p-4 rounded-lg">
            <h3 className="text-xl font-semibold mb-3">
              {existingRating > 0 ? "Update your rating" : "Rate this movie"}
            </h3>
            {/* Pass the existing rating to the StarRating component */}
            <StarRating initialRating={existingRating} onSetRating={onRate} />
          </div>
        </div>
      </div>
      {/* Click outside to close */}
      <div className="absolute inset-0 z-[-1]" onClick={onClose}></div>
    </div>
  );
}

function StarRating({ initialRating = 0, onSetRating }) {
  // Set the initial state to the user's existing rating
  const [rating, setRating] = useState(initialRating);
  const [hoverRating, setHoverRating] = useState(0);

  const handleRate = (rate) => {
    setRating(rate);
    onSetRating(rate);
  };
  
  // This ensures the stars are filled in when the modal opens
  useEffect(() => {
    setRating(initialRating);
  }, [initialRating]);

  return (
    <div className="flex items-center space-x-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          className="bg-transparent border-none"
          onClick={() => handleRate(star)}
          onMouseEnter={() => setHoverRating(star)}
          onMouseLeave={() => setHoverRating(0)}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className={`w-10 h-10 transition-colors
              ${(hoverRating || rating) >= star ? 'text-yellow-400' : 'text-gray-600'}
            `}
          >
            <path
              fillRule="evenodd"
              d="M10.788 3.21c.448-1.077 1.976-1.077 2.424 0l2.082 5.007 5.404.433c1.164.093 1.636 1.545.749 2.305l-4.116 3.99.94 5.577c.22 1.303-.959 2.387-2.18 1.758L12 17.314l-4.899 2.99c-1.22.63-2.4-.455-2.18-1.758l.94-5.577-4.116-3.99c-.887-.76-.415-2.212.749-2.305l5.404-.433 2.082-5.007z"
              clipRule="evenodd"
            />
          </svg>
        </button>
      ))}
    </div>
  );
}

// --- Utility Components ---

function LoadingSpinner() {
  return (
    <div className="flex justify-center items-center h-64">
      <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-yellow-400"></div>
    </div>
  );
}

function ErrorMessage({ message }) {
  return (
    <div className="bg-red-800 border border-red-700 text-red-100 px-4 py-3 rounded-lg relative mb-6" role="alert">
      <strong className="font-bold">Error: </strong>
      <span className="block sm:inline">{message}</span>
    </div>
  );
}

// --- SVG Icons ---

function LogoIcon() {
  return (
    <svg className="w-8 h-8 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400">
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
    </span>
  );
}

function StarIcon() {
  return (
    <svg className="w-7 h-7 mr-3 text-yellow-400" fill="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path fillRule="evenodd" d="M10.788 3.21c.448-1.077 1.976-1.077 2.424 0l2.082 5.007 5.404.433c1.164.093 1.636 1.545.749 2.305l-4.116 3.99.94 5.577c.22 1.303-.959 2.387-2.18 1.758L12 17.314l-4.899 2.99c-1.22.63-2.4-.455-2.18-1.758l.94-5.577-4.116-3.99c-.887-.76-.415-2.212.749-2.305l5.404-.433 2.082-5.007z" clipRule="evenodd" />
    </svg>
  );
}

