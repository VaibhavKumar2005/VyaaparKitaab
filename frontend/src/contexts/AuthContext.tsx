import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { apiFetch } from '../lib/api';
import { getAccessToken, setAccessToken, clearAccessToken } from '../lib/tokenStore';

type AuthUser = {
  email: string;
  role: 'STORE_OWNER' | 'CUSTOMER' | 'STAFF';
};

type AuthResponse = {
  access_token: string;
  token_type: string;
};

type AuthContextValue = {
  token: string | null;
  user: AuthUser | null;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: { email: string; password: string; full_name?: string; phone?: string }) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function decodeToken(token: string): AuthUser | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1] ?? '')) as { sub?: string; role?: string };
    if (!payload.sub) {
      return null;
    }
    return {
      email: payload.sub,
      role: (payload.role as AuthUser['role']) ?? 'STORE_OWNER',
    };
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [tokenState, setTokenState] = useState<string | null>(getAccessToken());
  const [user, setUser] = useState<AuthUser | null>(tokenState ? decodeToken(tokenState) : null);

  useEffect(() => {
    setAccessTokenInState(tokenState);
    setUser(tokenState ? decodeToken(tokenState) : null);
  }, [tokenState]);

  function setAccessTokenInState(t: string | null) {
    setAccessToken(t);
    setTokenState(t);
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      token: tokenState,
      user,
      login: async (email, password) => {
        const response = await apiFetch<AuthResponse>('/auth/login', {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        });
        setAccessTokenInState(response.access_token);
      },
      register: async (payload) => {
        const response = await apiFetch<AuthResponse>('/auth/register', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        setAccessTokenInState(response.access_token);
      },
      logout: () => {
        // clear local token; call backend to revoke cookie asynchronously
        clearAccessToken();
        setTokenState(null);
        fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'include' }).catch(() => {});
      },
    }),
    [tokenState, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}