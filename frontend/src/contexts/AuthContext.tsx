import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { apiFetch } from '../lib/api';

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
  refreshToken: () => Promise<string | null>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);
let memoryToken: string | null = null;

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
  const [token, setToken] = useState<string | null>(memoryToken);
  const [user, setUser] = useState<AuthUser | null>(memoryToken ? decodeToken(memoryToken) : null);

  useEffect(() => {
    memoryToken = token;
    setUser(token ? decodeToken(token) : null);
  }, [token]);

  const value = useMemo<AuthContextValue>(
    () => ({
      token,
      user,
      login: async (email, password) => {
        const response = await apiFetch<AuthResponse>('/auth/login', {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        });
        setToken(response.access_token);
      },
      register: async (payload) => {
        const response = await apiFetch<AuthResponse>('/auth/register', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        setToken(response.access_token);
      },
      logout: () => setToken(null),
      refreshToken: async () => token,
    }),
    [token, user],
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