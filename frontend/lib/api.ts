import { HealthResponse, IndexedFile, QueryResponse, StatsResponse } from './types';

export function getApiBase(): string {
  if (typeof window !== 'undefined') {
    const custom = localStorage.getItem('brain_api_url');
    if (custom && custom.trim()) {
      return custom.trim().replace(/\/+$/, '');
    }
  }
  let base = (process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
  if (base && !base.startsWith('http://') && !base.startsWith('https://')) {
    base = `https://${base}`;
  }
  return base;
}

export class ApiError extends Error {
  status: number;
  isNetworkError: boolean;

  constructor(message: string, status: number = 0, isNetworkError: boolean = false) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.isNetworkError = isNetworkError;
  }
}

export function getStoredToken(): string | null {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('brain_auth_token');
  }
  return null;
}

export function setStoredToken(token: string): void {
  if (typeof window !== 'undefined') {
    localStorage.setItem('brain_auth_token', token);
  }
}

export function clearStoredToken(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('brain_auth_token');
    window.dispatchEvent(new CustomEvent('brain-unauthorized'));
  }
}

function getAuthHeaders(includeContentType: boolean = false): Record<string, string> {
  const headers: Record<string, string> = {
    'Accept': 'application/json',
  };
  if (includeContentType) {
    headers['Content-Type'] = 'application/json';
  }
  const token = getStoredToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

function handleAuthResponse(res: Response): void {
  if (res.status === 401) {
    clearStoredToken();
  }
}

// --- Authentication Functions ---

export async function checkAuthStatus(): Promise<{ auth_enabled: boolean; authenticated: boolean }> {
  const apiBase = getApiBase();
  try {
    const res = await fetch(`${apiBase}/auth/status`, {
      method: 'GET',
      headers: getAuthHeaders(),
      cache: 'no-store',
    });
    if (!res.ok) {
      return { auth_enabled: false, authenticated: true };
    }
    return await res.json();
  } catch {
    return { auth_enabled: false, authenticated: true };
  }
}

export async function login(password: string): Promise<{ token: string; expires_at: number }> {
  const apiBase = getApiBase();
  try {
    const res = await fetch(`${apiBase}/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({ password }),
    });

    if (!res.ok) {
      if (res.status === 401) {
        throw new ApiError('Incorrect password. Access denied.', 401);
      }
      if (res.status === 429) {
        const body = await res.json().catch(() => null);
        throw new ApiError(body?.detail || 'Too many failed login attempts. Please wait 60 seconds.', 429);
      }
      throw new ApiError(`Login failed: ${res.statusText}`, res.status);
    }

    const data = await res.json();
    if (data.token) {
      setStoredToken(data.token);
    }
    return data;
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(`Cannot connect to backend at ${apiBase}`, 0, true);
  }
}

export function logout(): void {
  clearStoredToken();
}

// --- Data Endpoints ---

export async function checkHealth(): Promise<HealthResponse> {
  const apiBase = getApiBase();
  try {
    const res = await fetch(`${apiBase}/health`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      cache: 'no-store',
    });
    if (!res.ok) {
      throw new ApiError(`Health check failed: ${res.statusText}`, res.status);
    }
    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(`Cannot connect to backend server at ${apiBase}`, 0, true);
  }
}

export async function fetchStats(): Promise<StatsResponse> {
  const apiBase = getApiBase();
  try {
    const res = await fetch(`${apiBase}/stats`, {
      method: 'GET',
      headers: getAuthHeaders(),
      cache: 'no-store',
    });
    handleAuthResponse(res);
    if (!res.ok) {
      throw new ApiError(`Failed to fetch stats: ${res.statusText}`, res.status);
    }
    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(`Cannot connect to backend server at ${apiBase}`, 0, true);
  }
}

export async function fetchFiles(): Promise<IndexedFile[]> {
  const apiBase = getApiBase();
  try {
    const res = await fetch(`${apiBase}/files`, {
      method: 'GET',
      headers: getAuthHeaders(),
      cache: 'no-store',
    });
    handleAuthResponse(res);
    if (!res.ok) {
      throw new ApiError(`Failed to fetch indexed files: ${res.statusText}`, res.status);
    }
    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(`Cannot connect to backend server at ${apiBase}`, 0, true);
  }
}

export async function postQuery(
  question: string,
  top_k?: number,
  min_score?: number,
  provider: 'local' | 'cloud' = 'local',
  session_id?: string
): Promise<QueryResponse> {
  const apiBase = getApiBase();
  try {
    const res = await fetch(`${apiBase}/query`, {
      method: 'POST',
      headers: getAuthHeaders(true),
      body: JSON.stringify({ question, top_k, min_score, provider, session_id }),
    });

    handleAuthResponse(res);

    if (!res.ok) {
      let detail = 'Error processing query';
      try {
        const errorData = await res.json();
        detail = errorData.detail || detail;
      } catch {
        detail = res.statusText || detail;
      }

      if (res.status === 401) {
        throw new ApiError('Unauthorized: session expired or authentication required', 401);
      } else if (res.status === 400 && provider === 'cloud') {
        throw new ApiError(
          detail || 'Groq Cloud API key is not configured. Please set GROQ_API_KEY in your .env file.',
          400
        );
      } else if (res.status === 429) {
        throw new ApiError(`Groq Cloud Rate Limit: ${detail}`, 429);
      } else if (res.status === 503) {
        throw new ApiError(`LLM service unavailable: ${detail}`, 503);
      } else if (res.status === 502) {
        throw new ApiError(`LLM model error: ${detail}`, 502);
      } else {
        throw new ApiError(detail, res.status);
      }
    }

    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(`Cannot connect to backend server at ${apiBase}`, 0, true);
  }
}

export async function fetchSessions(): Promise<import('./types').SessionItem[]> {
  const apiBase = getApiBase();
  try {
    const res = await fetch(`${apiBase}/sessions`, {
      method: 'GET',
      headers: getAuthHeaders(),
      cache: 'no-store',
    });
    handleAuthResponse(res);
    if (!res.ok) {
      throw new ApiError(`Failed to fetch sessions: ${res.statusText}`, res.status);
    }
    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(`Cannot connect to backend server at ${apiBase}`, 0, true);
  }
}

export async function createSession(title?: string): Promise<import('./types').SessionItem> {
  const apiBase = getApiBase();
  try {
    const res = await fetch(`${apiBase}/sessions`, {
      method: 'POST',
      headers: getAuthHeaders(true),
      body: JSON.stringify(title ? { title } : {}),
    });
    handleAuthResponse(res);
    if (!res.ok) {
      throw new ApiError(`Failed to create session: ${res.statusText}`, res.status);
    }
    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(`Cannot connect to backend server at ${apiBase}`, 0, true);
  }
}

export async function fetchSession(sessionId: string): Promise<import('./types').SessionDetail> {
  const apiBase = getApiBase();
  try {
    const res = await fetch(`${apiBase}/sessions/${sessionId}`, {
      method: 'GET',
      headers: getAuthHeaders(),
      cache: 'no-store',
    });
    handleAuthResponse(res);
    if (!res.ok) {
      throw new ApiError(`Failed to fetch session details: ${res.statusText}`, res.status);
    }
    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(`Cannot connect to backend server at ${apiBase}`, 0, true);
  }
}

export async function renameSession(sessionId: string, title: string): Promise<void> {
  const apiBase = getApiBase();
  try {
    const res = await fetch(`${apiBase}/sessions/${sessionId}`, {
      method: 'PATCH',
      headers: getAuthHeaders(true),
      body: JSON.stringify({ title }),
    });
    handleAuthResponse(res);
    if (!res.ok) {
      throw new ApiError(`Failed to rename session: ${res.statusText}`, res.status);
    }
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(`Cannot connect to backend server at ${apiBase}`, 0, true);
  }
}

export async function deleteSession(sessionId: string): Promise<void> {
  const apiBase = getApiBase();
  try {
    const res = await fetch(`${apiBase}/sessions/${sessionId}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });
    handleAuthResponse(res);
    if (!res.ok) {
      throw new ApiError(`Failed to delete session: ${res.statusText}`, res.status);
    }
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(`Cannot connect to backend server at ${apiBase}`, 0, true);
  }
}
