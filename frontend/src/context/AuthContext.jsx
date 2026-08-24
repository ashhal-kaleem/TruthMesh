import React, { createContext, useContext, useState, useCallback } from 'react';
import { getUser, getToken, clearSession } from '../auth';

const AuthContext = createContext(null);

/**
 * Wraps the app so any component can read auth state without prop-drilling.
 * State is seeded from localStorage on first render, then kept in React state
 * so consumers re-render on login / logout without a page reload.
 */
export function AuthProvider({ children }) {
  const [user,  setUser]  = useState(() => getUser());
  const [token, setToken] = useState(() => getToken());

  /** Call after a successful authLogin / authRegister response. */
  const login = useCallback((newToken, newUser) => {
    setToken(newToken);
    setUser(newUser);
  }, []);

  /** Clears localStorage and resets React state. */
  const logout = useCallback(() => {
    clearSession();
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated: !!token, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
};
