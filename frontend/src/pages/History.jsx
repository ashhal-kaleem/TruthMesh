import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, ShieldX, HelpCircle, Clock, Trash2, Search,
         Loader2, AlertCircle, RefreshCw, EyeOff, LogIn, ChevronRight } from 'lucide-react';
import { fetchHistory, ApiError, normaliseVerdict } from '../api';
import { useAuth } from '../context/AuthContext';

// ─── Helpers ──────────────────────────────────────────────────────────────────
function getLabelConfig(label) {
  switch ((label || '').toUpperCase()) {
    case 'SUPPORTS':
      return {
        Icon: ShieldCheck,
        color: 'text-primary',
        badge: 'bg-primary/10 border-primary/20 text-primary',
        label: 'Supports',
      };
    case 'REFUTES':
      return {
        Icon: ShieldX,
        color: 'text-secondary',
        badge: 'bg-error-container/50 border-secondary/20 text-secondary',
        label: 'Refutes',
      };
    default:
      return {
        Icon: HelpCircle,
        color: 'text-tertiary',
        badge: 'bg-surface-container-low border-outline-variant text-on-surface-variant',
        label: 'Not Enough Info',
      };
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

const CREDIBILITY_MAP = { high: 0.9, medium: 0.6, low: 0.25, unknown: 0.4 };
function credibilityToFloat(raw) {
  if (typeof raw === 'number') return raw;
  return CREDIBILITY_MAP[(raw || '').toLowerCase()] ?? 0.4;
}

function mapApiItem(item) {
  // Build the full normalised result so Analysis.jsx can display it without
  // re-running the pipeline when the user clicks this history item.
  const citations = (item.citations || []).map(c => ({
    title:             c.title   || '',
    url:               c.url     || '',
    domain:            (() => { try { return new URL(c.url).hostname.replace(/^www\./, ''); } catch { return ''; } })(),
    excerpt:           c.excerpt || '',
    stance:            normaliseVerdict(c.bias_label) === 'NOT ENOUGH INFO' ? 'NEUTRAL' : normaliseVerdict(c.bias_label),
    reliability_score: credibilityToFloat(c.credibility_score),
    bias_label:        c.bias_label || 'Unknown',
  }));
  const normalisedResult = {
    claim:              item.claim_text || '',
    verdict:            normaliseVerdict(item.verdict),
    confidence:         typeof item.confidence === 'number' ? item.confidence : 0.5,
    reasoning:          item.reasoning || '',
    evidence_citations: citations,
    past_context_used:  item.past_context_used || false,
    image_analyzed:     item.image_analyzed    || false,
    _historyId:         item.id,
    _createdAt:         item.created_at || null,
  };
  return {
    id:               item.id ?? null,
    claim:            item.claim_text || '',
    label:            normaliseVerdict(item.verdict),
    timestamp:        item.created_at || new Date().toISOString(),
    sourceCount:      Array.isArray(item.citations) ? item.citations.length : 0,
    confidence:       item.confidence ?? null,
    normalisedResult, // full result for instant restore in Analysis.jsx
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
  const [hidden,   setHidden]   = useState(false);
  const PAGE_SIZE = 20;

  const loadHistory = async (p = 1, replace = true) => {
    setLoading(true);
    setError(null);
    setHidden(false);
    try {
      const raw = await fetchHistory(p, PAGE_SIZE);
      const items = raw.map(mapApiItem);
      setHistory(prev => replace ? items : [...prev, ...items]);
      setHasMore(raw.length >= PAGE_SIZE);
      setPage(p);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        navigate('/login', { state: { from: '/history' } });
        return;
      }
      setError('Unable to load your analysis history. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadHistory(1); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const removeItem = (id) => setHistory(h => h.filter(i => i.id !== id));

  const filtered = search.trim()
    ? history.filter(item => item.claim.toLowerCase().includes(search.toLowerCase()))
    : history;

  const visibleItems = hidden ? [] : filtered;

  // ─── Unauthenticated gate ──────────────────────────────────────────────────
  if (!isAuthenticated) {
    return (
      <div className="space-y-6 py-2 md:py-6 animate-in fade-in duration-500">
        <div>
          <h2 className="text-3xl md:text-4xl font-display-editorial font-bold text-on-surface">Analysis History</h2>
          <p className="text-on-surface-variant text-sm mt-1">Your verified claims, saved to your account.</p>
        </div>
        <div className="flex flex-col items-center justify-center py-16 text-center gap-3 bg-surface-container-lowest border border-outline-variant rounded-xl deep-shadow">
          <div className="w-12 h-12 rounded-full bg-surface-container flex items-center justify-center">
            <LogIn size={20} className="text-outline" aria-hidden="true" />
          </div>
          <h4 className="text-lg font-display-editorial font-bold text-on-surface">Sign in to view your history</h4>
          <p className="text-on-surface-variant text-sm max-w-sm mx-auto">
            History is saved per account. Sign in to access your previous analyses and review past evidence.
          </p>
          <button
            onClick={() => navigate('/login', { state: { from: '/history' } })}
            className="mt-3 inline-flex items-center gap-2 bg-primary text-on-primary font-ui-header font-semibold py-2 px-5 rounded-lg hover:opacity-90 transition-all text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
          >
            <LogIn size={15} aria-hidden="true" /> Sign In
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 py-2 md:py-6 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end gap-4 justify-between">
        <div>
          <h2 className="text-3xl md:text-4xl font-display-editorial font-bold text-on-surface">Analysis History</h2>
          <p className="text-on-surface-variant text-sm mt-1">
            {loading
              ? 'Loading your data…'
              : history.length === 0
              ? 'No analyses yet'
              : `${history.length} claim${history.length !== 1 ? 's' : ''} analysed`
            }
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <button
            onClick={() => loadHistory(1)}
            disabled={loading}
            title="Refresh history"
            aria-label="Refresh history"
            className="inline-flex items-center justify-center w-9 h-9 text-on-surface-variant border border-outline-variant rounded-lg hover:bg-surface-container transition-all disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} aria-hidden="true" />
          </button>
          {history.length > 0 && !hidden && (
            <button
              onClick={() => setHidden(true)}
              title="Clear this view — your server history is unaffected. Refresh to reload."
              aria-label="Clear this view (server history is unaffected)"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-on-surface-variant hover:text-primary px-3 h-9 rounded-lg border border-outline-variant hover:border-primary/40 transition-all focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
            >
              <EyeOff size={15} aria-hidden="true" /> Clear view
            </button>
          )}
        </div>
      </div>

      {/* Search */}
      {history.length > 0 && !hidden && (
        <div className="relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-outline pointer-events-none" size={18} aria-hidden="true" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search your analysis history…"
            aria-label="Search analysis history"
            className="w-full pl-11 pr-4 h-12 bg-surface-container-lowest border border-outline-variant rounded-xl focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all text-on-surface placeholder-outline text-sm shadow-sm"
          />
        </div>
      )}

      {/* Error state */}
      {error && !loading && (
        <div className="flex items-start gap-3 bg-error-container/40 border border-secondary/30 rounded-xl p-4 text-secondary">
          <AlertCircle size={18} className="shrink-0 mt-0.5" aria-hidden="true" />
          <div>
            <p className="font-semibold text-sm">Could not load history</p>
            <p className="text-sm opacity-85 mt-0.5">{error}</p>
            <button
              onClick={() => loadHistory(1)}
              className="mt-2 text-xs font-semibold underline hover:no-underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-secondary rounded"
            >
              Try again
            </button>
          </div>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && history.length === 0 && (
        <div className="space-y-2 animate-pulse">
          {[1, 2, 3, 4].map(i => <div key={i} className="h-20 rounded-xl bg-surface-container-high w-full" />)}
        </div>
      )}

      {/* Hidden state */}
      {hidden && (
        <div className="flex flex-col items-center justify-center py-16 text-center gap-2.5">
          <div className="w-12 h-12 rounded-full bg-surface-container flex items-center justify-center">
            <EyeOff size={22} className="text-outline" aria-hidden="true" />
          </div>
          <p className="text-base font-display-editorial font-bold text-on-surface">View cleared</p>
          <p className="text-sm text-on-surface-variant max-w-xs">Your history is still saved on the server.</p>
          <button
            onClick={() => loadHistory(1)}
            className="mt-2 text-sm font-semibold text-primary border border-primary/30 px-4 py-1.5 rounded-lg hover:bg-primary/10 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
          >
            Reload history
          </button>
        </div>
      )}

      {/* Empty state — no history at all */}
      {!loading && !error && !hidden && history.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center gap-2.5 bg-surface-container-lowest border border-outline-variant rounded-xl deep-shadow">
          <div className="w-12 h-12 rounded-full bg-surface-container flex items-center justify-center">
            <Clock size={22} className="text-outline" aria-hidden="true" />
          </div>
          <p className="text-base font-display-editorial font-bold text-on-surface">No analyses yet</p>
          <p className="text-sm text-on-surface-variant max-w-xs">
            Once you verify claims, they will appear here for easy reference.
          </p>
          <button
            onClick={() => navigate('/analysis')}
            className="mt-2 text-sm font-semibold text-primary border border-primary/30 px-4 py-1.5 rounded-lg hover:bg-primary/10 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
          >
            Go to Analysis
          </button>
        </div>
      )}

      {/* Empty search result */}
      {!loading && !error && !hidden && history.length > 0 && filtered.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center gap-2.5 border border-dashed border-outline-variant rounded-xl">
          <p className="text-base font-display-editorial font-bold text-on-surface-variant">No results</p>
          <p className="text-sm text-outline">No claims match "{search}".</p>
          <button onClick={() => setSearch('')} className="text-sm font-medium text-primary hover:underline">
            Clear search
          </button>
        </div>
      )}

      {/* History list */}
      {visibleItems.length > 0 && (
        <div className="flex flex-col gap-2">
          {visibleItems.map((item) => {
            const config = getLabelConfig(item.label);
            return (
              <div
                key={item.id ?? item.claim}
                className="group relative bg-surface-container-lowest border border-outline-variant rounded-xl transition-all duration-150 hover:border-primary/30 hover:shadow-sm focus-within:ring-2 focus-within:ring-primary focus-within:ring-offset-1 focus-within:border-primary"
              >
                <div className="flex items-center">
                  <button
                    className="flex-1 text-left py-4 pl-4 pr-2 flex items-center gap-4 min-w-0 outline-none"
                    onClick={() => navigate('/analysis', { state: { historyResult: item.normalisedResult } })}
                    title="View original result"
                    aria-label={`View original result: ${item.claim}`}
                  >
                    {/* Icon block */}
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${config.badge}`}>
                      <config.Icon size={18} aria-hidden="true" />
                    </div>

                    {/* Claim & Metadata */}
                    <div className="flex-1 min-w-0 overflow-hidden">
                      <p className="font-claim-text text-sm md:text-base text-on-surface truncate group-hover:text-primary transition-colors">
                        {item.claim}
                      </p>
                      <div className="flex items-center gap-x-3 gap-y-1 mt-1 flex-wrap">
                        <span className={`text-[11px] font-bold tracking-wider uppercase ${config.color}`}>
                          {config.label}
                        </span>
                        {item.confidence !== null && (
                          <span className="text-[11px] font-mono-technical text-outline">
                            {Math.round(item.confidence * 100)}% conf
                          </span>
                        )}
                        {item.sourceCount > 0 && (
                          <span className="text-[11px] text-outline">
                            {item.sourceCount} source{item.sourceCount !== 1 ? 's' : ''}
                          </span>
                        )}
                        <span className="text-[11px] text-outline ml-auto">
                          {formatRelativeTime(item.timestamp)}
                        </span>
                      </div>
                    </div>

                    {/* Go arrow */}
                    <div className="shrink-0 text-outline opacity-0 group-hover:opacity-100 transition-opacity px-2 hidden sm:block">
                      <ChevronRight size={18} aria-hidden="true" />
                    </div>
                  </button>

                  {/* Delete action */}
                  <div className="pr-3 shrink-0">
                    <button
                      onClick={() => removeItem(item.id ?? item.claim)}
                      className="text-outline hover:text-secondary opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-all p-2 rounded-lg hover:bg-error-container/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary focus-visible:opacity-100"
                      title="Remove from this view"
                      aria-label="Remove from this view"
                    >
                      <Trash2 size={16} aria-hidden="true" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Load more */}
      {hasMore && !loading && !hidden && (
        <div className="text-center pt-2">
          <button
            onClick={() => loadHistory(page + 1, false)}
            className="text-sm font-semibold text-primary border border-outline-variant px-5 py-2 rounded-lg hover:border-primary/50 hover:bg-surface-container transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            Load more
          </button>
        </div>
      )}
    </div>
  );
}
