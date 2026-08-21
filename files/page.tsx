"use client";

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";

type Step = "login" | "confirm" | "done" | "error";

export default function DevicePage() {
  const params = useSearchParams();
  const prefilledCode = params.get("user_code") ?? "";

  const [step, setStep] = useState<Step>("login");
  const [code, setCode] = useState(prefilledCode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (prefilledCode) setCode(prefilledCode);
  }, [prefilledCode]);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const res = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      setError("Incorrect email or password.");
      return;
    }
    setStep("confirm");
  }

  async function handleApprove() {
    setError("");
    const res = await fetch("/api/auth/device/verify", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_code: code }),
    });
    if (!res.ok) {
      setStep("error");
      return;
    }
    setStep("done");
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center px-6 py-16">
      <p className="mb-2 font-mono text-xs text-muted">Cortex / Device Login</p>

      {step === "login" && (
        <>
          <h1 className="mb-6 text-xl text-ink">Sign in to authorize this device</h1>
          <form onSubmit={handleLogin} className="space-y-4">
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
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded border border-hairline px-3 py-2 text-sm text-ink outline-none focus:border-accent"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-muted">Device code</label>
              <input
                type="text"
                required
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="XXXX-XXXX"
                className="w-full rounded border border-hairline px-3 py-2 font-mono text-sm text-ink outline-none focus:border-accent"
              />
              <p className="mt-1 text-xs text-muted">
                Shown in your terminal after running <code>workflo auth login</code>.
              </p>
            </div>
            {error && <p className="text-sm text-danger">{error}</p>}
            <button
              type="submit"
              className="w-full rounded bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/90"
            >
              Continue
            </button>
          </form>
          <p className="mt-6 text-sm text-muted">
            No account? <a href="/signup" className="text-accent no-underline">Sign up</a>
          </p>
        </>
      )}

      {step === "confirm" && (
        <>
          <h1 className="mb-3 text-xl text-ink">Authorize this device?</h1>
          <p className="mb-6 text-sm text-muted">
            Code <span className="font-mono text-ink">{code}</span> will be granted access to run
            Workflo on your behalf from this device.
          </p>
          {error && <p className="mb-4 text-sm text-danger">{error}</p>}
          <div className="flex gap-3">
            <button
              onClick={handleApprove}
              className="flex-1 rounded bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/90"
            >
              Approve
            </button>
            <button
              onClick={() => setStep("login")}
              className="flex-1 rounded border border-hairline px-4 py-2 text-sm text-ink hover:border-ink"
            >
              Cancel
            </button>
          </div>
        </>
      )}

      {step === "done" && (
        <>
          <h1 className="mb-3 text-xl text-ink">Device authorized</h1>
          <p className="text-sm text-muted">
            You can close this window and return to your terminal.
          </p>
        </>
      )}

      {step === "error" && (
        <>
          <h1 className="mb-3 text-xl text-ink">Something went wrong</h1>
          <p className="text-sm text-muted">
            This code may have expired. Run <code>workflo auth login</code> again.
          </p>
        </>
      )}
    </div>
  );
}
