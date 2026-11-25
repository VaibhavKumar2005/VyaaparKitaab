import React from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

interface State {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = { hasError: false, message: '' };

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      message: error?.message || 'An unexpected UI error occurred.',
    };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error('[VyaparKitaab UI ErrorBoundary]', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-canvas flex items-center justify-center p-6">
          <div className="w-full max-w-md rounded-xl border border-rule bg-canvas-raised p-6 text-center space-y-4 shadow-sm">
            <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-due-tint text-due">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div className="space-y-1">
              <h1 className="text-lg font-bold text-ink">Something went wrong</h1>
              <p className="text-xs text-ink-soft break-words">{this.state.message}</p>
            </div>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="inline-flex items-center gap-1.5 rounded-md bg-navy px-4 py-2 text-xs font-semibold text-white hover:bg-navy-dark"
            >
              <RotateCcw className="h-3.5 w-3.5" /> Reload Workspace
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
