import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

// --- Constants ---
const API_URL = "http://127.0.0.1:8000"; // Your FastAPI backend URL

// --- Axios Instance with Interceptor ---
// Create an axios instance
const apiClient = axios.create({
    baseURL: API_URL,
});

// Add a request interceptor to include the token
apiClient.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('accessToken');
        if (token) {
            config.headers['Authorization'] = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        // Do something with request error
        console.error("Axios request interceptor error:", error); // Added console log
        return Promise.reject(error);
    }
);

// Add a response interceptor for logging (optional, but helpful for debugging)
apiClient.interceptors.response.use(
  (response) => {
    // console.log("Axios response received:", response); // Uncomment for detailed logs
    return response;
  },
  (error) => {
    console.error("Axios response interceptor error:", error.response || error.message); // Added console log
    // Handle specific errors like 401 Unauthorized globally if needed
    if (error.response && error.response.status === 401) {
      console.warn("Unauthorized request - logging out.");
      // Note: Calling handleLogout directly here might cause issues if it relies on state
      // It's often better to handle 401s where the call is made or use a global state/context
      // For simplicity, we'll rely on the checks within the fetch functions for now.
    }
    return Promise.reject(error);
  }
);


// --- Helper Functions ---
function getPosterUrl(path) {
    if (!path) {
        // Return a placeholder if no poster URL exists
        const placeholderText = "No Poster";
        return `https://placehold.co/500x750/374151/FFFFFF?text=${encodeURIComponent(placeholderText)}`;
    }
    return `https://image.tmdb.org/t/p/w500${path}`;
}

// --- React Components ---

// Star Rating Component (No changes needed)
const StarRating = ({ initialRating = 0, onRatingSubmit, readOnly = false }) => {
    const [rating, setRating] = useState(initialRating);
    const [hoverRating, setHoverRating] = useState(0);

    useEffect(() => {
        setRating(initialRating); // Update rating if initialRating changes
    }, [initialRating]);

    const handleMouseOver = (index) => {
        if (!readOnly) setHoverRating(index);
    };

    const handleMouseLeave = () => {
        if (!readOnly) setHoverRating(0);
    };

    const handleClick = (index) => {
        if (!readOnly) {
            const newRating = index;
            setRating(newRating);
            if (onRatingSubmit) {
                onRatingSubmit(newRating);
            }
        }
    };

    return (
        <div className="flex space-x-1">
            {[1, 2, 3, 4, 5].map((index) => (
                <svg
                    key={index}
                    onMouseOver={() => handleMouseOver(index)}
                    onMouseLeave={handleMouseLeave}
                    onClick={() => handleClick(index)}
                    className={`w-6 h-6 cursor-pointer ${
                        (hoverRating || rating) >= index
                            ? 'text-yellow-400'
                            : 'text-gray-400'
                    } ${readOnly ? 'cursor-default' : ''}`}
                    fill="currentColor"
                    viewBox="0 0 20 20"
                    xmlns="http://www.w3.org/2000/svg"
                >
                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.286 3.96a1 1 0 00.95.69h4.162c.969 0 1.371 1.24.588 1.81l-3.366 2.446a1 1 0 00-.364 1.118l1.287 3.96c.3.921-.755 1.688-1.539 1.118l-3.365-2.446a1 1 0 00-1.175 0l-3.366 2.446c-.783.57-1.838-.197-1.539-1.118l1.287-3.96a1 1 0 00-.364-1.118L2.062 9.387c-.783-.57-.38-1.81.588-1.81h4.162a1 1 0 00.95-.69l1.286-3.96z"></path>
                </svg>
            ))}
        </div>
    );
};


