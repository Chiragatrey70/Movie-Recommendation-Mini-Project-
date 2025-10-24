import { useState, useEffect } from 'react'
import axios from 'axios'
import { Search, X, Star, Film, ThumbsUp } from 'lucide-react'

// Define the backend API URL
const API_URL = "http://127.0.0.1:8000"

// --- Main App Component ---
export default function App() {
  const [movies, setMovies] = useState([])
  const [recommendations, setRecommendations] = useState([])
  const [searchTerm, setSearchTerm] = useState("")
  const [selectedMovie, setSelectedMovie] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  
  // Our "test user". In a real app, this would come from login.
  const USER_ID = 1 

  // Fetch initial data (all movies and recommendations) on load
  useEffect(() => {
    const fetchInitialData = async () => {
      setIsLoading(true)
      setError(null)
      try {
        // Fetch all movies
        const moviesResponse = await axios.get(`${API_URL}/movies/`)
        setMovies(moviesResponse.data)
        
        // Fetch recommendations for our test user
        const recsResponse = await axios.get(`${API_URL}/recommendations/${USER_ID}`)
        setRecommendations(recsResponse.data)
        
      } catch (err) {
        console.error("Error fetching data:", err)
        setError("Could not connect to the movie server. Is it running?")
      }
      setIsLoading(false)
    }
    
    fetchInitialData()
  }, [])

  // Handle search logic
  const handleSearch = async (e) => {
    e.preventDefault()
    if (!searchTerm) {
      // If search is cleared, fetch all movies again
      const moviesResponse = await axios.get(`${API_URL}/movies/`)
      setMovies(moviesResponse.data)
      return
    }
    
    try {
      // Fetch movies matching the search term
      const response = await axios.get(`${API_URL}/movies/`, {
        params: { search: searchTerm }
      })
      setMovies(response.data)
    } catch (err) {
      console.error("Error searching movies:", err)
      setError("Error searching for movies.")
    }
  }

  // Handle rating a movie
  const handleRateMovie = async (movieId, score) => {
    try {
      await axios.post(`${API_URL}/ratings/`, {
        user_id: USER_ID,
        movie_id: movieId,
        score: score
      })
      
      // After rating, refresh recommendations
      const recsResponse = await axios.get(`${API_URL}/recommendations/${USER_ID}`)
      setRecommendations(recsResponse.data)
      
      // Close modal and show alert
      setSelectedMovie(null) // Close the modal on successful rating
      alert(`You rated this movie ${score} stars! Recommendations updated.`)

    } catch (err) {
      console.error("Error rating movie:", err)
      setError("Could not submit rating.")
    }
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white font-sans">
      {/* --- Header & Search Bar --- */}
      <header className="bg-gray-800 shadow-lg p-4 sticky top-0 z-10">
        <div className="container mx-auto max-w-6xl flex justify-between items-center">
          <div className="flex items-center space-x-2">
            <Film className="text-yellow-400" size={32} />
            <h1 className="text-2xl font-bold text-white">MovieRec</h1>
          </div>
          <form onSubmit={handleSearch} className="flex-1 max-w-md">
            <div className="relative">
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search for movies..."
                className="w-full bg-gray-700 text-white rounded-full py-2 px-4 focus:outline-none focus:ring-2 focus:ring-yellow-400"
              />
              <button type="submit" className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-yellow-400">
                <Search size={20} />
              </button>
            </div>
          </form>
        </div>
      </header>

      {/* --- Main Content --- */}
      <main className="container mx-auto max-w-6xl p-4 mt-8">
        {isLoading && <LoadingSpinner />}
        {error && <ErrorMessage message={error} />}
        
        {!isLoading && !error && (
          <>
            {/* --- BUG FIX #1: SEARCH RESULTS ---
              We only show the "Recommended" section if there is NO active search term.
              This pushes the "Search Results" section to the top.
            */}
            {!searchTerm && (
              <MovieSection 
                title="Recommended For You" 
                icon={<ThumbsUp className="text-yellow-400" />}
                movies={recommendations} 
                onMovieClick={setSelectedMovie} 
              />
            )}
            
            {/* --- Browse All Movies / Search Results Section --- */}
            <MovieSection 
              title={searchTerm ? "Search Results" : "Browse All Movies"}
              icon={<Film className="text-yellow-400" />}
              movies={movies} 
              onMovieClick={setSelectedMovie} 
            />
          </>
        )}
      </main>

      {/* --- Movie Details Modal --- */}
      {selectedMovie && (
        <MovieModal 
          movie={selectedMovie} 
          onClose={() => setSelectedMovie(null)} 
          onRate={handleRateMovie}
        />
      )}
    </div>
  )
}

// --- Child Components ---

/**
 * A reusable component to display a horizontal list of movies
 */
