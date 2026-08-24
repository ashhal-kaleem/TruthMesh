import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ShieldCheck, Loader2, AlertCircle, Eye, EyeOff } from 'lucide-react';
import { authLogin, authRegister, ApiError } from '../api';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const navigate  = useNavigate();
  const location  = useLocation();
  const { login } = useAuth();

  const [mode,     setMode]     = useState('login');   // 'login' | 'register'
  const [username, setUsername] = useState('');
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [showPw,   setShowPw]   = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState(null);

  useEffect(() => {
    document.title = mode === 'register' ? 'Register — TruthMesh' : 'Sign In — TruthMesh';
  }, [mode]);

  // Redirect to where the user came from, or /analysis as default
  const from = location.state?.from || '/analysis';

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    if (mode === 'register') {
      if (!email.trim()) { setError('Email is required.'); return; }
      if (password.length < 8) { setError('Password must be at least 8 characters.'); return; }
    }
    setLoading(true);
    setError(null);
    try {
      let access_token, name;
      if (mode === 'login') {
        ({ access_token, username: name } = await authLogin(username.trim(), password));
      } else {
        ({ access_token, username: name } = await authRegister(username.trim(), email.trim(), password));
      }
      login(access_token, { username: name });
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError
        ? `${err.message} (${err.status})`
        : 'Network error — check your connection.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Brand */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-primary-container mb-4">
            <ShieldCheck size={28} className="text-on-primary-container" />
          </div>
          <h1 className="text-3xl font-display-editorial font-bold text-primary">TruthMesh AI</h1>
          <p className="text-on-surface-variant mt-1 text-sm">Multi-agent fact verification</p>
        </div>

        {/* Card */}
        <div className="bg-surface-container-lowest border border-outline-variant rounded-2xl p-8 deep-shadow">
          {/* Mode toggle */}
          <div className="flex rounded-lg overflow-hidden border border-outline-variant mb-6">
            {['login', 'register'].map(m => (
              <button
                key={m}
                type="button"
                onClick={() => { setMode(m); setError(null); setEmail(''); setPassword(''); }}
                className={`flex-1 py-2.5 text-sm font-semibold font-ui-header transition-colors capitalize ${
                  mode === m
                    ? 'bg-primary text-on-primary'
                    : 'bg-surface-container text-on-surface-variant hover:bg-surface-container-high'
                }`}
              >
                {m === 'login' ? 'Sign In' : 'Register'}
              </button>
            ))}
          </div>

          {error && (
            <div className="flex items-start gap-2 bg-error-container/50 border border-secondary/30 rounded-lg px-4 py-3 mb-5 text-sm text-secondary">
              <AlertCircle size={16} className="shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-bold tracking-wider uppercase text-on-surface-variant mb-1.5">
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                autoComplete="username"
                disabled={loading}
                required
                className="w-full px-4 py-3 bg-surface-container border border-outline-variant rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary text-on-surface placeholder-outline transition-all disabled:opacity-60"
                placeholder="your_username"
              />
            </div>

            {mode === 'register' && (
              <div>
                <label className="block text-xs font-bold tracking-wider uppercase text-on-surface-variant mb-1.5">
                  Email
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  autoComplete="email"
                  disabled={loading}
                  required
                  className="w-full px-4 py-3 bg-surface-container border border-outline-variant rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary text-on-surface placeholder-outline transition-all disabled:opacity-60"
                  placeholder="you@example.com"
                />
              </div>
            )}

            <div>
              <label className="block text-xs font-bold tracking-wider uppercase text-on-surface-variant mb-1.5">
                Password {mode === 'register' && <span className="text-outline font-normal normal-case">(min. 8 chars)</span>}
              </label>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  disabled={loading}
                  required
                  className="w-full px-4 py-3 pr-11 bg-surface-container border border-outline-variant rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary text-on-surface placeholder-outline transition-all disabled:opacity-60"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPw(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-outline hover:text-on-surface transition-colors"
                  tabIndex={-1}
                >
                  {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || !username.trim() || !password}
              className="w-full bg-primary text-on-primary font-ui-header font-semibold py-3 rounded-lg hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 mt-2"
            >
              {loading
                ? <><Loader2 size={18} className="animate-spin" /> {mode === 'login' ? 'Signing in…' : 'Creating account…'}</>
                : mode === 'login' ? 'Sign In' : 'Create Account'
              }
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-on-surface-variant mt-6">
          You can also{' '}
          <button
            onClick={() => navigate('/analysis')}
            className="text-primary hover:underline font-semibold"
          >
            continue without an account
          </button>
          {' '}— history requires sign-in.
        </p>
      </div>
    </div>
  );
}
