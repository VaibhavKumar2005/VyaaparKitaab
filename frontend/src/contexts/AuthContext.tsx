import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { apiFetch } from '../lib/api';
import { getAccessToken, setAccessToken, clearAccessToken } from '../lib/tokenStore';
import { isDemoMode, setDemoMode } from '../mock/mockStore';

type AuthUser = {
  email: string;
  role: 'STORE_OWNER' | 'CUSTOMER' | 'STAFF';
};

type AuthResponse = {
  access_token: string;
  token_type: string;
};

type RegisterPayload = {
  email: string;
  password: string;
  full_name?: string;
  phone?: string;
  role?: 'STORE_OWNER' | 'CUSTOMER';
  business_name?: string;
  gstin?: string;
  address?: string;
};

type AuthContextValue = {
  token: string | null;
  user: AuthUser | null;
  isDemo: boolean;
  login: (email: string, password: string) => Promise<void>;
  customerOtpLogin: (phone: string, otp: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => void;
  enableDemo: () => void;
  enableCustomerDemo: () => void;
  disableDemo: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const DEMO_STORE_OWNER: AuthUser = {
  email: 'ramesh.sharma@sharmakirana.in',
  role: 'STORE_OWNER',
};

const DEMO_CUSTOMER: AuthUser = {
  email: 'ramesh.kumar@gmail.com',
  role: 'CUSTOMER',
};

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
  const [demoActive, setDemoActive] = useState<boolean>(() => isDemoMode());
  const [user, setUser] = useState<AuthUser | null>(() => {
    if (tokenState) return decodeToken(tokenState);
    if (demoActive) return DEMO_STORE_OWNER;
    return null;
  });

  useEffect(() => {
    const handleDemoChange = () => {
      const active = isDemoMode();
      setDemoActive(active);
      if (!tokenState) {
        setUser((prev) => (active ? (prev?.role === 'CUSTOMER' ? DEMO_CUSTOMER : DEMO_STORE_OWNER) : null));
      }
    };
    window.addEventListener('vyaapar_demo_mode_changed', handleDemoChange);
    return () => window.removeEventListener('vyaapar_demo_mode_changed', handleDemoChange);
  }, [tokenState]);

  useEffect(() => {
    setAccessToken(tokenState);
    if (tokenState) {
      setUser(decodeToken(tokenState));
    } else if (demoActive) {
      setUser((prev) => (prev?.role === 'CUSTOMER' ? DEMO_CUSTOMER : DEMO_STORE_OWNER));
    } else {
      setUser(null);
    }
  }, [tokenState, demoActive]);

  function setAccessTokenInState(t: string | null) {
    setAccessToken(t);
    setTokenState(t);
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      token: tokenState,
      user,
      isDemo: demoActive,
      login: async (email, password) => {
        const response = await apiFetch<AuthResponse>('/auth/login', {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        });
        setAccessTokenInState(response.access_token);
        setDemoMode(false);
      },
      customerOtpLogin: async (phone, otp) => {
        try {
          const response = await apiFetch<AuthResponse>('/auth/customer/otp-login', {
            method: 'POST',
            body: JSON.stringify({ phone, otp }),
          });
          setAccessTokenInState(response.access_token);
          setDemoMode(false);
        } catch {
          // Fallback to customer demo if backend is offline
          setDemoMode(true);
          setDemoActive(true);
          setUser(DEMO_CUSTOMER);
        }
      },
      register: async (payload) => {
        const { business_name, gstin, address, ...authPayload } = payload;
        const response = await apiFetch<AuthResponse>('/auth/register', {
          method: 'POST',
          body: JSON.stringify(authPayload),
        });
        setAccessTokenInState(response.access_token);
        setDemoMode(false);
        if (business_name && (payload.role ?? 'STORE_OWNER') === 'STORE_OWNER') {
          try {
            await apiFetch('/businesses', {
              method: 'POST',
              body: JSON.stringify({
                name: business_name,
                gstin: gstin || null,
                address: address || null,
                phone: payload.phone || null,
              }),
            });
          } catch {
            // Non-blocking if business creation fails
          }
        }
      },
      logout: () => {
        clearAccessToken();
        setTokenState(null);
        setDemoMode(false);
        fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'include' }).catch(() => {});
      },
      enableDemo: () => {
        setDemoMode(true);
        setDemoActive(true);
        setUser(DEMO_STORE_OWNER);
      },
      enableCustomerDemo: () => {
        setDemoMode(true);
        setDemoActive(true);
        setUser(DEMO_CUSTOMER);
      },
      disableDemo: () => {
        setDemoMode(false);
        setDemoActive(false);
        if (!tokenState) {
          setUser(null);
        }
      },
    }),
    [tokenState, user, demoActive],
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