import { HealthResponse, IndexedFile, QueryResponse, StatsResponse } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

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

export async function checkHealth(): Promise<HealthResponse> {
  try {
    const res = await fetch(`${API_BASE}/health`, {
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
    throw new ApiError(
      'Cannot connect to backend server at http://127.0.0.1:8000. Is FastAPI running?',
      0,
      true
    );
  }
}

export async function fetchStats(): Promise<StatsResponse> {
  try {
    const res = await fetch(`${API_BASE}/stats`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      cache: 'no-store',
    });
    if (!res.ok) {
      throw new ApiError(`Failed to fetch stats: ${res.statusText}`, res.status);
    }
    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(
      'Cannot connect to backend server at http://127.0.0.1:8000',
      0,
      true
    );
  }
}

export async function fetchFiles(): Promise<IndexedFile[]> {
  try {
    const res = await fetch(`${API_BASE}/files`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      cache: 'no-store',
    });
    if (!res.ok) {
      throw new ApiError(`Failed to fetch indexed files: ${res.statusText}`, res.status);
    }
    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(
      'Cannot connect to backend server at http://127.0.0.1:8000',
      0,
      true
    );
  }
}

export async function postQuery(
  question: string,
  top_k?: number,
  min_score?: number,
  provider: 'local' | 'cloud' = 'local',
  session_id?: string
): Promise<QueryResponse> {
  try {
    const res = await fetch(`${API_BASE}/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({ question, top_k, min_score, provider, session_id }),
    });

    if (!res.ok) {
      let detail = 'Error processing query';
      try {
        const errorData = await res.json();
        detail = errorData.detail || detail;
      } catch {
        detail = res.statusText || detail;
      }

      if (res.status === 400 && provider === 'cloud') {
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
    throw new ApiError(
      'Cannot connect to backend server at http://127.0.0.1:8000. Is FastAPI running?',
      0,
      true
    );
  }
}

export async function fetchSessions(): Promise<import('./types').SessionItem[]> {
  try {
    const res = await fetch(`${API_BASE}/sessions`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      cache: 'no-store',
    });
    if (!res.ok) {
      throw new ApiError(`Failed to fetch sessions: ${res.statusText}`, res.status);
    }
    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError('Cannot connect to backend server at http://127.0.0.1:8000', 0, true);
  }
}

export async function createSession(title?: string): Promise<import('./types').SessionItem> {
  try {
    const res = await fetch(`${API_BASE}/sessions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify(title ? { title } : {}),
    });
    if (!res.ok) {
      throw new ApiError(`Failed to create session: ${res.statusText}`, res.status);
    }
    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError('Cannot connect to backend server at http://127.0.0.1:8000', 0, true);
  }
}

export async function fetchSession(sessionId: string): Promise<import('./types').SessionDetail> {
  try {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      cache: 'no-store',
    });
    if (!res.ok) {
      throw new ApiError(`Failed to fetch session details: ${res.statusText}`, res.status);
    }
    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError('Cannot connect to backend server at http://127.0.0.1:8000', 0, true);
  }
}

export async function renameSession(sessionId: string, title: string): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) {
      throw new ApiError(`Failed to rename session: ${res.statusText}`, res.status);
    }
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError('Cannot connect to backend server at http://127.0.0.1:8000', 0, true);
  }
}

export async function deleteSession(sessionId: string): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
      method: 'DELETE',
      headers: { 'Accept': 'application/json' },
    });
    if (!res.ok) {
      throw new ApiError(`Failed to delete session: ${res.statusText}`, res.status);
    }
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError('Cannot connect to backend server at http://127.0.0.1:8000', 0, true);
  }
}


