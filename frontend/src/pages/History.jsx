import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, ShieldX, HelpCircle, Clock, Trash2, Search,
         Loader2, AlertCircle, LogIn, RefreshCw, EyeOff } from 'lucide-react';
import { fetchHistory, ApiError } from '../api';
import { useAuth } from '../context/AuthContext';
import { normaliseVerdict } from '../api';

// ─── Sample fallback shown in mock mode ───────────────────────────────────────
const SAMPLE_HISTORY = [
  { id: 'CK-8F92A', claim: 'Global supply chain disruptions projected to ease by Q3 based on leading maritime shipping indexes.', label: 'SUPPORTS', timestamp: new Date(Date.now() - 2 * 3600 * 1000).toISOString(), sourceCount: 5 },
  { id: 'CK-4B19C', claim: 'New breakthrough battery tech promises 1000x capacity increase with zero rare earth metals.', label: 'REFUTES', timestamp: new Date(Date.now() - 5 * 3600 * 1000).toISOString(), sourceCount: 1 },
  { id: 'CK-9X33Y', claim: 'Proposed central bank digital currency (CBDC) implementation timeline shifted to late 2026.', label: 'NOT ENOUGH INFO', timestamp: new Date(Date.now() - 24 * 3600 * 1000).toISOString(), sourceCount: 12 },
  { id: 'CK-1A07B', claim: 'Earnings report anomalies for Q2 tech sector.', label: 'SUPPORTS', timestamp: new Date(Date.now() - 3 * 24 * 3600 * 1000).toISOString(), sourceCount: 8 },
];

const IS_MOCK_MODE = import.meta.env.VITE_MOCK_MODE === 'true';

// ─── Helpers ──────────────────────────────────────────────────────────────────
function getLabelConfig(label) {
  switch ((label || '').toUpperCase()) {
    case 'SUPPORTS':
      return { Icon: ShieldCheck, dot: 'bg-cyan-500', text: 'text-cyan-700', badge: 'bg-cyan-50 border-cyan-200', label: 'Supports' };
    case 'REFUTES':
      return { Icon: ShieldX, dot: 'bg-secondary', text: 'text-secondary', badge: 'bg-error-container/50 border-secondary/20', label: 'Refutes' };
    default:
      return { Icon: HelpCircle, dot: 'bg-tertiary', text: 'text-tertiary', badge: 'bg-tertiary-container/20 border-tertiary/20', label: 'Not Enough Info' };
  }
}

function formatRelativeTime(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3600000);
  const d = Math.floor(h / 24);
  if (d > 0) return `${d}d ago`;
  if (h > 0) return `${h}h ago`;
  return 'Just now';
}

/**
 * Map a raw ClaimHistoryItem from the API to the local display shape.
 * { claim_id, claim_text, verdict, confidence, citations, created_at }
 */
function mapApiItem(item) {
  return {
    id:          item.id != null ? `CK-${String(item.id).padStart(5, '0')}` : `CK-${Math.random().toString(36).slice(2, 7).toUpperCase()}`,
    claim:       item.claim_text || '',
    label:       normaliseVerdict(item.verdict),
    timestamp:   item.created_at || new Date().toISOString(),
    sourceCount: Array.isArray(item.citations) ? item.citations.length : 0,
    confidence:  item.confidence ?? null,
  };
}

