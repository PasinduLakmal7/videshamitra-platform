import type { PageMeta, PageResult, Session, SessionUser } from '@/types/models';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
const SESSION_KEY = 'vm.admin.session';

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function getSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function setSession(session: Session): void {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function updateSessionTokens(tokens: Partial<Session>): void {
  const current = getSession();
  if (!current) return;
  setSession({ ...current, ...tokens });
}

export function clearSession(): void {
  sessionStorage.removeItem(SESSION_KEY);
  window.dispatchEvent(new Event('vm:session-cleared'));
}

export function getCurrentUser(): SessionUser | null {
  return getSession()?.user ?? null;
}

let refreshPromise: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    const session = getSession();
    if (!session?.refresh_token) return false;
    try {
      const response = await fetch(`${BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: session.refresh_token }),
      });
      if (!response.ok) return false;
      const body = await response.json();
      const refreshed = body.data as Session;
      setSession(refreshed);
      return true;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  formData?: FormData;
  query?: Record<string, string | number | boolean | null | undefined>;
  retry?: boolean;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === '') continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function rawRequest(path: string, options: RequestOptions = {}): Promise<Response> {
  const session = getSession();
  const headers: Record<string, string> = {};
  if (session?.access_token) headers.Authorization = `Bearer ${session.access_token}`;
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';

  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? 'GET',
    headers,
    body: options.formData ?? (options.body !== undefined ? JSON.stringify(options.body) : undefined),
  });

  if (response.status === 401 && options.retry !== false && session?.refresh_token) {
    const renewed = await refreshSession();
    if (renewed) return rawRequest(path, { ...options, retry: false });
    clearSession();
  }
  return response;
}

interface ApiEnvelope<T> {
  data?: T;
  meta?: PageMeta;
  error?: { code?: string; message?: string; details?: unknown };
}

async function parse<T>(response: Response): Promise<T> {
  const text = await response.text();
  let body: ApiEnvelope<T> | null;
  try {
    body = text ? (JSON.parse(text) as ApiEnvelope<T>) : null;
  } catch {
    body = null;
  }
  if (!response.ok) {
    const error = body?.error;
    throw new ApiError(
      response.status,
      error?.code ?? 'http_error',
      error?.message ?? `Request failed (${response.status})`,
      error?.details,
    );
  }
  return (body?.data ?? body) as T;
}

export const api = {
  async get<T>(path: string, query?: RequestOptions['query']): Promise<T> {
    return parse<T>(await rawRequest(path, { query }));
  },

  async page<T>(path: string, query?: RequestOptions['query']): Promise<PageResult<T>> {
    const response = await rawRequest(path, { query });
    const body = (await response
      .json()
      .catch(() => null)) as ApiEnvelope<T[]> | null;
    if (!response.ok) {
      throw new ApiError(
        response.status,
        body?.error?.code ?? 'http_error',
        body?.error?.message ?? `Request failed (${response.status})`,
        body?.error?.details,
      );
    }
    return { items: body?.data ?? [], meta: body?.meta as PageMeta };
  },

  async post<T>(path: string, body?: unknown): Promise<T> {
    return parse<T>(await rawRequest(path, { method: 'POST', body }));
  },

  async patch<T>(path: string, body?: unknown): Promise<T> {
    return parse<T>(await rawRequest(path, { method: 'PATCH', body }));
  },

  async delete<T>(path: string): Promise<T> {
    return parse<T>(await rawRequest(path, { method: 'DELETE' }));
  },

  async upload<T>(path: string, formData: FormData, idempotencyKey?: string): Promise<T> {
    const session = getSession();
    const response = await fetch(buildUrl(path), {
      method: 'POST',
      headers: {
        ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}),
        ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
      },
      body: formData,
    });
    return parse<T>(response);
  },
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Unexpected error';
}
