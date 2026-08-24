import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Layout from './components/Layout';
import Home from './pages/Home';
import Analysis from './pages/Analysis';
import History from './pages/History';
import Settings from './pages/Settings';
import Login from './pages/Login';

/**
 * Guards a route behind authentication.
 * Unauthenticated users are redirected to /login with a `from` state
 * so they bounce back after signing in.
 */
function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Login lives outside Layout (full-page) */}
          <Route path="/login" element={<Login />} />

          {/* All other routes share the sidebar Layout */}
          <Route
            path="/*"
            element={
              <Layout>
                <Routes>
                  <Route path="/" element={<Home />} />
                  <Route path="/analysis" element={<Analysis />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route
                    path="/history"
                    element={
                      <ProtectedRoute>
                        <History />
                      </ProtectedRoute>
                    }
                  />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Layout>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
