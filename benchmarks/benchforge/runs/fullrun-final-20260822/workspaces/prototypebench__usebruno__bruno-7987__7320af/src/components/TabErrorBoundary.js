import React, { Component } from 'react';

export class TabErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('TabErrorBoundary caught an error:', error, errorInfo);
    
    // Notify parent component about the error
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }
  }

  render() {
    if (this.state.hasError) {
      // Render fallback UI for tabs
      return (
        <div className="tab-error-boundary-fallback" style={{ padding: '16px', backgroundColor: '#fff5f5', border: '1px solid #ffebee', borderRadius: '4px' }}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: '8px' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <h3 style={{ margin: '0 0 0 8px', color: '#c62828', fontSize: '14px' }}>Tab Error</h3>
          </div>
          <p style={{ margin: '0 0 12px 0', fontSize: '13px', color: '#666' }}>
            This tab encountered an error and cannot be displayed.
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
              Reload Tab
            </button>
            {this.props.onClose && (
              <button 
                onClick={this.props.onClose}
                style={{ 
                  padding: '6px 12px', 
                  backgroundColor: '#f44336', 
                  color: 'white', 
                  border: 'none', 
                  borderRadius: '4px', 
                  cursor: 'pointer',
                  fontSize: '13px'
                }}
              >
                Close Tab
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
export default TabErrorBoundary;