import { getAccessToken, setAccessToken } from './tokenStore';

async function tryRefresh(): Promise<string | null> {
  try {
    const resp = await fetch('/api/v1/auth/refresh', {
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
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers,
    credentials: options.credentials ?? 'same-origin',
  });

  if (response.status === 401) {
    const newToken = await tryRefresh();
    if (newToken) {
      // retry original request once
      const retryHeaders = { ...headers, Authorization: `Bearer ${newToken}` };
      const retry = await fetch(`/api/v1${path}`, {
        ...options,
        headers: retryHeaders,
        credentials: options.credentials ?? 'same-origin',
      });
      if (!retry.ok) throw new Error(await retry.text());
      return retry.json() as Promise<T>;
    }
    throw new Error('Unauthorized');
  }

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json() as Promise<T>;
}