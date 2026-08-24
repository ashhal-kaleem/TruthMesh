import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Zap, Loader2, AlertCircle, ShieldCheck, ShieldX,
  HelpCircle, ExternalLink, ChevronDown, ChevronUp, Search,
  ImagePlus, X as XIcon, Clock, Image
} from 'lucide-react';
import { checkClaim, ApiError } from '../api';

const IS_MOCK_MODE = import.meta.env.VITE_MOCK_MODE === 'true';

// ─── Verdict Config ───────────────────────────────────────────────────────────
// Canonical verdict values from normaliseVerdict(): SUPPORTS | REFUTES | NOT ENOUGH INFO
function getVerdictConfig(verdict) {
  switch ((verdict || '').toUpperCase().trim()) {
    case 'SUPPORTS':
      return {
        Icon: ShieldCheck,
        color: 'text-cyan-700',
        bg: 'bg-cyan-50',
        border: 'border-cyan-300',
        bar: 'bg-cyan-500',
        label: 'Supports',
        description: 'The evidence supports this claim.',
      };
    case 'REFUTES':
      return {
        Icon: ShieldX,
        color: 'text-secondary',
        bg: 'bg-error-container/60',
        border: 'border-secondary/30',
        bar: 'bg-secondary',
        label: 'Refutes',
        description: 'The evidence refutes this claim.',
      };
    default:
      return {
        Icon: HelpCircle,
        color: 'text-tertiary',
        bg: 'bg-tertiary-container/20',
        border: 'border-tertiary/30',
        bar: 'bg-tertiary',
        label: 'Not Enough Info',
        description: 'Insufficient evidence to make a determination.',
      };
  }
}

function getStanceColor(stance) {
  switch ((stance || '').toUpperCase()) {
    case 'SUPPORTS': return 'text-cyan-700 bg-cyan-50 border-cyan-200';
    case 'REFUTES':  return 'text-secondary bg-error-container/50 border-secondary/20';
    default:         return 'text-on-surface-variant bg-surface-container border-outline-variant';
  }
}

// ─── Loading Skeleton ─────────────────────────────────────────────────────────
function LoadingSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="h-40 rounded-xl bg-surface-container-high w-full" />
      <div className="h-24 rounded-xl bg-surface-container-high w-full" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="h-36 rounded-xl bg-surface-container-high" />
        ))}
      </div>
    </div>
  );
}

// ─── Source Card ──────────────────────────────────────────────────────────────
// Reads from normalised internal model:
// { title, url, domain, excerpt, stance, reliability_score, bias_label }
function SourceCard({ source }) {
  const [expanded, setExpanded] = useState(false);
  const score = source.reliability_score ?? 0;
  const scorePercent = Math.round(score * 100);

  return (
    <div className="bg-surface-container-lowest border border-outline-variant rounded-lg p-4 deep-shadow hover-lift transition-all">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-xs font-bold tracking-wider px-2 py-0.5 rounded-full border uppercase ${getStanceColor(source.stance)}`}>
              {source.stance || 'Neutral'}
            </span>
            {source.domain && (
              <span className="font-mono-technical text-xs text-outline">{source.domain}</span>
            )}
            {source.bias_label && source.bias_label !== 'Unknown' && (
              <span className="text-xs px-2 py-0.5 rounded-full border bg-tertiary-container/20 border-tertiary/20 text-tertiary-container font-semibold">
                {source.bias_label}
              </span>
            )}
          </div>
          <h5 className="font-ui-header font-semibold text-on-surface text-sm line-clamp-2">{source.title}</h5>
        </div>
        <div className="text-right shrink-0 w-16">
          <p className="text-xs font-bold tracking-wide text-on-surface-variant uppercase mb-1">Trust</p>
          <p className="font-mono-technical font-bold text-on-surface">{scorePercent}%</p>
          <div className="w-full h-1.5 bg-surface-container-high rounded-full mt-1 overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${scorePercent}%`,
                backgroundColor: score > 0.8 ? '#0ea5e9' : score > 0.5 ? '#eab308' : '#ef4444',
              }}
            />
          </div>
        </div>
      </div>

      {/* excerpt replaces old .snippet — uses normalised field name */}
      {source.excerpt && (
        <>
          <button
            className="mt-3 text-xs text-on-surface-variant flex items-center gap-1 hover:text-primary transition-colors"
            onClick={() => setExpanded(e => !e)}
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {expanded ? 'Hide excerpt' : 'Show excerpt'}
          </button>
          {expanded && (
            <p className="mt-2 text-sm text-on-surface-variant italic border-l-2 border-outline-variant pl-3 leading-relaxed">
              "{source.excerpt}"
            </p>
          )}
        </>
      )}

      {source.url && (
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`View source: ${source.title}`}
          className="mt-3 inline-flex items-center gap-1 text-xs text-primary hover:underline"
        >
          <ExternalLink size={12} />
          View Source
        </a>
      )}
    </div>
  );
}

