import React, { Component } from 'react';

export class CollectionErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('CollectionErrorBoundary caught an error:', error, errorInfo);
    
    // Notify parent component about the error
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }
  }

  render() {
    if (this.state.hasError) {
      // Render fallback UI for collections
      return (
        <div className="collection-error-boundary-fallback" style={{ padding: '16px', backgroundColor: '#fff8e1', border: '1px solid #ffecb3', borderRadius: '4px' }}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: '8px' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 12h.01M12 21h.01M12 3h.01M12 12h.01M12 21h.01M12 3h.01M12 12h.01M12 21h.01M12 3h.01" />
            </svg>
            <h3 style={{ margin: '0 0 0 8px', color: '#ff6f00', fontSize: '14px' }}>Collection Error</h3>
          </div>
          <p style={{ margin: '0 0 12px 0', fontSize: '13px', color: '#666' }}>
            This collection encountered an error and cannot be displayed.
          </p>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button 
              onClick={() => this.setState({ hasError: false, error: null, errorInfo: null })}
              style={{ 
                padding: '6px 12px', 
                backgroundColor: '#4caf50', 
                color: 'white', 
                border: 'none', 
                borderRadius: '4px', 
                cursor: 'pointer',
                fontSize: '13px'
              }}
            >
              Reload Collection
            </button>
            {this.props.onRetry && (
              <button 
                onClick={this.props.onRetry}
                style={{ 
                  padding: '6px 12px', 
                  backgroundColor: '#2196f3', 
                  color: 'white', 
                  border: 'none', 
                  borderRadius: '4px', 
                  cursor: 'pointer',
                  fontSize: '13px'
                }}
              >
                Try Again
              </button>
            )}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

// Export as default for easy import
export default CollectionErrorBoundary;