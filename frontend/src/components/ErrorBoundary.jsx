import React from 'react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Astrograph UI Error caught by boundary:', error, errorInfo);
  }

  handleReload = () => {
    window.location.reload();
  };

  handleReset = () => {
    try {
      localStorage.clear();
      sessionStorage.clear();
    } catch {}
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            minHeight: '100vh',
            backgroundColor: '#020308',
            color: '#FFF7ED',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '2rem',
            fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
            textAlign: 'center',
          }}
        >
          <div
            style={{
              maxWidth: '560px',
              width: '100%',
              backgroundColor: 'rgba(13, 20, 36, 0.85)',
              border: '1px solid rgba(251, 146, 60, 0.3)',
              borderRadius: '16px',
              padding: '2rem',
              boxShadow: '0 20px 40px rgba(0, 0, 0, 0.6), 0 0 40px rgba(251, 146, 60, 0.1)',
            }}
          >
            <div style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>🪐</div>
            <h1
              style={{
                fontSize: '1.4rem',
                fontWeight: 700,
                color: '#FED7AA',
                marginBottom: '0.75rem',
              }}
            >
              Celestial Signal Interrupted
            </h1>
            <p
              style={{
                fontSize: '0.9rem',
                color: '#9CA3AF',
                marginBottom: '1.5rem',
                lineHeight: 1.5,
              }}
            >
              An unexpected error occurred while loading this view.
            </p>
            {this.state.error && (
              <pre
                style={{
                  backgroundColor: 'rgba(0, 0, 0, 0.5)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  color: '#FCA5A5',
                  padding: '0.75rem 1rem',
                  borderRadius: '8px',
                  fontSize: '0.75rem',
                  fontFamily: "'JetBrains Mono', monospace",
                  textAlign: 'left',
                  overflowX: 'auto',
                  marginBottom: '1.5rem',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {this.state.error.message || String(this.state.error)}
              </pre>
            )}
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
              <button
                type="button"
                onClick={this.handleReload}
                style={{
                  backgroundColor: '#FB923C',
                  color: '#020308',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '0.65rem 1.25rem',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                }}
              >
                Reload Page
              </button>
              <button
                type="button"
                onClick={this.handleReset}
                style={{
                  backgroundColor: 'transparent',
                  color: '#FED7AA',
                  border: '1px solid rgba(251, 146, 60, 0.4)',
                  borderRadius: '8px',
                  padding: '0.65rem 1.25rem',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                }}
              >
                Reset Session & Return Home
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
