/** API client for communicating with the Tenant Shield Control Plane. */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export interface RunSummary {
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  deselected: number;
  pass_rate_pct: number;
}

export interface TestRun {
  run_id: string;
  goal: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  started_at?: string;
  summary?: RunSummary;
}