// Movie Card Component (No changes needed)
const MovieCard = ({ movie, onClick }) => (
    <div
        className="bg-gray-700 rounded-lg overflow-hidden shadow-lg cursor-pointer transform hover:scale-105 transition-transform duration-200 flex flex-col h-full"
        onClick={() => onClick(movie)}
    >
        <img
            src={getPosterUrl(movie.poster_url)}
            alt={`${movie.title} poster`}
            className="w-full h-48 sm:h-64 object-cover" // Adjusted height
            onError={(e) => { // Basic error handling for images
               e.target.onerror = null;
               const placeholderText = movie.title || "Movie Poster";
               e.target.src=`https://placehold.co/500x750/374151/FFFFFF?text=${encodeURIComponent(placeholderText)}`;
             }}
        />
        <div className="p-3 sm:p-4 flex flex-col flex-grow">
            <h3 className="text-base sm:text-lg font-semibold mb-1 truncate">{movie.title}</h3>
            <p className="text-xs sm:text-sm text-gray-400 mb-2">{movie.release_year}</p>
             {/* <p className="text-xs text-gray-400 flex-grow">{movie.genres?.split('|').join(', ')}</p> */}
        </div>
    </div>
);


// Movie Modal Component (No changes needed)
const MovieModal = ({ movie, onClose, onRate, existingRating }) => {
    const handleRatingSubmit = async (score) => {
        console.log(`Rating movie ${movie.id} with score ${score}`);
        try {
            await onRate(movie.id, score);
            // Optionally close modal after rating, or show a success message
             onClose(); // Close modal after successful rating
        } catch (error) {
            console.error("Error submitting rating in modal:", error);
            // Show error to user in the modal? Maybe add an error state here.
        }
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4 overflow-y-auto">
            <div className="bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
                 {/* Header with Close Button */}
                <div className="flex justify-between items-center p-4 border-b border-gray-700 sticky top-0 bg-gray-800 z-10 flex-shrink-0">
                    <h2 className="text-xl md:text-2xl font-semibold truncate pr-4">{movie.title} ({movie.release_year})</h2>
                    <button
                        onClick={onClose}
                        className="text-gray-400 hover:text-white text-3xl font-bold leading-none p-1" // Added padding
                        aria-label="Close modal"
                    >
                        &times;
                    </button>
                </div>

                {/* Body Content */}
                <div className="p-4 md:p-6 md:flex md:space-x-6 overflow-y-auto flex-grow">
                    {/* Left side: Poster */}
                    <div className="md:w-1/3 mb-4 md:mb-0 flex-shrink-0">
                         <img
                             src={getPosterUrl(movie.poster_url)}
                             alt={`${movie.title} poster`}
                             className="w-full h-auto object-contain rounded-lg shadow-md max-h-96" // Contain poster
                             onError={(e) => { // Consistent error handling
                                e.target.onerror = null;
                                const placeholderText = movie.title || "Movie Poster";
                                e.target.src=`https://placehold.co/500x750/374151/FFFFFF?text=${encodeURIComponent(placeholderText)}`;
                              }}
                         />
                    </div>

                    {/* Right side: Details and Rating */}
                    <div className="md:w-2/3">
                        <p className="text-gray-400 mb-2 text-sm">{movie.genres?.split('|').join(', ')}</p>
                        <p className="text-gray-300 mb-6">{movie.description || "No description available."}</p>

                        <h3 className="text-lg font-semibold mb-2">Rate this movie</h3>
                        <StarRating
                            initialRating={existingRating} // Pass existing rating here
                            onRatingSubmit={handleRatingSubmit}
                        />
                         {existingRating > 0 && (
                            <p className="text-sm text-yellow-400 mt-2">Your rating: {existingRating} stars</p>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

// --- Main App Component ---
export default function App() {
    // --- State Variables ---
    const [page, setPage] = useState('Loading'); // Start in Loading state
    const [token, setToken] = useState(null); // Initialize token to null
    const [currentUser, setCurrentUser] = useState(null);
    const [recommendations, setRecommendations] = useState([]);
    const [userRatings, setUserRatings] = useState({}); // Stores ratings as { movie_id: score }
    const [selectedMovie, setSelectedMovie] = useState(null);
    const [searchQuery, setSearchQuery] = useState("");
    const [searchResults, setSearchResults] = useState([]);
    const [isLoading, setIsLoading] = useState(true); // Combined loading state
    const [errorMessage, setErrorMessage] = useState("");

    // --- Genre State ---
    const [genres] = useState([ // Hardcoded, using useState for consistency
        'Action', 'Adventure', 'Animation', 'Children', 'Comedy', 'Crime',
        'Documentary', 'Drama', 'Fantasy', 'Film-Noir', 'Horror', 'IMAX',
        'Musical', 'Mystery', 'Romance', 'Sci-Fi', 'Thriller', 'War', 'Western'
    ]);
    const [selectedGenre, setSelectedGenre] = useState(null);
    const [genreResults, setGenreResults] = useState([]);

    // --- Authentication Logic ---

    // Check localStorage for token on initial mount
    useEffect(() => {
        console.log("App mounted. Checking for token...");
        const storedToken = localStorage.getItem('accessToken');
        if (storedToken) {
            console.log("Token found in localStorage.");
            setToken(storedToken);
            // We'll fetch the user profile in the next effect
            setPage('App'); // Assume App page, profile fetch will verify
        } else {
            console.log("No token found. Setting page to Login.");
            setPage('Login');
            setIsLoading(false); // Not loading if going straight to login
        }
    }, []); // Empty dependency array, runs only once on mount

    // Fetch User Profile if token exists and page is App
    // This effect runs *after* the initial token check
    useEffect(() => {
        if (token && page === 'App') {
            console.log("Token exists and page is App. Fetching user profile...");
            setIsLoading(true); // Start loading when fetching profile
            const fetchUserProfile = async () => {
                try {
                    const response = await apiClient.get('/users/me');
                    console.log("User profile fetched successfully:", response.data);
                    setCurrentUser(response.data);
                    // Let the data fetching effect handle loading state after this
                } catch (error) {
                    console.error("Failed to fetch user profile (token might be invalid):", error);
                    handleLogout(); // Log out if token is invalid or request fails
                } finally {
                    // setIsLoading(false); // Loading is finished by the data fetch effect
                }
            };
            fetchUserProfile();
        } else if (!token && page !== 'Login' && page !== 'Register') {
             // If token becomes null unexpectedly while in App, redirect to Login
             console.log("Token is null, but page is not Login/Register. Logging out.");
             handleLogout();
        }
    }, [token, page]); // Rerun if token or page changes

    // Fetch Initial Data (recommendations and user ratings) *after* user profile is confirmed
    useEffect(() => {
        // Only run if we are logged in (token exists), on the App page, AND currentUser profile has been loaded
        if (token && page === 'App' && currentUser) {
             console.log("User profile loaded. Fetching initial recommendations and ratings...");
             setIsLoading(true); // Start loading data
             setErrorMessage("");
             setSelectedGenre(null); // Reset genre on initial load/login
             setSearchResults([]);   // Reset search on initial load/login

             const fetchInitialData = async () => {
                try {
                    console.log("Making parallel API calls for recs and ratings...");
                    // Fetch recommendations and ratings in parallel
                    const [recsResponse, ratingsResponse] = await Promise.all([
                        apiClient.get('/recommendations/'),
                        apiClient.get('/users/me/ratings')
                    ]);
                    console.log("Recommendations response:", recsResponse.data);
                    console.log("Ratings response:", ratingsResponse.data);

                    setRecommendations(recsResponse.data);

                    // Convert ratings array to map { movie_id: score }
                    const ratingsMap = ratingsResponse.data.reduce((acc, rating) => {
                        acc[rating.movie_id] = rating.score;
                        return acc;
                    }, {});
                    console.log("Ratings map created:", ratingsMap);
                    setUserRatings(ratingsMap);

                } catch (error) {
                    console.error("Failed to fetch initial data (recs/ratings):", error);
                    setErrorMessage("Could not load recommendations or your ratings.");
                    if (error.response?.status === 401) {
                         console.warn("Unauthorized fetching initial data. Logging out.");
                         handleLogout(); // Log out if unauthorized
                    }
                } finally {
                     console.log("Finished fetching initial data.");
                     setIsLoading(false); // Stop loading after data is fetched (or fails)
                }
            };
            fetchInitialData();
        }
    }, [token, page, currentUser]); // Rerun if user logs in or profile changes


    const handleLogin = async (email, password) => {
        console.log("handleLogin called with email:", email); // Log start
        setIsLoading(true);
        setErrorMessage("");
        try {
            const formData = new URLSearchParams();
            formData.append('username', email); // API expects 'username' for the email field
            formData.append('password', password);
            console.log("Attempting to POST /token/");

            // Use the standard axios instance here, not apiClient, as login doesn't need prior auth
            const response = await axios.post(`${API_URL}/token/`, formData, {
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            });
            console.log("Login successful:", response.data);
            const { access_token } = response.data;
            localStorage.setItem('accessToken', access_token);
            setToken(access_token); // Update token state
            // Reset states for the new user session
            setRecommendations([]);
            setUserRatings({});
            setSearchResults([]);
            setSelectedGenre(null);
            setGenreResults([]);
            setCurrentUser(null); // Clear old user profile, let effect fetch new one
            setPage('App'); // Change page AFTER setting token
            console.log("Navigating to App page.");
        } catch (error) {
            console.error("Login failed:", error.response?.data?.detail || error.message);
            setErrorMessage(error.response?.data?.detail || "Login failed. Please check credentials.");
        } finally {
             console.log("handleLogin finished.");
             setIsLoading(false); // Stop loading indicator
        }
    };

    const handleRegister = async (username, email, password) => {
        console.log("handleRegister called with username:", username, "email:", email); // Log start
        setIsLoading(true);
        setErrorMessage("");
        try {
             console.log("Attempting to POST /register/");
             // Use standard axios for registration
             await axios.post(`${API_URL}/register/`, { username, email, password });
             console.log("Registration successful.");
             setErrorMessage("Registration successful! Please login."); // Display success message
             setPage('Login'); // Go to login page after registration
        } catch (error) {
            console.error("Registration failed:", error.response?.data?.detail || error.message);
            setErrorMessage(error.response?.data?.detail || "Registration failed. Please try again.");
        } finally {
             console.log("handleRegister finished.");
             setIsLoading(false); // Stop loading indicator
        }
    };

    // Use useCallback to memoize handleLogout
    const handleLogout = useCallback(() => {
        console.log("handleLogout called.");
        localStorage.removeItem('accessToken');
        setToken(null);
        setCurrentUser(null);
        // Clear all movie/rating data
        setRecommendations([]);
        setUserRatings({});
        setSearchResults([]);
        setSelectedGenre(null);
        setGenreResults([]);
        setErrorMessage("");
        setSearchQuery("");
        setPage('Login'); // Ensure navigation back to Login
        setIsLoading(false); // Ensure loading is stopped
        console.log("User logged out, state cleared, navigating to Login.");
    }, []); // No dependencies needed for logout


    // --- Search Logic ---
    const handleSearch = async (e) => {
        e.preventDefault();
        console.log("handleSearch called with query:", searchQuery);
        if (!searchQuery.trim()) {
             setSearchResults([]);
             setSelectedGenre(null); // Clear genre filter if search is empty
             setErrorMessage("");
             // No need to refetch recommendations, just clear results
             console.log("Empty search query, clearing results.");
            return;
        }
        setIsLoading(true);
        setErrorMessage("");
        setSelectedGenre(null); // Clear genre when searching
        setGenreResults([]); // Clear genre results
        try {
            console.log(`Searching for: ${searchQuery}`);
            const response = await apiClient.get(`/movies/?search=${encodeURIComponent(searchQuery)}&limit=50`); // Use apiClient
            console.log("Search results received:", response.data);
            setSearchResults(response.data);
            if (response.data.length === 0) {
                 setErrorMessage(`No movies found matching "${searchQuery}".`);
            }
        } catch (error) {
            console.error("Search failed:", error);
            setErrorMessage("Could not perform search.");
             if (error.response?.status === 401) {
                 handleLogout(); // Log out if unauthorized
            }
        } finally {
             console.log("handleSearch finished.");
             setIsLoading(false);
        }
    };

    // --- Genre Filter Logic ---
    const handleGenreSelect = async (genre) => {
        console.log("handleGenreSelect called with genre:", genre);
        if (selectedGenre === genre) {
            // If clicking the same genre again, clear the filter
            console.log("Clearing genre filter.");
            setSelectedGenre(null);
            setGenreResults([]);
            setSearchResults([]); // Also clear search
            setErrorMessage("");
            // Refetch recommendations when clearing genre filter
            // Let the main data fetching effect handle this by dependency on selectedGenre (or add manual fetch)
            // For simplicity, we'll rely on the effect for now.
            return;
        }

        setIsLoading(true);
        setErrorMessage("");
        setSelectedGenre(genre);
        setSearchQuery(""); // Clear search query
        setSearchResults([]); // Clear search results

        try {
            console.log(`Fetching movies for genre: ${genre}`);
            const response = await apiClient.get(`/movies/?genre=${encodeURIComponent(genre)}&limit=50`); // Use apiClient
            console.log(`Genre results for ${genre}:`, response.data);
            setGenreResults(response.data);
             if (response.data.length === 0) {
                 setErrorMessage(`No movies found in the "${genre}" genre.`);
            }
        } catch (error) {
            console.error(`Failed to fetch genre ${genre}:`, error);
            setErrorMessage(`Could not load movies for the "${genre}" genre.`);
             if (error.response?.status === 401) {
                 handleLogout(); // Log out if unauthorized
            }
        } finally {
             console.log("handleGenreSelect finished.");
             setIsLoading(false);
        }
    };


    // --- Rating Logic ---
    const handleRateMovie = async (movieId, score) => {
        console.log(`handleRateMovie called for movie ${movieId} with score ${score}`);
        if (!token) {
             setErrorMessage("You must be logged in to rate movies.");
             console.warn("Attempted to rate while logged out.");
             return Promise.reject("Not logged in"); // Return rejected promise
        }
        setErrorMessage(""); // Clear previous errors
        try {
            console.log("Attempting to POST /ratings/");
            const response = await apiClient.post('/ratings/', { movie_id: movieId, score }); // Use apiClient
            console.log("Rating submitted successfully:", response.data);
            // Update the local userRatings state immediately for instant feedback
            setUserRatings(prevRatings => {
                const newRatings = { ...prevRatings, [movieId]: score };
                console.log("Updating userRatings state:", newRatings);
                return newRatings;
            });
             return response.data; // Return data on success

        } catch (error) {
            console.error("Failed to submit rating:", error.response?.data?.detail || error.message);
            setErrorMessage(error.response?.data?.detail || "Could not submit rating.");
             if (error.response?.status === 401) {
                 handleLogout(); // Log out if unauthorized
            }
            // Re-throw the error so the modal can know it failed
            throw error;
        }
        // No finally block needed here, let promise resolve/reject
    };


    // --- UI Rendering ---

     // Loading State (before token check completes)
     if (page === 'Loading') {
        return <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">Loading...</div>;
     }

    // Login Page
    if (page === 'Login') {
        return (
            <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center p-4">
                <div className="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
                    <h1 className="text-3xl font-bold mb-6 text-center text-yellow-400">MovieRec Login</h1>
                    {errorMessage && <p className="mb-4 text-center text-red-500 bg-red-900 bg-opacity-30 p-3 rounded">{errorMessage}</p>}
                    <form onSubmit={(e) => {
                        e.preventDefault();
                        const email = e.target.email.value;
                        const password = e.target.password.value;
                        handleLogin(email, password);
                    }}>
                        <div className="mb-4">
                            <label className="block text-gray-400 mb-2" htmlFor="email">Email</label>
                            <input className="w-full p-3 bg-gray-700 rounded text-white focus:outline-none focus:ring-2 focus:ring-yellow-500" type="email" id="email" name="email" required />
                        </div>
                        <div className="mb-6">
                            <label className="block text-gray-400 mb-2" htmlFor="password">Password</label>
                            <input className="w-full p-3 bg-gray-700 rounded text-white focus:outline-none focus:ring-2 focus:ring-yellow-500" type="password" id="password" name="password" required />
                        </div>
                        <button className="w-full bg-yellow-500 hover:bg-yellow-600 text-gray-900 font-bold py-3 px-4 rounded transition duration-200" type="submit" disabled={isLoading}>
                            {isLoading ? 'Logging in...' : 'Login'}
                        </button>
                    </form>
                    <p className="mt-6 text-center text-gray-400">
                        Don't have an account? <button className="text-yellow-400 hover:underline" onClick={() => { setErrorMessage(""); setPage('Register'); }}>Register here</button>
                    </p>
                </div>
            </div>
        );
    }

    // Registration Page
    if (page === 'Register') {
        return (
             <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center p-4">
                <div className="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
                    <h1 className="text-3xl font-bold mb-6 text-center text-yellow-400">Create Your Account</h1>
                     {errorMessage && <p className="mb-4 text-center text-red-500 bg-red-900 bg-opacity-30 p-3 rounded">{errorMessage}</p>}
                    <form onSubmit={(e) => {
                        e.preventDefault();
                        const username = e.target.username.value;
                        const email = e.target.email.value;
                        const password = e.target.password.value;
                        handleRegister(username, email, password);
                    }}>
                        <div className="mb-4">
                            <label className="block text-gray-400 mb-2" htmlFor="username">Username</label>
                            <input className="w-full p-3 bg-gray-700 rounded text-white focus:outline-none focus:ring-2 focus:ring-yellow-500" type="text" id="username" name="username" required />
                        </div>
                        <div className="mb-4">
                            <label className="block text-gray-400 mb-2" htmlFor="email">Email</label>
                            <input className="w-full p-3 bg-gray-700 rounded text-white focus:outline-none focus:ring-2 focus:ring-yellow-500" type="email" id="email" name="email" required />
                        </div>
                        <div className="mb-6">
                            <label className="block text-gray-400 mb-2" htmlFor="password">Password (min. 4 chars)</label>
                            <input className="w-full p-3 bg-gray-700 rounded text-white focus:outline-none focus:ring-2 focus:ring-yellow-500" type="password" id="password" name="password" minLength="4" required />
                        </div>
                        <button className="w-full bg-yellow-500 hover:bg-yellow-600 text-gray-900 font-bold py-3 px-4 rounded transition duration-200" type="submit" disabled={isLoading}>
                             {isLoading ? 'Creating Account...' : 'Create Account'}
                        </button>
                    </form>
                    <p className="mt-6 text-center text-gray-400">
                        Already have an account? <button className="text-yellow-400 hover:underline" onClick={() => { setErrorMessage(""); setPage('Login'); }}>Login here</button>
                    </p>
                </div>
            </div>
        );
    }

    // Main App Page (Logged In)
    if (page === 'App') {
         // Determine which list of movies to display
        let moviesToDisplay = [];
        let sectionTitle = "";
        let isDisplayingRecommendations = false;

        if (searchResults.length > 0) {
            moviesToDisplay = searchResults;
            sectionTitle = `Search Results for "${searchQuery}"`;
        } else if (selectedGenre) { // Show genre results even if empty, message handles it
            moviesToDisplay = genreResults;
            sectionTitle = `Movies in ${selectedGenre}`;
        } else {
            moviesToDisplay = recommendations;
            sectionTitle = "Recommended For You";
            isDisplayingRecommendations = true;
        }


        return (
            <div className="min-h-screen bg-gray-900 text-white p-4 md:p-8">
                {/* Header */}
                <header className="flex flex-col md:flex-row justify-between items-center mb-6 md:mb-10">
                    <h1 className="text-3xl md:text-4xl font-bold text-yellow-400 mb-4 md:mb-0">🎬 MovieRec</h1>
                    <div className="flex items-center space-x-4 w-full md:w-auto">
                        <span className="text-gray-300 hidden sm:inline">Welcome, {currentUser?.username || 'User'}!</span>
                         {/* Search Form */}
                         <form onSubmit={handleSearch} className="flex-grow md:flex-grow-0 md:w-64">
                            <div className="relative">
                                <input
                                    type="search"
                                    placeholder="Search for movies..."
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    className="w-full p-2 pl-4 pr-10 bg-gray-800 rounded-full text-white border border-gray-700 focus:outline-none focus:ring-2 focus:ring-yellow-500"
                                />
                                <button type="submit" className="absolute right-0 top-0 mt-2 mr-3 text-gray-400 hover:text-white">
                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                                </button>
                            </div>
                        </form>
                        <button
                            onClick={handleLogout}
                            className="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded transition duration-200"
                        >
                            Logout
                        </button>
                    </div>
                </header>

                 {/* Error Message Display */}
                 {errorMessage && !isLoading && ( // Show error only if not loading
                    <div className="mb-6 p-4 bg-red-900 bg-opacity-50 text-red-300 border border-red-700 rounded-lg text-center">
                        {errorMessage}
                    </div>
                )}

                 {/* Genre Filter Buttons */}
                <div className="mb-8">
                    <h2 className="text-xl font-semibold mb-4 flex items-center">
                        {/* Genre Icon */}
                        Browse by Genre
                    </h2>
                    <div className="flex flex-wrap gap-2">
                        {genres.map(genre => (
                            <button
                                key={genre}
                                onClick={() => handleGenreSelect(genre)}
                                className={`px-4 py-1 rounded-full text-sm font-medium transition duration-200 ${
                                    selectedGenre === genre
                                        ? 'bg-yellow-500 text-gray-900'
                                        : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                                }`}
                                disabled={isLoading} // Disable while loading
                            >
                                {genre}
                            </button>
                        ))}
                         {selectedGenre && ( // Show a "Clear Filter" button if a genre is selected
                            <button
                                onClick={() => handleGenreSelect(selectedGenre)} // Click again to clear
                                className="px-4 py-1 rounded-full text-sm font-medium bg-red-600 hover:bg-red-700 text-white transition duration-200"
                                disabled={isLoading} // Disable while loading
                            >
                                Clear Filter &times;
                            </button>
                        )}
                    </div>
                </div>


                {/* Main Content Area: Recommendations or Search Results or Genre Results */}
                 <section>
                    <h2 className="text-2xl font-semibold mb-6 flex items-center">
                        {/* Section Icon */}
                        {sectionTitle}
                    </h2>

                    {isLoading ? (
                        <div className="text-center text-gray-400 text-xl py-10">Loading movies...</div> // Enhanced loading
                    ) : moviesToDisplay.length > 0 ? (
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 md:gap-6">
                            {moviesToDisplay.map(movie => (
                                <MovieCard key={movie.id} movie={movie} onClick={setSelectedMovie} />
                            ))}
                        </div>
                    ) : !errorMessage ? ( // Only show "no movies" if there isn't already an error message
                        <div className="text-center text-gray-400 py-10">
                             {selectedGenre ? `No movies found for ${selectedGenre}.`
                             : searchResults.length === 0 && searchQuery ? `No movies found for "${searchQuery}".`
                             : isDisplayingRecommendations ? "No recommendations available yet. Try rating some movies!"
                             : "No movies to display." // Generic fallback
                            }
                        </div>
                    ) : null /* Error message is already displayed above */}
                 </section>

                {/* Movie Modal */}
                {selectedMovie && (
                    <MovieModal
                        movie={selectedMovie}
                        onClose={() => setSelectedMovie(null)}
                        onRate={handleRateMovie}
                        existingRating={userRatings[selectedMovie.id] || 0} // Pass existing rating from state map
                    />
                )}
            </div>
        );
    }

     // Fallback for unknown page state (should ideally not happen)
    return <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">An unexpected error occurred. Please try refreshing.</div>;
}

