"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 12) {
      setError("Password must be at least 12 characters.");
      return;
    }
    const res = await fetch("/api/auth/signup", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setError(body.detail ?? "Could not create account.");
      return;
    }
    router.push("/device");
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center px-6 py-16">
      <p className="mb-2 font-mono text-xs text-muted">Cortex</p>
      <h1 className="mb-6 text-xl text-ink">Create your account</h1>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-sm text-muted">Email</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded border border-hairline px-3 py-2 text-sm text-ink outline-none focus:border-accent"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm text-muted">Password</label>
          <input
            type="password"
            required
            minLength={12}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded border border-hairline px-3 py-2 text-sm text-ink outline-none focus:border-accent"
          />
          <p className="mt-1 text-xs text-muted">At least 12 characters.</p>
        </div>
        {error && <p className="text-sm text-danger">{error}</p>}
        <button
          type="submit"
          className="w-full rounded bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/90"
        >
          Create account
        </button>
      </form>
      <p className="mt-6 text-sm text-muted">
        Already have an account? <a href="/device" className="text-accent no-underline">Sign in</a>
      </p>
    </div>
  );
}
