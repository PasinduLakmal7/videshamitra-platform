import React from 'react';

interface State {
  error: Error | null;
}

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error): void {
    console.error('Admin portal error', error);
  }

  render(): React.ReactNode {
    if (this.state.error) {
      return (
        <div className="centered-screen">
          <div className="empty-state">
            <h1>Something went wrong</h1>
            <p>{this.state.error.message}</p>
            <button
              type="button"
              className="btn btn-primary btn-md"
              onClick={() => window.location.assign('/')}
            >
              Reload portal
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
