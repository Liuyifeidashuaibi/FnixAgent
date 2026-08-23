import React, { Component } from 'react';

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    // Update state so the next render will show the fallback UI
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    // You can also log the error to an error reporting service
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      // You can render any custom fallback UI
      return (
        <div className="error-boundary-fallback">
          <h2>Something went wrong.</h2>
          <p>We're sorry, but this section encountered an error.</p>
          <button onClick={() => this.setState({ hasError: false, error: null, errorInfo: null })}>
            Try again
          </button>
          {this.state.error && (
            <details style={{ whiteSpace: 'pre-wrap' }}>
              {this.state.error.toString()}
              <br />
              {this.state.errorInfo?.componentStack}
            </details>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}

export function withErrorBoundary(WrappedComponent, options = {}) {
  const { fallback = null, onError = null } = options;
  
  return class extends Component {
    constructor(props) {
      super(props);
      this.state = { hasError: false, error: null, errorInfo: null };
    }

    static getDerivedStateFromError(error) {
      return { hasError: true, error };
    }

    componentDidCatch(error, errorInfo) {
      if (onError) {
        onError(error, errorInfo);
      }
      console.error('withErrorBoundary caught an error:', error, errorInfo);
    }

    render() {
      if (this.state.hasError) {
        if (fallback) {
          return fallback;
        }
        return (
          <div className="error-boundary-fallback">
            <h2>Something went wrong.</h2>
            <p>We're sorry, but this section encountered an error.</p>
            <button onClick={() => this.setState({ hasError: false, error: null, errorInfo: null })}>
              Try again
            </button>
          </div>
        );
      }

      return <WrappedComponent {...this.props} />;
    }
  };
}