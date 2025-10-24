import { useState, useEffect } from 'react';
import axios from 'axios';

// --- Constants ---
const API_URL = "http://127.0.0.1:8000";

// --- Axios API Client ---
// Create a global API client instance
// This is better than using axios.get() everywhere
const apiClient = axios.create({
  baseURL: API_URL,
});

// Use an "interceptor" to automatically add the auth token to every request
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      // Add the "Authorization: Bearer <token>" header
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);


// --- Main App Component (Now an Auth Router) ---
export default function App() {
  // Page state: 'login', 'register', or 'app'
  const [page, setPage] = useState('login'); 
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [currentUser, setCurrentUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true); // Show spinner on initial load

  // --- Auth Effect ---
  // On load, check if we have a token and if it's valid
  useEffect(() => {
    const validateToken = async () => {
      if (token) {
        try {
          // apiClient automatically uses the token from localStorage
          // We call the new /users/me endpoint to get our own user details
          const response = await apiClient.get('/users/me');
          setCurrentUser(response.data);
          setPage('app'); // If token is valid, go to the app
        } catch (error) {
          // Token is invalid or expired
          console.error("Token validation failed:", error);
          localStorage.removeItem('token');
          setToken(null);
          setCurrentUser(null);
          setPage('login'); // Go to login
        }
      } else {
        setPage('login'); // No token, go to login
      }
      setAuthLoading(false); // Done checking, hide spinner
    };

    validateToken();
  }, [token]); // This effect runs when the app loads or when the token state changes

  // --- Auth Handlers ---
  
  const handleLogin = async (email, password) => {
    try {
      // FastAPI's OAuth2 expects form data, not JSON
      const formData = new URLSearchParams();
      formData.append('username', email); // It expects 'username', but we're sending email
      formData.append('password', password);

      const response = await apiClient.post('/token/', formData, {
         headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });

      const newAuthToken = response.data.access_token;
      localStorage.setItem('token', newAuthToken);
      setToken(newAuthToken); // This will trigger the useEffect to fetch user and change page

    } catch (error) {
      console.error("Login failed:", error);
      // Return the error message to display in the form
      return error.response?.data?.detail || "An unknown error occurred.";
    }
  };

  const handleRegister = async (username, email, password) => {
    try {
      await apiClient.post('/register/', {
        username,
        email,
        password,
      });
      // After successful registration, send them to the login page
      setPage('login');
      return null; // No error

    } catch (error) {
      console.error("Registration failed:", error);
      return error.response?.data?.detail || "An unknown error occurred.";
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    setToken(null);
    setCurrentUser(null);
    setPage('login'); // Go to login page
  };
  
  // --- Render Logic ---

  if (authLoading) {
    return <FullPageSpinner />;
  }

  if (page === 'login') {
    return <LoginPage onLogin={handleLogin} onGoToRegister={() => setPage('register')} />;
  }

  if (page === 'register') {
    return <RegisterPage onRegister={handleRegister} onGoToLogin={() => setPage('login')} />;
  }

  if (page === 'app' && currentUser) {
    // We are logged in, show the main MovieApp
    return <MovieApp user={currentUser} onLogout={handleLogout} />;
  }

  // Fallback (shouldn't really be reached)
  return <LoginPage onLogin={handleLogin} onGoToRegister={() => setPage('register')} />;
}

// ==================================================================
// --- MAIN MOVIE APPLICATION (Protected) ---
// This is our old "App" component, now renamed to "MovieApp"
// ==================================================================

function MovieApp({ user, onLogout }) {
  const [recommendations, setRecommendations] = useState([]);
  const [userRatings, setUserRatings] = useState({});
  const [selectedMovie, setSelectedMovie] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  // Fetch initial data (recommendations and user ratings) on page load
  useEffect(() => {
    const fetchInitialData = async () => {
      try {
        setIsLoading(true);
        setErrorMessage("");
        
        // Use apiClient - it sends the token automatically!
        const recsResponse = await apiClient.get('/recommendations/');
        setRecommendations(recsResponse.data);
        
        // Use the new /users/me/ratings endpoint
        const ratingsResponse = await apiClient.get('/users/me/ratings');
        // Convert array of {movie_id, score} to a fast-lookup map {movie_id: score}
        const ratingsMap = ratingsResponse.data.reduce((acc, rating) => {
          acc[rating.movie_id] = rating.score;
          return acc;
        }, {});
        setUserRatings(ratingsMap);

      } catch (err) {
        console.error("Error fetching initial data:", err);
        if (err.response && err.response.status === 401) {
          // Token is bad, force logout
          onLogout();
        } else {
          setErrorMessage("Could not fetch data. Is the backend server running?");
        }
      } finally {
        setIsLoading(false);
      }
    };
    
    fetchInitialData();
  }, [onLogout]); // Add onLogout to dependency array

  // Fetch search results when searchQuery changes
  useEffect(() => {
    if (searchQuery.trim() === "") {
      setSearchResults([]);
      return;
    }

    const fetchSearch = async () => {
      try {
        setErrorMessage("");
        // Use apiClient for public endpoint
        const response = await apiClient.get('/movies/', {
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
    setErrorMessage(""); 
    if (!selectedMovie) return;

    // We no longer need user_id, the token handles it!
    const newRating = {
      movie_id: selectedMovie.id,
      score: rating,
    };

    try {
      // Use apiClient
      const response = await apiClient.post('/ratings/', newRating);
      
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
      if (err.response && err.response.status === 401) {
        onLogout();
      } else {
        setErrorMessage("Could not submit rating.");
      }
    }
  };
  
  const fetchRecommendations = async () => {
    try {
      setErrorMessage("");
      // Use apiClient
      const response = await apiClient.get('/recommendations/');
      setRecommendations(response.data);
    } catch (err) {
      console.error("Error fetching recommendations:", err);
    }
  };

  // --- Render Logic ---

  const moviesToShow = searchQuery.trim() ? searchResults : recommendations;
  const title = searchQuery.trim() ? "Search Results" : "Recommended For You";

  return (
    <div className="min-h-screen bg-gray-900 text-white font-sans">
      <Header 
        user={user}
        onLogout={onLogout}
        searchQuery={searchQuery} 
        setSearchQuery={setSearchQuery} 
      />

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

// ==================================================================
// --- AUTH PAGE COMPONENTS ---
// ==================================================================

function LoginPage({ onLogin, onGoToRegister }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    const apiError = await onLogin(email, password);
    setLoading(false);
    if (apiError) {
      setError(apiError);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center p-4">
      <div className="bg-gray-800 p-8 rounded-lg shadow-2xl w-full max-w-md">
        <div className="text-3xl font-bold text-yellow-400 flex items-center justify-center mb-6">
          <LogoIcon />
          MovieRec
        </div>
        <h2 className="text-2xl font-bold text-center text-white mb-6">Login to your account</h2>
        
        {error && <p className="bg-red-800 text-red-100 p-3 rounded-lg mb-4 text-center">{error}</p>}
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <AuthInput
            id="email"
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
          />
          <AuthInput
            id="password"
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-yellow-400 text-gray-900 font-bold py-3 px-4 rounded-lg hover:bg-yellow-300 transition-colors disabled:opacity-50"
          >
            {loading ? 'Logging in...' : 'Login'}
          </button>
        </form>
        <p className="text-center text-gray-400 mt-6">
          Don't have an account?{' '}
          <button onClick={onGoToRegister} className="text-yellow-400 font-semibold hover:underline">
            Register here
          </button>
        </p>
      </div>
    </div>
  );
}

function RegisterPage({ onRegister, onGoToLogin }) {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (password.length < 4) {
      setError("Password must be at least 4 characters long.");
      return;
    }
    setError('');
    setLoading(true);
    const apiError = await onRegister(username, email, password);
    setLoading(false);
    if (apiError) {
      setError(apiError);
    } else {
      // If registration is successful (no error), show an alert
      // and then go to login
      alert("Registration successful! Please log in.");
      onGoToLogin();
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center p-4">
      <div className="bg-gray-800 p-8 rounded-lg shadow-2xl w-full max-w-md">
        <h2 className="text-3xl font-bold text-center text-yellow-400 mb-6">Create Your Account</h2>
        
        {error && <p className="bg-red-800 text-red-100 p-3 rounded-lg mb-4 text-center">{error}</p>}
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <AuthInput
            id="username"
            label="Username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
          <AuthInput
            id="email"
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
          />
          <AuthInput
            id="password"
            label="Password (min. 4 chars)"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-yellow-400 text-gray-900 font-bold py-3 px-4 rounded-lg hover:bg-yellow-300 transition-colors disabled:opacity-50"
          >
            {loading ? 'Registering...' : 'Create Account'}
          </button>
        </form>
        <p className="text-center text-gray-400 mt-6">
          Already have an account?{' '}
          <button onClick={onGoToLogin} className="text-yellow-400 font-semibold hover:underline">
            Login here
          </button>
        </p>
      </div>
    </div>
  );
}

// Re-usable input component for auth forms
function AuthInput({ id, label, type, value, onChange, autoComplete }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-gray-300 mb-1">
        {label}
      </label>
      <input
        id={id}
        name={id}
        type={type}
        required
        value={value}
        onChange={onChange}
        autoComplete={autoComplete}
        className="w-full bg-gray-700 text-white px-4 py-3 rounded-lg focus:outline-none focus:ring-2 focus:ring-yellow-400 border border-gray-600"
      />
    </div>
  );
}

function FullPageSpinner() {
  return (
    <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">
      <LoadingSpinner />
    </div>
  );
}


// ==================================================================
// --- ORIGINAL APP COMPONENTS (Updated Header) ---
// (These are all the same as the last version, just included for
// a complete single-file copy/paste)
// ==================================================================

function Header({ user, onLogout, searchQuery, setSearchQuery }) {
  return (
    <header className="bg-gray-800 shadow-lg sticky top-0 z-50">
      <nav className="container mx-auto px-4 py-4 flex justify-between items-center">
        <div className="text-2xl font-bold text-yellow-400 flex items-center">
          <LogoIcon />
          MovieRec
        </div>
        <div className="flex items-center space-x-4">
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
          <div className="text-gray-300">|</div>
          {/* Show user's name and logout button */}
          <span className="text-gray-300 hidden sm:block">Welcome, {user.username}!</span>
          <button
            onClick={onLogout}
            className="bg-yellow-400 text-gray-900 font-semibold py-2 px-4 rounded-lg text-sm hover:bg-yellow-300 transition-colors"
          >
            Logout
          </button>
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
  const mainGenre = movie.genres ? movie.genres.split('|')[0] : 'Movie';

  return (
    <div
      onClick={() => onMovieSelect(movie)}
      className="bg-gray-800 rounded-lg shadow-lg overflow-hidden cursor-pointer transform transition-transform duration-300 hover:scale-105 hover:shadow-yellow-400/20 group"
    >
      <div className="aspect-[2/3] w-full bg-gray-700 flex items-center justify-center overflow-hidden">
        {movie.poster_url ? (
          <img 
            src={movie.poster_url} 
            alt={movie.title} 
            className="w-full h-full object-cover transition-opacity duration-300 group-hover:opacity-75"
            onError={(e) => { 
              // If poster fails to load, hide the img tag to show the fallback
              e.target.style.display = 'none'; 
              e.target.parentElement.querySelector('div').style.display = 'flex';
            }}
          />
        ) : null}
        {/* Fallback if no poster URL or if image fails to load */}
        <div style={{ display: movie.poster_url ? 'none' : 'flex' }} className="w-full h-full items-center justify-center p-4">
          <span className="text-lg font-bold text-center text-yellow-400">{movie.title}</span>
        </div>
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
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4 overflow-y-auto">
      {/* Click outside to close */}
      <div className="absolute inset-0 z-[-1]" onClick={onClose}></div>

      <div 
        className="bg-gray-800 rounded-lg shadow-2xl w-full max-w-lg relative my-8"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-3 right-3 text-gray-400 hover:text-white text-3xl z-10"
        >
          &times;
        </button>
        
        <div className="w-full h-48 bg-gray-700 rounded-t-lg overflow-hidden relative">
          {movie.poster_url && (
            <img 
              src={movie.poster_url} 
              alt="" 
              className="w-full h-full object-cover object-top opacity-30"
            />
          )}
           <div className="absolute inset-0 bg-gradient-to-t from-gray-800 via-gray-800/80 to-transparent"></div>
        </div>
        
        <div className="p-8 pt-0 -mt-24 relative z-0">
          <h2 className="text-3xl font-bold mb-2 text-yellow-400">{movie.title} ({movie.release_year})</h2>
          <p className="text-gray-400 mb-4">{movie.genres ? movie.genres.split('|').join(', ') : ''}</p>
          <p className="text-gray-300 mb-6">{movie.description || "No description available."}</p>
          
          <div className="bg-gray-700/50 p-4 rounded-lg">
            <h3 className="text-xl font-semibold mb-3">
              {existingRating > 0 ? "Update your rating" : "Rate this movie"}
            </h3>
            <StarRating initialRating={existingRating} onSetRating={onRate} />
          </div>
        </div>
      </div>
    </div>
  );
}

function StarRating({ initialRating = 0, onSetRating }) {
  const [rating, setRating] = useState(initialRating);
  const [hoverRating, setHoverRating] = useState(0);

  const handleRate = (rate) => {
    setRating(rate);
    onSetRating(rate);
  };
  
  // When the modal opens, the initialRating prop might change.
  // This useEffect ensures the stars update if the prop changes.
  useEffect(() => {
    setRating(initialRating);
  }, [initialRating]);

  return (
    <div className="flex items-center space-x-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button" // Add type="button" to prevent form submission if it's in a form
          className="bg-transparent border-none p-0 cursor-pointer"
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