// ─── Results Display ──────────────────────────────────────────────────────────
// Reads from normalised internal model:
// { verdict, confidence, reasoning, evidence_citations, claim }
function ResultsDisplay({ result, claim }) {
  const config = getVerdictConfig(result.verdict);
  const evidenceList = result.evidence_citations || [];
  const confidencePct = Math.round((result.confidence ?? 0.5) * 100);
  const confidenceLabel =
    confidencePct >= 80 ? 'High confidence'
    : confidencePct >= 50 ? 'Moderate confidence'
    : 'Low confidence';

  return (
    <div className="space-y-6">
      {/* Verdict Card */}
      <div className={`rounded-xl border p-6 deep-shadow ${config.bg} ${config.border}`}>
        <div className="flex items-center gap-4 mb-4">
          <div className={`p-3 rounded-full bg-white/60 ${config.color}`}>
            <config.Icon size={28} strokeWidth={2} />
          </div>
          <div>
            <p className="text-xs font-bold tracking-widest uppercase text-on-surface-variant">Verdict</p>
            <h3 className={`text-2xl font-display-editorial font-bold ${config.color}`}>{config.label}</h3>
            <p className="text-sm text-on-surface-variant mt-0.5">{config.description}</p>
          </div>
        </div>

        {claim && (
          <blockquote className="font-claim-text italic text-on-surface border-l-4 border-current/30 pl-4 mb-4 leading-relaxed text-lg opacity-80">
            "{claim}"
          </blockquote>
        )}

        {/* Confidence meter — C2 fix */}
        <div className="pt-4 border-t border-current/20">
          <div className="flex items-center justify-between mb-1.5">
            <p className="text-xs font-bold tracking-widest uppercase text-on-surface-variant">Confidence</p>
            <p className="font-mono-technical text-sm font-bold text-on-surface">{confidencePct}%</p>
          </div>
          <div className="h-2 w-full bg-surface-container-high rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${config.bar}`}
              style={{ width: `${confidencePct}%` }}
            />
          </div>
          <p className="text-xs text-on-surface-variant mt-1">{confidenceLabel}</p>
        </div>

        {/* Feature pills — past context / image */}
        {(result.past_context_used || result.image_analyzed) && (
          <div className="flex flex-wrap gap-2 pt-3 border-t border-current/20 mt-1">
            {result.past_context_used && (
              <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-surface-container border border-outline-variant text-on-surface-variant font-semibold">
                <Clock size={11} /> Past context used
              </span>
            )}
            {result.image_analyzed && (
              <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-surface-container border border-outline-variant text-on-surface-variant font-semibold">
                <Image size={11} /> Image analysed
              </span>
            )}
          </div>
        )}
      </div>

      {/* Analysis Summary — uses result.reasoning (was result.explanation) */}
      {result.reasoning && (
        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-6 deep-shadow">
          <h4 className="text-sm font-bold tracking-widest uppercase text-on-surface-variant mb-3">Analysis Summary</h4>
          <p className="text-on-surface leading-relaxed">{result.reasoning}</p>
        </div>
      )}

      {/* Evidence Sources — uses result.evidence_citations (was result.evidence) */}
      {evidenceList.length > 0 && (
        <div>
          <h4 className="text-sm font-bold tracking-widest uppercase text-on-surface-variant mb-4">
            Evidence Sources ({evidenceList.length})
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {evidenceList.map((src, idx) => (
              <SourceCard key={idx} source={src} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Error Display ────────────────────────────────────────────────────────────
function ErrorDisplay({ error, onRetry }) {
  const isTimeout    = error instanceof ApiError && error.status === 408;
  const isServerError = error instanceof ApiError && (error.status >= 500 || error.status === 429);
  const isNetworkError = error.name === 'TypeError';

  const headline = isTimeout     ? 'Request Timed Out'
                 : isServerError ? 'API Unavailable'
                 :                 'Something Went Wrong';

  const body = isTimeout
    ? 'The API server is cold-starting (Render free tier). First requests can take up to 60 s. Wait a moment and retry — subsequent requests will be fast.'
    : isServerError
      ? `The TruthMesh API returned an error (${error.status}). The service may be warming up — free-tier cold starts can take ~60 s.`
      : isNetworkError
        ? 'Could not reach the TruthMesh API. Check your network, or wait a moment and retry.'
        : error.message;

  return (
    <div className="rounded-xl border border-secondary/30 bg-error-container/50 p-8 text-center deep-shadow">
      <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-white/60 text-secondary mb-4">
        <AlertCircle size={28} />
      </div>
      <h3 className="font-display-editorial font-bold text-2xl text-secondary mb-2">
        {headline}
      </h3>
      <p className="text-on-surface-variant text-sm max-w-md mx-auto mb-2">
        {body}
      </p>
      {isServerError && !isTimeout && (
        <p className="font-mono-technical text-xs text-on-surface-variant mb-6 bg-white/40 rounded px-3 py-1.5 inline-block">
          {error.message}
        </p>
      )}
      <div className="flex flex-col sm:flex-row gap-3 justify-center">
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-2 bg-secondary text-on-secondary font-ui-header font-semibold py-2.5 px-6 rounded-lg hover:opacity-90 transition-opacity"
        >
          <Zap size={18} /> Retry
        </button>
        <a
          href="https://github.com/ashhal-kaleem/TruthMesh"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 border border-secondary/40 text-secondary font-ui-header font-semibold py-2.5 px-6 rounded-lg hover:bg-secondary/10 transition-colors"
        >
          <ExternalLink size={18} /> View Repo
        </a>
      </div>
    </div>
  );
}

// ─── Main Analysis Page ───────────────────────────────────────────────────────
export default function Analysis() {
  const location = useLocation();
  const navigate = useNavigate();
  const [claim,    setClaim]    = useState('');
  const [image,    setImage]    = useState(null);

  // Page title
  useEffect(() => { document.title = 'Claim Analysis — TruthMesh'; }, []);

  const [preview,  setPreview]  = useState(null);      // object URL | null
  const [loading,  setLoading]  = useState(false);
  const [result,   setResult]   = useState(null);
  const [error,    setError]    = useState(null);
  const fileRef   = useRef(null);
  const resultRef = useRef(null);   // U9: scroll target after analysis completes

  // Revoke preview URL on unmount / change to avoid memory leaks
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const handleImageSelect = (file) => {
    if (!file || !file.type.startsWith('image/')) return;
    if (preview) URL.revokeObjectURL(preview);
    setImage(file);
    setPreview(URL.createObjectURL(file));
  };

  const clearImage = () => {
    if (preview) URL.revokeObjectURL(preview);
    setImage(null);
    setPreview(null);
    if (fileRef.current) fileRef.current.value = '';
  };

  // I2 fix: ref guard prevents StrictMode double-fire and stale-closure issues.
  const hasFired = useRef(false);

  useEffect(() => {
    if (hasFired.current) return;
    const initial = location.state?.initialClaim;
    if (!initial) return;

    hasFired.current = true;
    // Clear router state before the async call so back-navigation doesn't re-fire
    navigate('.', { replace: true, state: {} });
    setClaim(initial);

    const run = async () => {
      setLoading(true);
      setResult(null);
      setError(null);
      try {
        const data = await checkClaim(initial, image);
        setResult(data);
        // U9: scroll to results after completion
        setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
      } catch (err) {
        setError(err);
        setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
      } finally {
        setLoading(false);
      }
    };
    run();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmitClaim = async (claimText) => {
    const text = (claimText || claim).trim();
    if (!text || loading) return;
    setClaim(text);
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const data = await checkClaim(text, image);
      setResult(data);
      // U9: scroll to results after completion
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
    } catch (err) {
      setError(err);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    handleSubmitClaim(claim);
  };

  return (
    <div className="space-y-8 py-2 md:py-6">
      {/* Header */}
      <div>
        <h2 className="text-3xl md:text-4xl font-display-editorial font-bold text-primary">Claim Analysis</h2>
        <p className="text-on-surface-variant mt-1">Submit a claim to begin multi-agent fact verification.</p>
        {IS_MOCK_MODE && (
          <span className="mt-2 inline-flex items-center gap-2 bg-tertiary-container/30 border border-tertiary/30 text-tertiary-container px-3 py-1 rounded-full text-xs font-bold tracking-wider uppercase">
            ⚙ Dev Mock Mode
          </span>
        )}
      </div>

      {/* Analysis Form */}
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-2 flex flex-col md:flex-row gap-2 deep-shadow focus-within:border-primary focus-within:ring-1 focus-within:ring-primary transition-all">
          <div className="flex-1 relative">
            <Search className="absolute left-4 top-4 text-outline" size={22} />
            <textarea
              value={claim}
              onChange={e => setClaim(e.target.value)}
              disabled={loading}
              rows={3}
              className="w-full min-h-[56px] pl-12 pr-4 py-4 bg-transparent border-none outline-none font-body-main text-on-surface placeholder-outline focus:ring-0 resize-none disabled:opacity-60"
              placeholder="e.g. The Earth's average temperature has risen by 1.1°C since the pre-industrial era..."
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmitClaim(claim);
                }
              }}
            />

            {/* Image preview strip */}
            {preview && (
              <div className="mx-2 mb-2 flex items-center gap-2 bg-surface-container rounded-lg p-2 border border-outline-variant">
                <img src={preview} alt="Attached" className="h-12 w-12 object-cover rounded" />
                <span className="text-xs text-on-surface-variant truncate flex-1">{image?.name}</span>
                <button type="button" onClick={clearImage} className="text-outline hover:text-secondary transition-colors">
                  <XIcon size={16} />
                </button>
              </div>
            )}
          </div>

          <div className="flex items-end justify-end md:flex-col gap-2 p-1">
            {/* Image attach button */}
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={e => handleImageSelect(e.target.files?.[0])}
            />
            <button
              type="button"
              title="Attach image"
              aria-label="Attach image"
              onClick={() => fileRef.current?.click()}
              disabled={loading}
              className={`p-2.5 rounded-lg border transition-colors ${
                image
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-outline-variant text-on-surface-variant hover:text-primary hover:border-primary'
              } disabled:opacity-50`}
            >
              <ImagePlus size={18} />
            </button>

            <button
              type="submit"
              disabled={!claim.trim() || loading}
              className="bg-primary text-on-primary font-ui-header font-semibold py-3 px-8 rounded-lg hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 whitespace-nowrap"
            >
              {loading
                ? <><Loader2 size={18} className="animate-spin" /> Analyzing…</>
                : <><Zap size={18} /> Analyze Claim</>
              }
            </button>
          </div>
        </div>
        <p className="text-xs text-on-surface-variant">
          Press Enter to submit · Shift+Enter for new line{image ? ' · Image attached' : ' · Attach an image with the 📷 button'}.
        </p>
      </form>

      {/* Results — U9: ref attached so scroll-into-view lands here */}
      <div ref={resultRef}>
        {loading && <LoadingSkeleton />}
        {error && !loading && <ErrorDisplay error={error} onRetry={() => handleSubmitClaim(claim)} />}
        {result && !loading && !error && <ResultsDisplay result={result} claim={claim} />}
      </div>

      {/* Empty state */}
      {!loading && !result && !error && (
        <div className="flex flex-col items-center justify-center py-24 text-center gap-4">
          <div className="w-16 h-16 rounded-full bg-surface-container flex items-center justify-center">
            <Search size={28} className="text-outline" />
          </div>
          <h4 className="text-xl font-display-editorial text-on-surface-variant">No analysis yet</h4>
          <p className="text-on-surface-variant text-sm max-w-xs">Submit a claim above to start the multi-agent verification process.</p>
        </div>
      )}
    </div>
  );
}