export default function History() {
  const navigate = useNavigate();
  const { isAuthenticated, logout } = useAuth();

  useEffect(() => { document.title = 'Analysis History — TruthMesh'; }, []);

  const [history,  setHistory]  = useState([]);
  const [search,   setSearch]   = useState('');
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState(null);
  const [page,     setPage]     = useState(1);
  const [hasMore,  setHasMore]  = useState(false);
  const PAGE_SIZE = 20;

  const loadHistory = async (p = 1, replace = true) => {
    setLoading(true);
    setError(null);
    try {
      const raw = await fetchHistory(p, PAGE_SIZE);

      // Mock mode returns [] — show sample data so the page isn't blank
      const items = raw.length === 0 && IS_MOCK_MODE
        ? SAMPLE_HISTORY
        : raw.map(mapApiItem);

      setHistory(prev => replace ? items : [...prev, ...items]);
      setHasMore(raw.length >= PAGE_SIZE);
      setPage(p);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        navigate('/login', { state: { from: '/history' } });
        return;
      }
      setError(err.message || 'Failed to load history.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadHistory(1); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const removeItem = (id) => setHistory(h => h.filter(i => i.id !== id));

  const filtered = history.filter(item =>
    item.claim.toLowerCase().includes(search.toLowerCase()) ||
    item.id.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-8 py-2 md:py-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end gap-4 justify-between">
        <div>
          <h2 className="text-3xl md:text-4xl font-display-editorial font-bold text-primary">Analysis History</h2>
          <p className="text-on-surface-variant mt-1">
            {loading ? 'Loading…' : `${history.length} claim${history.length !== 1 ? 's' : ''} analysed`}
            {IS_MOCK_MODE && <span className="ml-2 text-xs text-tertiary-container font-semibold">(demo data)</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => loadHistory(1)}
            disabled={loading}
            title="Refresh"
            className="inline-flex items-center gap-2 text-sm text-on-surface-variant border border-outline-variant px-3 py-2 rounded-lg hover:bg-surface-container transition-all disabled:opacity-50"
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          </button>
          {history.length > 0 && (
            <button
              onClick={() => setHistory([])}
              title="Hides results from this view only — your saved history on the server is not affected. Click Refresh to reload."
              aria-label="Hide all results from this view (server history is unaffected)"
              className="inline-flex items-center gap-2 text-sm text-on-surface-variant hover:text-primary px-4 py-2 rounded-lg border border-outline-variant hover:border-primary/40 transition-all"
            >
              <EyeOff size={16} /> Hide View
            </button>
          )}
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-outline" size={18} />
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Filter by claim or ID…"
          className="w-full pl-12 pr-4 py-3 bg-surface-container-lowest border border-outline-variant rounded-lg focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all text-on-surface placeholder-outline"
        />
      </div>

      {/* Error state */}
      {error && !loading && (
        <div className="flex items-start gap-3 bg-error-container/40 border border-secondary/30 rounded-xl p-5 text-secondary">
          <AlertCircle size={20} className="shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-sm">Failed to load history</p>
            <p className="text-sm opacity-80 mt-0.5">{error}</p>
            <button onClick={() => loadHistory(1)} className="mt-2 text-xs underline hover:no-underline">Retry</button>
          </div>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && history.length === 0 && (
        <div className="space-y-3 animate-pulse">
          {[1,2,3].map(i => <div key={i} className="h-20 rounded-xl bg-surface-container-high" />)}
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && filtered.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-center gap-4">
          <div className="w-16 h-16 rounded-full bg-surface-container flex items-center justify-center">
            <Clock size={28} className="text-outline" />
          </div>
          <h4 className="text-xl font-display-editorial text-on-surface-variant">No history found</h4>
          <p className="text-on-surface-variant text-sm max-w-xs">
            {search ? `No results for "${search}"` : 'Analyse a claim and it will appear here.'}
          </p>
        </div>
      )}

      {/* History list */}
      {filtered.length > 0 && (
        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden deep-shadow">
          <ul className="divide-y divide-outline-variant">
            {filtered.map((item) => {
              const config = getLabelConfig(item.label);
              return (
                <li
                  key={item.id}
                  className="p-5 hover:bg-surface-container-low transition-colors flex items-center justify-between gap-4 group"
                >
                  <div className="flex items-center gap-4 overflow-hidden flex-1">
                    <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${config.dot}`} />
                    <div className="min-w-0">
                      <p className="font-claim-text text-base text-primary truncate">{item.claim}</p>
                      <div className="flex items-center gap-3 mt-1 flex-wrap">
                        <span className={`text-xs font-bold tracking-wider px-2 py-0.5 rounded-full border uppercase ${config.badge} ${config.text}`}>
                          {config.label}
                        </span>
                        <span className="font-mono-technical text-xs text-outline">{item.id}</span>
                        {item.sourceCount > 0 && (
                          <span className="text-xs text-on-surface-variant">{item.sourceCount} sources</span>
                        )}
                        {item.confidence !== null && (
                          <span className="font-mono-technical text-xs text-outline">
                            {Math.round(item.confidence * 100)}% confidence
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="font-mono-technical text-xs text-outline hidden sm:block">
                      {formatRelativeTime(item.timestamp)}
                    </span>
                    <button
                      onClick={() => removeItem(item.id)}
                      className="text-outline hover:text-secondary opacity-0 group-hover:opacity-100 transition-all"
                      title="Remove"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Load more */}
      {hasMore && !loading && (
        <div className="text-center">
          <button
            onClick={() => loadHistory(page + 1, false)}
            className="text-sm font-semibold text-primary border border-primary/30 px-5 py-2 rounded-lg hover:bg-primary/10 transition-colors"
          >
            Load more
          </button>
        </div>
      )}
    </div>
  );
}
