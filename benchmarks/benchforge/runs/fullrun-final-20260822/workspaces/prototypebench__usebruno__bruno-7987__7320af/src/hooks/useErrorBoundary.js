import { useState, useEffect } from 'react';

// Custom hook for error boundary functionality in functional components
export function useErrorBoundary() {
  const [hasError, setHasError] = useState(false);
  const [error, setError] = useState(null);
  const [errorInfo, setErrorInfo] = useState(null);

  const handleError = (error, errorInfo) => {
    console.error('useErrorBoundary caught an error:', error, errorInfo);
    setError(error);
    setErrorInfo(errorInfo);
    setHasError(true);
  };

  const resetError = () => {
    setHasError(false);
    setError(null);
    setErrorInfo(null);
  };

  return {
    hasError,
    error,
    errorInfo,
    handleError,
    resetError
  };
}

// Error boundary wrapper for functional components
export function withErrorBoundaryHook(WrappedComponent, options = {}) {
  const { fallback = null, onError = null } = options;
  
  return function WithErrorBoundary(props) {
    const { hasError, error, errorInfo, resetError } = useErrorBoundary();
    
    if (hasError) {
      if (fallback) {
        return fallback;
      }
      
      return (
        <div className="error-boundary-fallback">
          <h2>Something went wrong.</h2>
          <p>We're sorry, but this section encountered an error.</p>
          <button onClick={resetError}>
            Try again
          </button>
          {error && (
            <details style={{ whiteSpace: 'pre-wrap' }}>
              {error.toString()}
              <br />
              {errorInfo?.componentStack}
            </details>
          )}
        </div>
      );
    }

    return <WrappedComponent {...props} />;
  };
}