function MovieSection({ title, icon, movies, onMovieClick }) {
  if (movies.length === 0) {
    return (
      <section className="mb-12">
        <h2 className="text-3xl font-bold mb-6 flex items-center space-x-3">
          {icon}
          <span>{title}</span>
        </h2>
        <p className="text-gray-400">No movies to display in this section.</p>
      </section>
    )
  }

  return (
    <section className="mb-12">
      <h2 className="text-3xl font-bold mb-6 flex items-center space-x-3">
        {icon}
        <span>{title}</span>
      </h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-6">
        {movies.map(movie => (
          <MovieCard key={movie.id} movie={movie} onClick={() => onMovieClick(movie)} />
        ))}
      </div>
    </section>
  )
}

/**
 * A card for a single movie
 */
function MovieCard({ movie, onClick }) {
  // Simple placeholder image logic
  const placeholderUrl = `https://placehold.co/500x750/1a202c/FFFF00?text=${encodeURIComponent(movie.title)}`
  
  return (
    <div 
      className="bg-gray-800 rounded-lg shadow-lg overflow-hidden cursor-pointer transform transition-transform duration-300 hover:scale-105 hover:shadow-yellow-400/20"
      onClick={onClick}
    >
      <img 
        src={placeholderUrl} 
        alt={movie.title} 
        className="w-full h-auto object-cover" 
        onError={(e) => e.target.src = 'https://placehold.co/500x750/1a202c/FFFF00?text=Image+Not+Found'}
      />
      <div className="p-4">
        <h3 className="font-bold text-lg truncate" title={movie.title}>{movie.title}</h3>
        <p className="text-gray-400 text-sm">{movie.release_year}</p>
      </div>
    </div>
  )
}

/**
 * A modal to show movie details and allow rating
 */
function MovieModal({ movie, onClose, onRate }) {
  const placeholderUrl = `https://placehold.co/400x600/1a202c/FFFF00?text=${encodeURIComponent(movie.title)}`

  return (
    <div 
      className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div 
        className="bg-gray-800 rounded-lg shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto flex flex-col md:flex-row"
        onClick={(e) => e.stopPropagation()} // Prevent modal from closing when clicking inside
      >
        {/* --- Close Button --- */}
        <button 
          onClick={onClose} 
          className="absolute top-4 right-4 text-gray-400 hover:text-white z-10"
        >
          <X size={28} />
        </button>
        
        {/* --- Movie Poster --- */}
        <img 
          src={placeholderUrl} 
          alt={movie.title} 
          className="w-full md:w-1/3 h-auto object-cover rounded-l-lg"
          onError={(e) => e.target.src = 'https://placehold.co/400x600/1a202c/FFFF00?text=Image+Not+Found'}
        />
        
        {/* --- Movie Details --- */}
        <div className="p-8 flex-1">
          <h2 className="text-4xl font-bold mb-2">{movie.title} ({movie.release_year})</h2>
          <p className="text-lg text-gray-400 mb-4">{movie.genres.split(',').join(', ')}</p>
          <p className="text-gray-300 mb-6">{movie.description}</p>
          
          <div className="border-t border-gray-700 pt-6">
            <h3 className="text-2xl font-semibold mb-4">Rate this movie</h3>
            {/* --- BUG FIX #2: STAR RATING ---
              We pass the onRate function to the improved StarRating component.
            */}
            <StarRating onRate={onRate} />
          </div>
        </div>
      </div>
    </div>
  )
}

/**
 * --- BUG FIX #2: STAR RATING (Component Logic) ---
 * This component now uses internal state (`hoverRating`) to track
 * the hover effect, lighting up all stars up to the one you're hovering over.
 */
function StarRating({ onRate }) {
  const [hoverRating, setHoverRating] = useState(0); // State for hover

  return (
    <div 
      className="flex space-x-2" 
      onMouseLeave={() => setHoverRating(0)} // Reset hover when mouse leaves the group
    >
      {[1, 2, 3, 4, 5].map(starValue => (
        <button 
          key={starValue}
          onClick={() => onRate(starValue)}
          onMouseEnter={() => setHoverRating(starValue)} // Set hover state
          className="transition-colors"
          title={`Rate ${starValue} stars`}
        >
          <Star 
            size={32} 
            className={
              starValue <= hoverRating 
                ? "text-yellow-400 fill-yellow-400" // Lit star (filled)
                : "text-gray-500"                   // Unlit star (outline)
            } 
          />
        </button>
      ))}
    </div>
  )
}

/**
 * Loading spinner
 */
function LoadingSpinner() {
  return (
    <div className="flex justify-center items-center h-64">
      <div className="animate-spin rounded-full h-32 w-32 border-t-4 border-b-4 border-yellow-400"></div>
    </div>
  )
}

/**
 * Error message display
 */
function ErrorMessage({ message }) {
  return (
    <div className="bg-red-900 border border-red-700 text-red-100 px-4 py-3 rounded-lg text-center">
      <strong className="font-bold">Error: </strong>
      <span className="block sm:inline">{message}</span>
    </div>
  )
}

