"use client";

import { ReactNode, useEffect, useState } from "react";
import { isAuthenticated } from "../lib/auth";

/**
 * Wraps protected content. When auth is required but the user is not
 * authenticated, shows a login prompt instead of children.
 *
 * In dev mode (no OIDC configured), this is effectively a no-op.
 */
export function AuthGuard({ children }: { children: ReactNode }) {
  const [authed, setAuthed] = useState(true);

  useEffect(() => {
    // In production with AUTH_REQUIRED=true, the backend will reject requests
    // without a token; the api wrapper redirects on 401. Here we simply gate
    // the initial render for a smoother UX.
    setAuthed(isAuthenticated());
  }, []);

  if (!authed && process.env.NODE_ENV === "production") {
    return (
      <div style={{ padding: 48, textAlign: "center", color: "#94a3b8" }}>
        <h2>Authentication required</h2>
        <p>Please sign in to access Cortex Autopilot</p>
     </div>
    );
  }

  return <>{children</>;
}
