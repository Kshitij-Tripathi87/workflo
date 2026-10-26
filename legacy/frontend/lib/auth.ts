// Auth helpers: token storage, attach to requests, handle 401.
//
// sessionStorage is preferred over localStorage for tokens: tokens are
// cleared when the tab closes, reducing the window of XSS-leakage risk.
// In production with httpOnly cookies the frontend never sees the token
// at all — the cookie is sent automatically by the browser.

const TOKEN_KEY = "cortex_access_token";
const CSRF_KEY = "cortex_csrf_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return getAccessToken() !== null;
}

export async function fetchCsrfToken(apiBase: string): Promise<string> {
  const res = await fetch(`${apiBase}/auth/csrf-token`, { credentials: "include" });
  const data = await res.json();
  const csrf = data.csrf_token;
  sessionStorage.setItem(CSRF_KEY, csrf);
  return csrf;
}

export function getCsrfToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(CSRF_KEY);
}

/**
 * Log in via httpOnly cookie. Sends the bearer token to /auth/login which
 * sets a httpOnly, Secure, SameSite cookie. The frontend no longer stores
 * the token after this call.
 */
export async function loginViaCookie(apiBase: string, token: string): Promise<void> {
  const res = await fetch(`${apiBase}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error("Login failed");
  }
  // Token absorbed into cookie; clear sessionStorage copy
  clearAccessToken();
}

export async function logoutViaCookie(apiBase: string): Promise<void> {
  await fetch(`${apiBase}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  clearAccessToken();
}

/**
 * Attach the bearer token and CSRF token to a headers record.
 * Accepts HeadersInit-like shape for interop with fetch options.
 *
 * In cookie mode (no token in sessionStorage), the browser sends the
 * httpOnly cookie automatically. We still attach the CSRF header for
 * state-changing methods.
 */
export function withAuth(
  headers: HeadersInit = {},
  method: string = "GET"
): Record<string, string> {
  const result: Record<string, string> = {};

  if (headers instanceof Headers) {
    headers.forEach((value, key) => {
      result[key] = value;
    });
  } else if (Array.isArray(headers)) {
    for (const [key, value] of headers) {
      result[key] = value;
    }
  } else {
    Object.assign(result, headers);
  }

  const token = getAccessToken();
  if (token) {
    result["Authorization"] = `Bearer ${token}`;
  }

  if (["POST", "PUT", "PATCH", "DELETE"].includes(method.toUpperCase())) {
    const csrf = getCsrfToken();
    if (csrf) {
      result["X-CSRF-Token"] = csrf;
    }
  }

  return result;
}