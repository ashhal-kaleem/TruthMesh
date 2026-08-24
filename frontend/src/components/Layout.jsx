import React, { useState, useEffect } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { Home, History, Settings, Github, Search,
         Menu, X, LogOut, LogIn, User } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const REPO_URL = 'https://github.com/ashhal-kaleem/TruthMesh';

export default function Layout({ children }) {
  const [mobileMenuOpen,  setMobileMenuOpen]  = useState(false);
  const [logoutPending,   setLogoutPending]   = useState(false);
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Scroll-lock body when mobile sidebar is open
  useEffect(() => {
    document.body.style.overflow = mobileMenuOpen ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [mobileMenuOpen]);

  // Reset logout pending when route changes
  useEffect(() => {
    setLogoutPending(false);
  }, [location.pathname]);

  const closeMobile = () => { setMobileMenuOpen(false); setLogoutPending(false); };

  const handleLogoutClick = () => {
    if (!logoutPending) { setLogoutPending(true); return; }
    setLogoutPending(false);
    logout();
    navigate('/login');
  };

  const cancelLogout = () => setLogoutPending(false);

  const getNavLinkClass = ({ isActive }) =>
    `group flex items-center gap-3.5 px-6 py-3.5 transition-all focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary ${
      isActive
        ? 'text-primary bg-surface-container-high border-r-[3px] border-primary font-semibold'
        : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container border-r-[3px] border-transparent font-medium'
    }`;

  const getNavIconClass = (isActive) =>
    `transition-colors duration-150 ${isActive ? 'text-primary' : 'text-outline group-hover:text-on-surface'}`;

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-surface">
      {/* Sidebar */}
      <nav
        className={`fixed inset-y-0 left-0 z-40 w-64 bg-surface border-r border-outline-variant flex flex-col transition-transform duration-300 md:translate-x-0 ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}`}
        aria-label="Main navigation"
      >
        {/* Brand */}
        <div className="p-6 border-b border-outline-variant flex justify-between items-center h-16">
          <div>
            <h1 className="text-xl font-display-editorial font-bold text-on-surface">TruthMesh <span className="text-primary font-medium">AI</span></h1>
          </div>
          <button
            className="md:hidden text-outline hover:text-on-surface transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded p-1"
            onClick={closeMobile}
            aria-label="Close navigation"
          >
            <X size={20} />
          </button>
        </div>

        {/* Nav links */}
        <div className="flex-1 py-6 flex flex-col">
          <p className="px-6 text-xs font-bold tracking-widest uppercase text-outline mb-2">Menu</p>
          <ul className="flex flex-col">
            {[
              { to: '/',         Icon: Home,     label: 'Home',     end: true  },
              { to: '/analysis', Icon: Search,   label: 'Analysis', end: false },
              { to: '/history',  Icon: History,  label: 'History',  end: false },
              { to: '/settings', Icon: Settings, label: 'Settings', end: false },
            ].map(({ to, Icon, label, end }) => (
              <li key={to}>
                <NavLink to={to} end={end} className={getNavLinkClass} onClick={closeMobile}>
                  {({ isActive }) => (
                    <>
                      <Icon size={18} className={getNavIconClass(isActive)} aria-hidden="true" />
                      <span>{label}</span>
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>

        {/* Footer: GitHub link + auth */}
        <div className="border-t border-outline-variant mt-auto">
          {/* External links */}
          <div className="py-2">
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex items-center gap-3.5 px-6 py-3 text-on-surface-variant hover:text-on-surface hover:bg-surface-container transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary font-medium"
              aria-label="View TruthMesh on GitHub"
            >
              <Github size={18} className="text-outline group-hover:text-on-surface transition-colors duration-150" aria-hidden="true" />
              <span className="text-sm">GitHub</span>
            </a>
          </div>

          {/* Auth Block */}
          <div className="border-t border-outline-variant bg-surface-container-lowest">
            {isAuthenticated ? (
              <div className="p-4">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0 border border-primary/20">
                    <User size={15} className="text-primary" aria-hidden="true" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-outline font-medium leading-none mb-1">Signed in as</p>
                    <p className="text-sm text-on-surface font-semibold truncate leading-none">{user?.username}</p>
                  </div>
                </div>

                {logoutPending ? (
                  <div className="bg-surface-container-low rounded-lg p-2 border border-outline-variant animate-in fade-in duration-150">
                    <p className="text-xs text-on-surface-variant font-medium text-center mb-2">Sign out of TruthMesh?</p>
                    <div className="flex gap-1.5">
                      <button
                        onClick={cancelLogout}
                        className="flex-1 text-xs font-semibold border border-outline-variant text-on-surface-variant py-1.5 rounded bg-surface-container-lowest hover:bg-surface-container transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary shadow-sm"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleLogoutClick}
                        className="flex-1 flex items-center justify-center gap-1.5 text-xs font-semibold bg-secondary border border-secondary text-on-secondary py-1.5 rounded transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-secondary shadow-sm"
                      >
                        Sign out
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={handleLogoutClick}
                    className="flex items-center justify-center gap-2 text-sm font-medium text-secondary hover:bg-error-container/50 border border-transparent hover:border-secondary/20 py-2 rounded-lg transition-colors w-full focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-secondary"
                    aria-label="Sign out"
                  >
                    <LogOut size={15} /> Sign out
                  </button>
                )}
              </div>
            ) : (
              <div className="p-4">
                <button
                  onClick={() => { navigate('/login'); closeMobile(); }}
                  className="flex items-center justify-center gap-2 px-4 py-2 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 transition-colors rounded-lg w-full text-sm font-semibold focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary shadow-sm"
                >
                  <LogIn size={16} aria-hidden="true" /> Sign In
                </button>
              </div>
            )}
          </div>
        </div>
      </nav>

      {/* Main area */}
      <main className="flex-1 md:ml-64 flex flex-col min-h-screen relative">
        {/* Top bar (Mobile only now, desktop has cleaner edge) */}
        <header className="md:hidden bg-surface/90 backdrop-blur-md border-b border-outline-variant sticky top-0 z-30">
          <div className="h-14 flex justify-between items-center px-4 w-full">
            <div className="flex items-center gap-3">
              <button
                className="text-outline hover:text-on-surface transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded p-1"
                onClick={() => setMobileMenuOpen(true)}
                aria-label="Open navigation"
                aria-expanded={mobileMenuOpen}
              >
                <Menu size={22} />
              </button>
              <span className="font-display-editorial text-xl font-bold text-on-surface">TruthMesh</span>
            </div>

            <div className="flex items-center">
              {isAuthenticated ? (
                <button
                  onClick={() => setMobileMenuOpen(true)}
                  aria-label="Open account menu"
                  className="w-8 h-8 rounded-full bg-primary/10 border border-primary/20 text-primary flex items-center justify-center font-bold text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
                >
                  {user?.username?.charAt(0).toUpperCase() || 'U'}
                </button>
              ) : (
                <button
                  onClick={() => navigate('/login')}
                  className="text-primary text-sm font-semibold focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded px-2 py-1"
                >
                  Sign In
                </button>
              )}
            </div>
          </div>
        </header>

        {/* Desktop top spacer to match the visual rhythm (optional, depending on content padding) */}
        <div className="hidden md:block h-6 w-full" />

        {/* Page content */}
        <div className="flex-1 p-4 md:px-10 lg:px-16 max-w-[1200px] mx-auto w-full flex flex-col">
          {children}
        </div>

        {/* Footer */}
        <footer className="mt-auto px-4 md:px-10 lg:px-16 py-6 border-t border-outline-variant bg-surface-container-lowest flex flex-col md:flex-row justify-between items-center gap-4">
          <span className="text-xs font-semibold tracking-widest text-outline uppercase">
            © {new Date().getFullYear()} TruthMesh AI
          </span>
          <div className="flex gap-5 text-sm font-medium text-on-surface-variant">
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-primary transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded px-1"
            >
              GitHub
            </a>
            <NavLink to="/settings" className="hover:text-primary transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded px-1">
              Settings
            </NavLink>
          </div>
        </footer>
      </main>

      {/* Mobile backdrop */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm z-30 md:hidden animate-in fade-in duration-200"
          onClick={closeMobile}
          aria-hidden="true"
        />
      )}
    </div>
  );
}
