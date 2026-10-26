"use client";

import { ReactNode, Component, ErrorInfo } from "react";

interface State {
  hasError: boolean;
  error?: Error;
}

/**
 * Catches rendering errors in any child subtree and shows a fallback.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 48, textAlign: "center", color: "#ef4444" }}>
          <h2>Something went wrong</h2>
          <p style={{ color: "#94a3b8" }}>{this.state.error?.message}</p>
          <button
            onClick={() => window.location.reload()}
            style={{
              marginTop: 16,
              padding: "10px 16px",
              borderRadius: 8,
              border: "1px solid #334155",
              background: "#1e293b",
              color: "#fff",
              cursor: "pointer",
            }}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
