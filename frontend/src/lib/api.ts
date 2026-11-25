import { getAccessToken, setAccessToken } from './tokenStore';

const API_BASE = import.meta.env.VITE_API_URL
  ? String(import.meta.env.VITE_API_URL).replace(/\/$/, '')
  : '';

async function readApiErrorMessage(response: Response): Promise<string> {
  const raw = await response.text().catch(() => '');
  const trimmed = raw.trim();
  if (!trimmed) {
    return `Request failed (HTTP ${response.status})`;
  }
  try {
    const parsed = JSON.parse(trimmed) as {
      detail?: string | Array<{ msg?: string; loc?: Array<string | number> }>;
      message?: string;
      error?: string;
    };
    if (typeof parsed.detail === 'string' && parsed.detail.trim()) {
      return parsed.detail.trim();
    }
    if (Array.isArray(parsed.detail) && parsed.detail.length > 0) {
      const msgs = parsed.detail
        .map((item) => {
          const field = Array.isArray(item.loc) ? item.loc.slice(-1)[0] : '';
          return field ? `${field}: ${item.msg ?? 'invalid value'}` : (item.msg ?? 'Invalid input');
        })
        .filter(Boolean);
      if (msgs.length > 0) return msgs.join('; ');
    }
    if (typeof parsed.message === 'string' && parsed.message.trim()) {
      return parsed.message.trim();
    }
    if (typeof parsed.error === 'string' && parsed.error.trim()) {
      return parsed.error.trim();
    }
  } catch {
    // Response was not JSON; fall through to raw text
  }
  return trimmed;
}

async function tryRefresh(): Promise<string | null> {
  try {
    const resp = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    if (data?.access_token) {
      setAccessToken(data.access_token);
      return data.access_token;
    }
  } catch {
    return null;
  }
  return null;
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAccessToken();
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}/api/v1${path}`, {
    ...options,
    headers,
    credentials: options.credentials ?? 'same-origin',
  });

  if (response.status === 401) {
    const newToken = await tryRefresh();
    if (newToken) {
      const retryHeaders = { ...headers, Authorization: `Bearer ${newToken}` };
      const retry = await fetch(`${API_BASE}/api/v1${path}`, {
        ...options,
        headers: retryHeaders,
        credentials: options.credentials ?? 'same-origin',
      });
      if (!retry.ok) throw new Error(await readApiErrorMessage(retry));
      return retry.json() as Promise<T>;
    }
    throw new Error('Unauthorized');
  }

  if (!response.ok) {
    throw new Error(await readApiErrorMessage(response));
  }

  return response.json() as Promise<T>;
}
