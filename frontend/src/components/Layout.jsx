import React, { useState, useEffect } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { Home, History, Settings, BookOpen, ExternalLink, Search,
         Menu, X, LogOut, LogIn, User } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const REPO_URL = 'https://github.com/ashhal-kaleem/TruthMesh';

export default function Layout({ children }) {
  const [mobileMenuOpen,  setMobileMenuOpen]  = useState(false);
  const [logoutPending,   setLogoutPending]   = useState(false);
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();

  // Scroll-lock body when mobile sidebar is open
  useEffect(() => {
    if (mobileMenuOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [mobileMenuOpen]);

  const closeMobile = () => { setMobileMenuOpen(false); setLogoutPending(false); };

  // U5: two-step logout — first click shows confirm, second executes
  const handleLogoutClick = () => {
    if (!logoutPending) { setLogoutPending(true); return; }
    setLogoutPending(false);
    logout();
    navigate('/login');
  };

  const cancelLogout = () => setLogoutPending(false);

  const getNavLinkClass = ({ isActive }) =>
    `flex items-center gap-3 px-6 py-3 transition-all ${
      isActive
        ? 'text-primary border-r-2 border-primary font-semibold bg-surface-container-high'
        : 'text-on-surface-variant hover:text-primary hover:bg-surface-container'
    }`;

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-surface">
      {/* Sidebar */}
      <nav
        className={`fixed inset-y-0 left-0 z-40 w-64 bg-surface border-r border-outline-variant flex flex-col transition-transform duration-300 md:translate-x-0 ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}`}
        aria-label="Main navigation"
      >
        {/* Brand */}
        <div className="p-6 border-b border-outline-variant flex justify-between items-center">
          <div>
            <h1 className="text-xl font-display-editorial font-bold text-primary">TruthMesh AI</h1>
            <p className="text-xs font-semibold tracking-widest text-on-surface-variant mt-1 uppercase">Research Preview</p>
          </div>
          <button
            className="md:hidden text-on-surface-variant hover:text-primary transition-colors"
            onClick={closeMobile}
            aria-label="Close navigation"
          >
            <X size={24} />
          </button>
        </div>

        {/* Nav links */}
        <div className="flex-1 overflow-y-auto py-4">
          <ul className="space-y-1">
            {[
              { to: '/',         Icon: Home,     label: 'Home',     end: true  },
              { to: '/analysis', Icon: Search,   label: 'Analysis', end: false },
              { to: '/history',  Icon: History,  label: 'History',  end: false },
              { to: '/settings', Icon: Settings, label: 'Settings', end: false },
            ].map(({ to, Icon, label, end }) => (
              <li key={to}>
                <NavLink to={to} end={end} className={getNavLinkClass} onClick={closeMobile}>
                  <Icon size={20} />
                  <span>{label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </div>

        {/* Footer links + auth */}
        <div className="p-4 border-t border-outline-variant mt-auto space-y-1">
          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 px-4 py-2 text-on-surface-variant hover:text-primary transition-colors hover:bg-surface-container rounded"
          >
            <BookOpen size={18} />
            <span className="text-sm">About TruthMesh</span>
            <ExternalLink size={11} className="ml-auto opacity-40" />
          </a>
          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 px-4 py-2 text-on-surface-variant hover:text-primary transition-colors hover:bg-surface-container rounded"
          >
            <ExternalLink size={18} />
            <span className="text-sm">Source Code</span>
          </a>

          <div className="pt-2 mt-2 border-t border-outline-variant">
            {isAuthenticated ? (
              <div className="px-4 py-2">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-7 h-7 rounded-full bg-primary-container flex items-center justify-center shrink-0">
                    <User size={14} className="text-on-primary-container" />
                  </div>
                  <span className="text-sm text-on-surface font-semibold truncate">{user?.username}</span>
                </div>
                {logoutPending ? (
                  <div className="space-y-1">
                    <p className="text-xs text-on-surface-variant px-2 pb-1">Sign out of TruthMesh?</p>
                    <div className="flex gap-1.5">
                      <button
                        onClick={handleLogoutClick}
                        className="flex-1 flex items-center justify-center gap-1.5 text-xs font-semibold bg-secondary text-on-secondary px-2 py-1.5 rounded transition-colors"
                      >
                        <LogOut size={13} /> Confirm
                      </button>
                      <button
                        onClick={cancelLogout}
                        className="flex-1 text-xs font-semibold border border-outline-variant text-on-surface-variant px-2 py-1.5 rounded hover:bg-surface-container transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={handleLogoutClick}
                    className="flex items-center gap-2 text-sm text-secondary hover:bg-error-container/30 px-2 py-1.5 rounded transition-colors w-full"
                    aria-label="Sign out"
                  >
                    <LogOut size={15} /> Sign out
                  </button>
                )}
              </div>
            ) : (
              <button
                onClick={() => { navigate('/login'); closeMobile(); }}
                className="flex items-center gap-3 px-4 py-2 text-primary hover:bg-primary/10 transition-colors rounded w-full text-sm font-semibold"
              >
                <LogIn size={18} /> Sign In
              </button>
            )}
          </div>
        </div>
      </nav>

      {/* Main area */}
      <main className="flex-1 md:ml-64 flex flex-col min-h-screen">
        {/* TopAppBar */}
        <header className="bg-surface/80 backdrop-blur-md border-b border-outline-variant shadow-sm sticky top-0 z-30">
          <div className="h-16 flex justify-between items-center px-4 md:px-12 max-w-[1280px] mx-auto w-full">
            {/* Mobile: hamburger + brand */}
            <div className="md:hidden flex items-center gap-4">
              <button
                className="text-on-surface-variant hover:text-primary transition-colors"
                onClick={() => setMobileMenuOpen(true)}
                aria-label="Open navigation"
              >
                <Menu size={24} />
              </button>
              <span className="font-display-editorial text-2xl font-bold text-primary">TruthMesh</span>
            </div>

            {/* Desktop: auth controls (right-aligned) */}
            <div className="hidden md:flex flex-1 items-center justify-end gap-4">
              {isAuthenticated ? (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-on-surface-variant font-semibold">{user?.username}</span>
                  {logoutPending ? (
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-on-surface-variant">Sign out?</span>
                      <button
                        onClick={handleLogoutClick}
                        className="text-xs font-semibold bg-secondary text-on-secondary px-2.5 py-1 rounded transition-colors"
                      >
                        Confirm
                      </button>
                      <button
                        onClick={cancelLogout}
                        className="text-xs font-semibold border border-outline-variant text-on-surface-variant px-2.5 py-1 rounded hover:bg-surface-container transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={handleLogoutClick}
                      title="Sign out"
                      aria-label="Sign out"
                      className="flex items-center gap-1.5 text-xs font-semibold text-on-surface-variant border border-outline-variant px-2.5 py-1 rounded-lg hover:bg-error-container/30 hover:text-secondary hover:border-secondary/40 transition-colors"
                    >
                      <LogOut size={13} />
                      Sign out
                    </button>
                  )}
                </div>
              ) : (
                <button
                  onClick={() => navigate('/login')}
                  className="flex items-center gap-2 text-sm font-semibold text-primary border border-primary/30 px-3 py-1.5 rounded-lg hover:bg-primary/10 transition-colors"
                >
                  <LogIn size={15} /> Sign In
                </button>
              )}
            </div>

            {/* Mobile: auth avatar — routes through sidebar for two-step */}
            <div className="md:hidden flex items-center gap-3">
              {isAuthenticated ? (
                <button
                  onClick={() => setMobileMenuOpen(true)}
                  title="Account menu"
                  aria-label="Open account menu"
                  className="w-8 h-8 rounded-full bg-primary-container text-on-primary-container flex items-center justify-center font-bold text-sm"
                >
                  {user?.username?.charAt(0).toUpperCase() || 'U'}
                </button>
              ) : (
                <button onClick={() => navigate('/login')} className="text-primary" aria-label="Sign in">
                  <LogIn size={20} />
                </button>
              )}
            </div>
          </div>
        </header>

        {/* Page content */}
        <div className="flex-1 p-4 md:p-8 lg:p-12 max-w-[1200px] mx-auto w-full flex flex-col">
          {children}
        </div>

        {/* Footer */}
        <footer className="mt-auto px-4 md:px-12 py-6 border-t border-outline-variant bg-surface-container-lowest flex flex-col md:flex-row justify-between items-center gap-4">
          <span className="text-xs font-semibold tracking-widest text-on-surface-variant uppercase">
            © {new Date().getFullYear()} TruthMesh AI · Research Preview
          </span>
          <div className="flex gap-4 text-sm text-on-surface-variant">
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-primary transition-colors"
            >
              About
            </a>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-primary transition-colors"
            >
              GitHub
            </a>
            <NavLink to="/settings" className="hover:text-primary transition-colors">
              Settings
            </NavLink>
          </div>
        </footer>
      </main>

      {/* Mobile backdrop — tap to close sidebar */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/30 backdrop-blur-sm z-30 md:hidden"
          onClick={closeMobile}
          aria-hidden="true"
        />
      )}
    </div>
  );
}
