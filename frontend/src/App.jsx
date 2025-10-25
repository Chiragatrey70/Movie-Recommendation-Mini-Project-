import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

// --- Constants ---
const API_URL = "http://127.0.0.1:8000"; // Your backend URL

// --- API Client Setup ---
// Create an axios instance
const apiClient = axios.create({
  baseURL: API_URL,
});

// Add a request interceptor to include the auth token
// Ensure this runs *before* any requests are made after login/refresh
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('accessToken');
//  console.log("Interceptor: Token found:", !!token); // DEBUG
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
//    console.log("Interceptor: Added Auth header:", config.headers.Authorization); // DEBUG
  } else {
//    console.log("Interceptor: No token found, removing Auth header."); // DEBUG
    delete config.headers.Authorization; // Ensure header is removed if no token
  }
  return config;
}, (error) => {
//  console.error("Interceptor Error:", error); // DEBUG
  return Promise.reject(error);
});


// --- Main App Component ---
export default function App() {
  // Authentication State
  const [token, setToken] = useState(() => localStorage.getItem('accessToken')); // Initialize from localStorage
  const [user, setUser] = useState(null); // Stores {id, username, email}
  const [page, setPage] = useState(token ? 'app' : 'login'); // 'login', 'register', 'app'

  // App Data State
  const [recommendations, setRecommendations] = useState([]);
  const [userRatings, setUserRatings] = useState({}); // Stores ratings as { movie_id: score }
  const [watchlist, setWatchlist] = useState([]); // Stores full watchlist items {id, user_id, movie_id, added_at, movie: {...}}
  const [watchlistIds, setWatchlistIds] = useState(new Set()); // Stores just movie IDs for quick lookup

  // UI State
  const [selectedMovie, setSelectedMovie] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [selectedGenre, setSelectedGenre] = useState(null); // Added for genre filtering
  const [genreResults, setGenreResults] = useState([]); // Added for genre results
  const [isLoading, setIsLoading] = useState(false); // Combined loading state
  const [message, setMessage] = useState({ type: '', text: '' }); // { type: 'success'/'error', text: '...' }

  // --- Utility Functions ---
  const showMessage = (type, text) => {
    setMessage({ type, text });
    // Clear message after 5 seconds
    setTimeout(() => setMessage({ type: '', text: '' }), 5000);
  };

  // --- Data Fetching Hooks ---

  // Fetch Initial Data (recommendations, user ratings, watchlist) on page load/login
  const fetchInitialData = useCallback(async () => {
    // This function now *assumes* the token is valid and set by the interceptor
    if (!localStorage.getItem('accessToken')) { // Double check if token exists before fetching
        console.log("fetchInitialData: No token found, skipping fetch.");
        handleLogout(); // Ensure logged out state if no token
        return;
    }
    console.log("fetchInitialData: Token found, attempting to fetch data..."); // DEBUG
    setIsLoading(true);
    setMessage({ type: '', text: '' }); // Clear previous messages
    try {
      // Use Promise.all to fetch in parallel
      const [recsResponse, ratingsResponse, watchlistResponse, userResponse] = await Promise.all([
        apiClient.get('/recommendations/'),
        apiClient.get('/users/me/ratings'),
        apiClient.get('/users/me/watchlist'),
        apiClient.get('/users/me/') // Fetch user details
      ]);

      console.log("fetchInitialData: Data fetched successfully."); // DEBUG
      setRecommendations(recsResponse.data || []);

      // Process ratings into a map
      const ratingsMap = (ratingsResponse.data || []).reduce((acc, rating) => {
        acc[rating.movie_id] = rating.score;
        return acc;
      }, {});
      setUserRatings(ratingsMap);

      // Process watchlist
      setWatchlist(watchlistResponse.data || []);
      const wlIds = new Set((watchlistResponse.data || []).map(item => item.movie.id)); // Use movie.id from watchlist item
      setWatchlistIds(wlIds);

      // Set user details
      setUser(userResponse.data);

      setPage('app'); // Ensure user sees the app page

    } catch (error) {
      console.error("Error fetching initial data:", error);
      showMessage('error', 'Could not load movie data. Please try again.');
       if (error.response && error.response.status === 401) {
         console.log("fetchInitialData: Received 401, logging out."); // DEBUG
         showMessage('error', 'Session expired. Please log in again.');
         handleLogout(); // Log out if token is invalid
       }
    } finally {
      setIsLoading(false);
    }
  }, []); // Removed token dependency - effect below handles token changes


  // Effect to run fetchInitialData when the component mounts *if* a token exists,
  // or clear state and go to login if no token exists.
  useEffect(() => {
    const currentToken = localStorage.getItem('accessToken');
    if (currentToken) {
        setToken(currentToken); // Ensure token state is sync'd
        setPage('app');
        fetchInitialData();
    } else {
        // Clear data on initial load if no token
        setUser(null);
        setRecommendations([]);
        setUserRatings({});
        setWatchlist([]);
        setWatchlistIds(new Set());
        setToken(null);
        setPage('login');
    }
  }, [fetchInitialData]); // Run only once on mount

  // Effect to handle logout logic or page changes when token *state* changes
  useEffect(() => {
      if (!token) {
          // Clear sensitive data when token state becomes null (logout)
          setUser(null);
          setRecommendations([]);
          setUserRatings({});
          setWatchlist([]);
          setWatchlistIds(new Set());
          setPage('login'); // Navigate to login page
      }
      // Note: We don't fetch data *here* based on token state changes
      // to avoid double fetches. Initial fetch is handled by the mount effect.
  }, [token]);


  // Fetch Search Results when searchQuery changes (debounced slightly)
  useEffect(() => {
    if (searchQuery.trim() === "") {
      setSearchResults([]);
      return; // Don't search if query is empty
    }
    if (!token) return; // Don't search if not logged in

    // Debounce search API calls
    const handler = setTimeout(async () => {
      setIsLoading(true);
      // Clear genre filter when searching
      setSelectedGenre(null);
      setGenreResults([]);
      try {
        const response = await apiClient.get(`/movies/?search=${searchQuery}`);
        setSearchResults(response.data);
      } catch (error) {
        console.error("Error fetching search results:", error);
        showMessage('error', 'Could not perform search.');
        if (error.response && error.response.status === 401) handleLogout(); // Logout on 401
      } finally {
        setIsLoading(false);
      }
    }, 300); // Wait 300ms after user stops typing

    return () => clearTimeout(handler); // Cleanup timeout on unmount or query change
  }, [searchQuery, token]); // Added token dependency


  // Fetch Genre Results when selectedGenre changes
  useEffect(() => {
      if (!selectedGenre) {
          setGenreResults([]);
          return; // Don't fetch if no genre selected
      }
      if (!token) return; // Don't fetch if not logged in

      const fetchGenreMovies = async () => {
          setIsLoading(true);
          // Clear search results when filtering by genre
          setSearchQuery("");
          setSearchResults([]);
          try {
              const response = await apiClient.get(`/movies/?genre=${selectedGenre}`);
              setGenreResults(response.data);
          } catch (error) {
              console.error("Error fetching genre results:", error);
              showMessage('error', `Could not load movies for ${selectedGenre}.`);
              if (error.response && error.response.status === 401) handleLogout(); // Logout on 401
          } finally {
              setIsLoading(false);
          }
      };

      fetchGenreMovies();
  }, [selectedGenre, token]); // Added token dependency


  // --- Event Handlers ---

  const handleLogin = async (email, password) => {
    setIsLoading(true);
    setMessage({ type: '', text: '' });
    try {
      // Use form data for OAuth2
      const formData = new URLSearchParams();
      formData.append('username', email); // The API expects email in the 'username' field
      formData.append('password', password);

      const response = await apiClient.post('/token/', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });

      const newAccessToken = response.data.access_token;
      localStorage.setItem('accessToken', newAccessToken); // Store token
      setToken(newAccessToken); // Update state to trigger useEffect for data fetching
      setPage('app'); // Explicitly set page to app immediately
      // Call fetchInitialData *after* setting token and page
      fetchInitialData();


    } catch (error) {
      console.error("Login failed:", error);
      showMessage('error', error.response?.data?.detail || 'Invalid login credentials.');
      localStorage.removeItem('accessToken'); // Ensure old token is removed on failure
      setToken(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRegister = async (username, email, password) => {
    setIsLoading(true);
    setMessage({ type: '', text: '' });
    try {
      await apiClient.post('/register/', { username, email, password });
      showMessage('success', 'Registration successful! Please login.');
      setPage('login'); // Switch to login page after successful registration
    } catch (error) {
      console.error("Registration failed:", error);
      showMessage('error', error.response?.data?.detail || 'Registration failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogout = useCallback(() => { // Wrap in useCallback if passed as prop
    console.log("handleLogout called"); // DEBUG
    localStorage.removeItem('accessToken');
    setToken(null); // This will trigger the useEffect to clear state and change page
  }, []); // Empty dependency array


  const handleSearchChange = (event) => {
    setSearchQuery(event.target.value);
  };

  const handleMovieClick = (movie) => {
    setSelectedMovie(movie);
  };

  const handleCloseModal = () => {
    setSelectedMovie(null);
  };

  // Handler for rating a movie (called from modal)
  const handleRateMovie = async (movieId, score) => {
    if (!token) {
        showMessage('error', 'Please log in to rate movies.');
        return;
    }
    console.log(`Rating movie ${movieId} with score ${score}`); // DEBUG
    setMessage({ type: '', text: '' }); // Clear message
    try {
        const response = await apiClient.post('/ratings/', { movie_id: movieId, score });
        // Update local state immediately for better UX
        setUserRatings(prevRatings => ({
            ...prevRatings,
            [movieId]: score,
        }));
        showMessage('success', 'Rating submitted!');
        // Optionally close modal after rating
        // setSelectedMovie(null);

        // No need to manually trigger refetch, background task handles retraining
    } catch (error) {
        console.error("Error submitting rating:", error);
        showMessage('error', error.response?.data?.detail || 'Could not submit rating.');
        if (error.response && error.response.status === 401) handleLogout(); // Logout on 401
    }
  };

  // Handler for genre button clicks
  const handleGenreSelect = (genre) => {
      if (selectedGenre === genre) {
          setSelectedGenre(null); // Deselect if clicked again
      } else {
          setSelectedGenre(genre);
      }
  };

  // --- NEW Watchlist Handlers ---
  const handleAddToWatchlist = async (movieId) => {
    if (!movieId || !token) return;
    setMessage({ type: '', text: '' });
    try {
      const response = await apiClient.post('/watchlist/', { movie_id: movieId });
      // Add to local state immediately
      setWatchlist(prev => [...prev, response.data]); // Add full item with movie details
      setWatchlistIds(prev => new Set(prev).add(movieId));
      showMessage('success', `${response.data.movie.title} added to watchlist!`);
    } catch (error) {
      console.error("Error adding to watchlist:", error);
      showMessage('error', error.response?.data?.detail || 'Could not add to watchlist.');
      if (error.response && error.response.status === 401) handleLogout(); // Logout on 401
    }
  };

  const handleRemoveFromWatchlist = async (movieId) => {
    if (!movieId || !token) return;
    setMessage({ type: '', text: '' });
    try {
      await apiClient.delete(`/watchlist/${movieId}`);
      // Remove from local state immediately
      const movieTitle = watchlist.find(item => item.movie.id === movieId)?.movie?.title || 'Movie'; // Get title before filtering
      setWatchlist(prev => prev.filter(item => item.movie.id !== movieId));
      setWatchlistIds(prev => {
          const newSet = new Set(prev);
          newSet.delete(movieId);
          return newSet;
      });
      showMessage('success', `${movieTitle} removed from watchlist.`);
    } catch (error) {
      console.error("Error removing from watchlist:", error);
      showMessage('error', error.response?.data?.detail || 'Could not remove from watchlist.');
      if (error.response && error.response.status === 401) handleLogout(); // Logout on 401
    }
  };


  // --- Render Logic ---

  // Decide which movie list to display
  let moviesToDisplay = [];
  let listTitle = "";
  if (searchQuery && searchResults.length > 0) {
      moviesToDisplay = searchResults;
      listTitle = `Search Results for "${searchQuery}"`;
  } else if (searchQuery && !isLoading) {
      // Show message if search yields no results (and not loading)
      listTitle = `No results found for "${searchQuery}"`;
  } else if (selectedGenre) {
      moviesToDisplay = genreResults;
      listTitle = `Movies in ${selectedGenre}`;
  } else {
      moviesToDisplay = recommendations;
      listTitle = "Recommended For You";
  }


  // Render based on page state
  if (!token && page !== 'register') { // If no token, default to login unless explicitly on register
      return <Login onLogin={handleLogin} onNavigateRegister={() => setPage('register')} isLoading={isLoading} message={message} />;
  }

  if (page === 'register') {
    return <Register onRegister={handleRegister} onNavigateLogin={() => setPage('login')} isLoading={isLoading} message={message} />;
  }

  if (page === 'app' && token) { // Only render app if token exists and page is set
    // Main application view
    return (
      <div className="min-h-screen bg-gray-900 text-white font-inter">
        {/* Header */}
        <header className="bg-gray-800 shadow-md p-4 flex justify-between items-center sticky top-0 z-50">
          <h1 className="text-2xl font-bold text-yellow-400 flex items-center">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-8 h-8 mr-2">
              <path strokeLinecap="round" strokeLinejoin="round" d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9A2.25 2.25 0 0 0 13.5 5.25h-9a2.25 2.25 0 0 0-2.25 2.25v9A2.25 2.25 0 0 0 4.5 18.75Z" />
            </svg>
            MovieRec
          </h1>
          <div className="flex items-center space-x-4">
            {user && <span className="text-gray-300">Welcome, {user.username}!</span>}
             {/* Search Bar */}
             <div className="relative">
                <input
                    type="text"
                    placeholder="Search for movies..."
                    value={searchQuery}
                    onChange={handleSearchChange}
                    className="bg-gray-700 text-white rounded-full py-2 px-4 pl-10 focus:outline-none focus:ring-2 focus:ring-yellow-400"
                />
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 text-gray-400 absolute left-3 top-1/2 transform -translate-y-1/2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
                </svg>
            </div>
            <button
              onClick={handleLogout}
              className="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded-md transition duration-150 ease-in-out"
            >
              Logout
            </button>
          </div>
        </header>

         {/* Message Display */}
         {message.text && (
           <div className={`p-4 text-center ${message.type === 'error' ? 'bg-red-800 text-red-100' : 'bg-green-800 text-green-100'}`}>
             {message.text}
           </div>
         )}


        {/* Main Content */}
        <main className="p-6">
           {/* Genre Filter Buttons */}
           <div className="mb-8">
                <h2 className="text-xl font-semibold mb-4 text-gray-300 flex items-center">
                   <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-6 h-6 mr-2 text-yellow-400">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.372l2.508-2.507c.828-.5 1-1.608.373-2.607L11.16 3.66A2.25 2.25 0 0 0 9.568 3Z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 6h.008v.008H6V6Z" />
                    </svg>
                    Browse by Genre
                </h2>
                <div className="flex flex-wrap gap-2">
                    {['Action', 'Adventure', 'Animation', 'Children', 'Comedy', 'Crime', 'Documentary', 'Drama', 'Fantasy', 'Film-Noir', 'Horror', 'IMAX', 'Musical', 'Mystery', 'Romance', 'Sci-Fi', 'Thriller', 'War', 'Western'].map(genre => (
                        <button
                            key={genre}
                            onClick={() => handleGenreSelect(genre)}
                            className={`px-4 py-2 rounded-full text-sm font-medium transition duration-150 ease-in-out ${
                                selectedGenre === genre
                                ? 'bg-yellow-400 text-gray-900'
                                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                            }`}
                        >
                            {genre}
                        </button>
                    ))}
                     {selectedGenre && (
                        <button
                            onClick={() => setSelectedGenre(null)} // Clear filter button
                            className="px-4 py-2 rounded-full text-sm font-medium bg-red-600 text-red-100 hover:bg-red-700 transition duration-150 ease-in-out flex items-center"
                        >
                             <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 mr-1">
                             <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                             </svg>
                            Clear Filter
                        </button>
                    )}
                </div>
            </div>


            {/* Movie Display Area */}
           {isLoading && !selectedMovie ? ( // Show loading only if not viewing modal
                <div className="flex justify-center items-center h-64">
                    <div className="animate-spin rounded-full h-16 w-16 border-t-4 border-b-4 border-yellow-400"></div>
                </div>
            ) : (
                <>
                  {/* Title for the current list */}
                  {listTitle && (
                    <h2 className="text-2xl font-semibold mb-6 text-gray-300 flex items-center">
                        {listTitle === "Recommended For You" ? (
                             <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-6 h-6 mr-2 text-yellow-400">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M11.48 3.499a.562.562 0 0 1 1.04 0l2.125 5.111a.563.563 0 0 0 .475.31h5.518a.563.563 0 0 1 .32.875l-4.148 3.119a.562.562 0 0 0-.192.558l1.528 5.349a.562.562 0 0 1-.828.61l-4.402-3.23a.563.563 0 0 0-.64 0l-4.402 3.23a.562.562 0 0 1-.828-.61l1.528-5.349a.562.562 0 0 0-.192-.558L2.099 9.875a.563.563 0 0 1 .32-.875h5.518a.563.563 0 0 0 .475-.31L11.48 3.5Z" />
                             </svg>
                        ) : ( selectedGenre ? (
                             <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-6 h-6 mr-2 text-yellow-400">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.372l2.508-2.507c.828-.5 1-1.608.373-2.607L11.16 3.66A2.25 2.25 0 0 0 9.568 3Z" />
                                <path strokeLinecap="round" strokeLinejoin="round" d="M6 6h.008v.008H6V6Z" />
                             </svg>
                        ) : ( searchQuery ? (
                             <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-6 h-6 mr-2 text-yellow-400">
                               <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
                             </svg>
                        ) : null ))}
                        {listTitle}
                    </h2>
                  )}

                  {/* Grid for movies */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6">
                    {moviesToDisplay.length > 0 ? (
                        moviesToDisplay.map(movie => (
                           <MovieCard
                                key={movie.id}
                                movie={movie}
                                onClick={() => handleMovieClick(movie)}
                                isOnWatchlist={watchlistIds.has(movie.id)} // Pass watchlist status
                                onAddToWatchlist={() => handleAddToWatchlist(movie.id)}
                                onRemoveFromWatchlist={() => handleRemoveFromWatchlist(movie.id)}
                            />
                        ))
                    ) : (
                         !isLoading && <p className="col-span-full text-center text-gray-500">{listTitle.startsWith("No results") ? "" : "No movies to display."}</p> // Avoid double message
                    )}
                   </div>
                </>
            )}

             {/* Watchlist Section - Display only if no genre/search is active */}
             {!selectedGenre && !searchQuery && watchlist.length > 0 && (
                <div className="mt-12">
                     <h2 className="text-2xl font-semibold mb-6 text-gray-300 flex items-center">
                         <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-6 h-6 mr-2 text-yellow-400">
                           <path strokeLinecap="round" strokeLinejoin="round" d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0 1 11.186 0Z" />
                         </svg>
                        Your Watchlist
                    </h2>
                     <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6">
                        {watchlist.map(item => (
                             <MovieCard
                                key={`wl-${item.id}`} // Use watchlist item id as key here, prefix to avoid conflict
                                movie={item.movie}
                                onClick={() => handleMovieClick(item.movie)}
                                isOnWatchlist={true} // It's definitely on the watchlist
                                onAddToWatchlist={() => {}} // No action needed
                                onRemoveFromWatchlist={() => handleRemoveFromWatchlist(item.movie.id)}
                            />
                        ))}
                    </div>
                </div>
            )}
        </main>

        {/* Movie Detail Modal */}
        {selectedMovie && (
            <MovieModal
                movie={selectedMovie}
                onClose={handleCloseModal}
                onRate={handleRateMovie}
                existingRating={userRatings[selectedMovie.id] || 0} // Pass existing rating from state
                isOnWatchlist={watchlistIds.has(selectedMovie.id)} // Pass watchlist status
                onAddToWatchlist={() => handleAddToWatchlist(selectedMovie.id)}
                onRemoveFromWatchlist={() => handleRemoveFromWatchlist(selectedMovie.id)}
            />
        )}
      </div>
    );
  }

  // Fallback loading state (e.g., while initially checking token)
  return <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">Loading...</div>;
}


// --- Child Components ---

// Movie Card Component
function MovieCard({ movie, onClick, isOnWatchlist, onAddToWatchlist, onRemoveFromWatchlist }) {
   // Function to handle button click without triggering card click
   const handleButtonClick = (e, action) => {
      e.stopPropagation(); // Prevent event from bubbling up to the card's onClick
      action();
   };

  // Construct the full poster URL
  const posterBaseUrl = "https://image.tmdb.org/t/p/w500"; // Base URL for TMDB posters
  const posterUrl = movie.poster_url ? `${posterBaseUrl}${movie.poster_url}` : 'https://placehold.co/500x750/374151/9CA3AF?text=No+Poster';
  const placeholderUrl = 'https://placehold.co/500x750/374151/9CA3AF?text=No+Poster';

  return (
    <div
      onClick={onClick}
      className="bg-gray-800 rounded-lg shadow-lg overflow-hidden cursor-pointer transform transition duration-300 hover:scale-105 hover:shadow-xl relative group" // Added group for hover effect on button
    >
      <img
        src={posterUrl}
        alt={`${movie.title} Poster`}
        className="w-full h-auto object-cover aspect-[2/3]" // Maintain aspect ratio
        onError={(e) => { e.target.onerror = null; e.target.src = placeholderUrl; }} // Fallback image
        loading="lazy" // Added lazy loading for performance
      />
      <div className="p-3">
        <h3 className="font-semibold text-sm truncate text-yellow-400">{movie.title}</h3>
        <p className="text-xs text-gray-400">{movie.release_year}</p>
      </div>
       {/* Watchlist Button Overlay - Improved visibility */}
       <button
            onClick={(e) => handleButtonClick(e, isOnWatchlist ? onRemoveFromWatchlist : onAddToWatchlist)}
            className={`absolute top-2 right-2 p-1.5 rounded-full text-white transition-all duration-200 ${
                isOnWatchlist
                ? 'bg-red-600 hover:bg-red-700'
                : 'bg-blue-600 hover:bg-blue-700'
            } opacity-0 group-hover:opacity-100 focus:opacity-100`} // Show on hover/focus
            aria-label={isOnWatchlist ? 'Remove from Watchlist' : 'Add to Watchlist'}
            title={isOnWatchlist ? 'Remove from Watchlist' : 'Add to Watchlist'}
       >
           {isOnWatchlist ? (
               <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                 <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12.502 0c-.283.045-.566.097-.852.152L4.772 5.79m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
               </svg>

            ) : (
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
            )}
        </button>
    </div>
  );
}


// Movie Modal Component
function MovieModal({ movie, onClose, onRate, existingRating, isOnWatchlist, onAddToWatchlist, onRemoveFromWatchlist }) {
  const [rating, setRating] = useState(existingRating || 0);

  // Construct the full poster URL
  const posterBaseUrl = "https://image.tmdb.org/t/p/w500";
  const posterUrl = movie.poster_url ? `${posterBaseUrl}${movie.poster_url}` : 'https://placehold.co/500x750/374151/9CA3AF?text=No+Poster';
  const placeholderUrl = 'https://placehold.co/500x750/374151/9CA3AF?text=No+Poster';


  // Update local rating state if existingRating changes (e.g., after submitting)
  useEffect(() => {
    setRating(existingRating || 0);
  }, [existingRating]);

  const handleRatingChange = (newRating) => {
    setRating(newRating); // Update local state immediately for visual feedback
    onRate(movie.id, newRating); // Call the prop to submit the rating via API
  };

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4 overflow-y-auto" // Added overflow-y-auto
      onClick={onClose} // Close modal on backdrop click
    >
      <div
        className="bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl overflow-hidden relative my-auto" // Added my-auto for vertical centering
        onClick={e => e.stopPropagation()} // Prevent modal close when clicking inside
      >
         {/* Close Button */}
         <button
            onClick={onClose}
            className="absolute top-3 right-3 text-gray-400 hover:text-white transition duration-150 z-10 bg-gray-900 bg-opacity-50 rounded-full p-1" // Added background for visibility
            aria-label="Close modal"
         >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-6 h-6">
               <path strokeLinecap="round" strokeLinejoin="round" d="m9.75 9.75 4.5 4.5m0-4.5-4.5 4.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
         </button>

         <div className="md:flex">
             {/* Poster */}
             <div className="md:flex-shrink-0">
                  <img
                    src={posterUrl}
                    alt={`${movie.title} Poster`}
                    className="w-full h-auto object-cover md:w-64 aspect-[2/3]"
                    onError={(e) => { e.target.onerror = null; e.target.src = placeholderUrl; }}
                   />
             </div>

             {/* Details */}
             <div className="p-6 flex flex-col justify-between">
                <div>
                   <h2 className="text-3xl font-bold mb-2 text-yellow-400">{movie.title} ({movie.release_year})</h2>
                   <p className="text-sm text-gray-400 mb-4">{movie.genres?.split('|').join(', ')}</p>
                   <p className="text-gray-300 mb-6">{movie.description || "No description available."}</p> {/* Added fallback */}
                </div>

                {/* Actions: Rating and Watchlist */}
                {/* MODIFICATION START: Added space-y-4 to the parent div */}
                <div className="mt-auto space-y-4">
                    <div>
                        <h3 className="text-lg font-semibold mb-2 text-gray-300">Rate this movie</h3>
                        <StarRating currentRating={rating} onRatingChange={handleRatingChange} />
                    </div>
                     <button
                        onClick={isOnWatchlist ? onRemoveFromWatchlist : onAddToWatchlist}
                        className={`w-full py-2 px-4 rounded-md font-semibold transition-colors duration-200 flex items-center justify-center ${
                            isOnWatchlist
                            ? 'bg-red-600 hover:bg-red-700 text-white'
                            : 'bg-blue-600 hover:bg-blue-700 text-white'
                        }`}
                    >
                        {isOnWatchlist ? (
                             <>
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 mr-2">
                                <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12.502 0c-.283.045-.566.097-.852.152L4.772 5.79m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                                </svg>
                                Remove from Watchlist
                            </>
                        ) : (
                             <>
                                 <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 mr-2">
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                                 </svg>
                                Add to Watchlist
                            </>
                        )}
                    </button>
                 </div>
                 {/* MODIFICATION END */}
             </div>
        </div>
      </div>
    </div>
  );
}


// Star Rating Component - Optimized for Half Stars
function StarRating({ currentRating = 0, onRatingChange, maxRating = 5 }) {
  const [hoverRating, setHoverRating] = useState(0);

  const handleMouseEnter = (ratingValue) => {
    setHoverRating(ratingValue);
  };

  const handleMouseLeave = () => {
    setHoverRating(0);
  };

  const handleClick = (ratingValue) => {
    onRatingChange(ratingValue);
  };

  // Determine the fill percentage for the stars container
  const fillPercentage = ((hoverRating || currentRating) / maxRating) * 100;

  return (
    <div
      className="flex relative cursor-pointer h-6" // <-- ADDED h-6
      onMouseLeave={handleMouseLeave}
      style={{ width: `${maxRating * 1.5}rem` }} // Set width based on star size (1.5rem = w-6)
    >
      {/* Background (Empty) Stars */}
      <div className="flex absolute top-0 left-0 text-gray-500">
        {[...Array(maxRating)].map((_, i) => (
          <svg key={`empty-${i}`} className="w-6 h-6" fill="currentColor" viewBox="0 0 20 20"><path d="M10 15l-5.878 3.09 1.123-6.545L.489 6.91l6.572-.955L10 0l2.939 5.955 6.572.955-4.756 4.635 1.123 6.545z"/></svg>
        ))}
      </div>

      {/* Foreground (Filled) Stars - clipped by width */}
      <div
        className="flex absolute top-0 left-0 text-yellow-400 overflow-hidden" // Overflow hidden clips the stars
        style={{ width: `${fillPercentage}%` }} // Dynamic width based on rating
      >
         {[...Array(maxRating)].map((_, i) => (
           <svg key={`filled-${i}`} className="w-6 h-6 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path d="M10 15l-5.878 3.09 1.123-6.545L.489 6.91l6.572-.955L10 0l2.939 5.955 6.572.955-4.756 4.635 1.123 6.545z"/></svg>
        ))}
      </div>

       {/* Invisible Hitboxes for Half-Star Interaction */}
       <div className="flex absolute top-0 left-0 w-full h-full">
            {[...Array(maxRating * 2)].map((_, index) => {
                const ratingValue = (index + 1) * 0.5;
                return (
                    <div
                        key={`hitbox-${index}`}
                        className="w-[0.75rem] h-full" // Half the width of a full star (w-6 = 1.5rem)
                        onMouseEnter={() => handleMouseEnter(ratingValue)}
                        onClick={() => handleClick(ratingValue)}
                        aria-label={`Rate ${ratingValue} stars`} // Accessibility
                    />
                );
            })}
       </div>
    </div>
  );
}


// Login Component
function Login({ onLogin, onNavigateRegister, isLoading, message }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!isLoading) {
      onLogin(email, password);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center font-inter p-4">
      <div className="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
        <h2 className="text-3xl font-bold text-center text-yellow-400 mb-8">MovieRec Login</h2>
        {message.text && (
          <div className={`p-3 mb-4 rounded text-center text-sm ${message.type === 'error' ? 'bg-red-800 text-red-100' : 'bg-green-800 text-green-100'}`}>
            {message.text}
          </div>
        )}
        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label className="block text-gray-400 text-sm font-bold mb-2" htmlFor="login-email">
              Email
            </label>
            <input
              id="login-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="shadow appearance-none border rounded w-full py-2 px-3 bg-gray-700 text-white leading-tight focus:outline-none focus:ring-2 focus:ring-yellow-400 focus:border-transparent"
            />
          </div>
          <div className="mb-6">
            <label className="block text-gray-400 text-sm font-bold mb-2" htmlFor="login-password">
              Password
            </label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="shadow appearance-none border rounded w-full py-2 px-3 bg-gray-700 text-white mb-3 leading-tight focus:outline-none focus:ring-2 focus:ring-yellow-400 focus:border-transparent"
            />
          </div>
          <div className="flex items-center justify-between">
            <button
              type="submit"
              disabled={isLoading}
              className="bg-yellow-400 hover:bg-yellow-500 text-gray-900 font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline w-full disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
            >
              {isLoading ? (
                  <>
                    <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-gray-900" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Logging in...
                  </>
              ) : 'Log In'}
            </button>
          </div>
          <p className="text-center text-gray-500 text-sm mt-6">
            Don't have an account?{' '}
            <button type="button" onClick={onNavigateRegister} className="font-bold text-yellow-400 hover:text-yellow-300 focus:outline-none">
              Register here
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}


// Register Component
function Register({ onRegister, onNavigateLogin, isLoading, message }) {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
     if (password.length < 4) {
      alert("Password must be at least 4 characters long."); // Simple validation
      return;
     }
    if (!isLoading) {
      onRegister(username, email, password);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center font-inter p-4">
      <div className="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
        <h2 className="text-3xl font-bold text-center text-yellow-400 mb-8">Create Your Account</h2>
         {message.text && (
           <div className={`p-3 mb-4 rounded text-center text-sm ${message.type === 'error' ? 'bg-red-800 text-red-100' : 'bg-green-800 text-green-100'}`}>
             {message.text}
           </div>
         )}
        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label className="block text-gray-400 text-sm font-bold mb-2" htmlFor="register-username">
              Username
            </label>
            <input
              id="register-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              className="shadow appearance-none border rounded w-full py-2 px-3 bg-gray-700 text-white leading-tight focus:outline-none focus:ring-2 focus:ring-yellow-400 focus:border-transparent"
            />
          </div>
          <div className="mb-4">
            <label className="block text-gray-400 text-sm font-bold mb-2" htmlFor="register-email">
              Email
            </label>
            <input
              id="register-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="shadow appearance-none border rounded w-full py-2 px-3 bg-gray-700 text-white leading-tight focus:outline-none focus:ring-2 focus:ring-yellow-400 focus:border-transparent"
            />
          </div>
          <div className="mb-6">
            <label className="block text-gray-400 text-sm font-bold mb-2" htmlFor="register-password">
              Password (min. 4 chars)
            </label>
            <input
              id="register-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength="4"
              className="shadow appearance-none border rounded w-full py-2 px-3 bg-gray-700 text-white mb-3 leading-tight focus:outline-none focus:ring-2 focus:ring-yellow-400 focus:border-transparent"
            />
          </div>
          <div className="flex items-center justify-between">
            <button
              type="submit"
              disabled={isLoading}
              className="bg-yellow-400 hover:bg-yellow-500 text-gray-900 font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline w-full disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
            >
              {isLoading ? (
                  <>
                    <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-gray-900" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Creating Account...
                  </>
                ) : 'Create Account'}
            </button>
          </div>
          <p className="text-center text-gray-500 text-sm mt-6">
            Already have an account?{' '}
            <button type="button" onClick={onNavigateLogin} className="font-bold text-yellow-400 hover:text-yellow-300 focus:outline-none">
              Login here
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}

