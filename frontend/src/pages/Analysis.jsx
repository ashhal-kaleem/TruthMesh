import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Zap, Loader2, AlertCircle, ShieldCheck, ShieldX,
  HelpCircle, ExternalLink, ChevronDown, ChevronUp,
  ImagePlus, X as XIcon, Clock, Image, RotateCcw,
  SlidersHorizontal, ArrowUpDown, Search
} from 'lucide-react';
import { checkClaim, ApiError } from '../api';

// ─── Verdict Config ───────────────────────────────────────────────────────────
function getVerdictConfig(verdict) {
  switch ((verdict || '').toUpperCase().trim()) {
    case 'SUPPORTS':
      return {
        Icon: ShieldCheck,
        color: 'text-primary',
        bg: 'bg-primary/8',
        border: 'border-primary/25',
        bar: 'bg-primary',
        label: 'Supports',
        description: 'The evidence supports this claim.',
      };
    case 'REFUTES':
      return {
        Icon: ShieldX,
        color: 'text-secondary',
        bg: 'bg-error-container/50',
        border: 'border-secondary/25',
        bar: 'bg-secondary',
        label: 'Refutes',
        description: 'The evidence refutes this claim.',
      };
    default:
      return {
        Icon: HelpCircle,
        color: 'text-tertiary',
        bg: 'bg-surface-container',
        border: 'border-outline-variant',
        bar: 'bg-tertiary',
        label: 'Not Enough Info',
        description: 'Insufficient evidence to make a determination.',
      };
  }
}

function getStanceStyle(stance) {
  switch ((stance || '').toUpperCase()) {
    case 'SUPPORTS': return 'text-primary bg-primary/10 border-primary/30';
    case 'REFUTES':  return 'text-secondary bg-error-container/50 border-secondary/30';
    default:         return 'text-on-surface-variant bg-surface-container border-outline-variant';
  }
}

// ─── Confidence helpers ───────────────────────────────────────────────────────
function getConfidenceLabel(pct) {
  if (pct >= 75) return { text: 'High',     color: 'text-primary'   };
  if (pct >= 45) return { text: 'Moderate', color: 'text-tertiary'  };
  return              { text: 'Low',      color: 'text-secondary' };
}

// ─── "What this means" ────────────────────────────────────────────────────────
function getWhatThisMeans(verdict, confidencePct) {
  const v = (verdict || '').toUpperCase().trim();
  const isHigh = confidencePct >= 75;
  const isMed  = confidencePct >= 45;
  if (v === 'SUPPORTS') {
    if (isHigh) return 'Multiple sources consistently back this claim. The retrieved evidence directly supports the stated assertion.';
    if (isMed)  return 'Some evidence supports this claim, though confidence is moderate. Consider reviewing the sources below.';
    return 'Limited evidence supports this claim. Treat the verdict with caution and consult primary sources.';
  }
  if (v === 'REFUTES') {
    if (isHigh) return 'Multiple independent sources contradict this claim. The evidence strongly indicates the assertion is incorrect.';
    if (isMed)  return 'Available evidence leans against this claim, though the analysis is not definitive.';
    return 'Some evidence contradicts this claim, but confidence is low. Additional sources may be needed.';
  }
  return 'The retrieved evidence is inconclusive. The claim may require more authoritative or recent sources to verify.';
}

// ─── Safe lightweight markdown renderer ──────────────────────────────────────
function renderMarkdownSafe(text) {
  if (!text) return [];
  return text.split('\n').filter(line => line.trim()).map((line, idx) => {
    const isBullet = /^\s*[-*]\s/.test(line);
    const cleaned = line.replace(/^\s*[-*]\s/, '');
    const parts = cleaned.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).map((part, pi) => {
      if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={pi}>{part.slice(2, -2)}</strong>;
      if (/^\*[^*]+\*$/.test(part))     return <em key={pi}>{part.slice(1, -1)}</em>;
      return part;
    });
    return isBullet
      ? <li key={idx} className="ml-5 list-disc leading-relaxed">{parts}</li>
      : <p key={idx} className="leading-relaxed">{parts}</p>;
  });
}

// ─── Progress stage hook ──────────────────────────────────────────────────────
const PROGRESS_STAGES = [
  { label: 'Understanding claim'  },
  { label: 'Searching evidence'   },
  { label: 'Evaluating sources'   },
  { label: 'Generating verdict'   },
];

function useProgressStage(loading) {
  const [stage, setStage] = useState(0);
  const timerRef = useRef(null);
  useEffect(() => {
    if (!loading) { setStage(0); clearTimeout(timerRef.current); return; }
    const delays = [3000, 10000, 22000];
    let current = 0;
    const advance = () => {
      current++;
      if (current < PROGRESS_STAGES.length - 1) {
        setStage(current);
        timerRef.current = setTimeout(advance, delays[current]);
      } else {
        setStage(PROGRESS_STAGES.length - 1);
      }
    };
    timerRef.current = setTimeout(advance, delays[0]);
    return () => clearTimeout(timerRef.current);
  }, [loading]);
  return stage;
}

// ─── Delayed state hook ───────────────────────────────────────────────────────
function useDelayedState(loading, delayMs = 30000) {
  const [isDelayed, setIsDelayed] = useState(false);
  useEffect(() => {
    if (!loading) {
      setIsDelayed(false);
      return;
    }
    const timer = setTimeout(() => setIsDelayed(true), delayMs);
    return () => clearTimeout(timer);
  }, [loading, delayMs]);
  return isDelayed;
}

// ─── Analysis progress display ────────────────────────────────────────────────
function AnalysisProgress({ stage, isDelayed }) {
  return (
    <div className="space-y-5" aria-live="polite" aria-label="Analysis in progress">
      {/* Pipeline indicator */}
      <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-5">
        <div className="flex items-center gap-3 mb-5">
          <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
            <Loader2 size={16} className="text-primary animate-spin" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xs font-bold tracking-widest uppercase text-on-surface-variant">Fact-checking</p>
            <p className="text-sm font-semibold text-on-surface mt-0.5">{PROGRESS_STAGES[stage].label}…</p>
          </div>
        </div>

        {/* Stage steps — horizontal on md, wraps on small */}
        <div className="flex flex-wrap items-center gap-y-2 gap-x-1">
          {PROGRESS_STAGES.map((s, i) => {
            const isActive  = i === stage;
            const isDone    = i < stage;
            return (
              <React.Fragment key={s.label}>
                <div
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-all duration-300 ${
                    isActive ? 'bg-primary text-on-primary border-primary'
                    : isDone ? 'bg-primary/10 text-primary border-primary/20'
                             : 'bg-transparent text-outline border-outline-variant/60'
                  }`}
                >
                  {isDone    && <span className="text-primary leading-none" aria-hidden="true">✓</span>}
                  {isActive  && <Loader2 size={10} className="animate-spin shrink-0" aria-hidden="true" />}
                  {s.label}
                </div>
                {i < PROGRESS_STAGES.length - 1 && (
                  <div className={`h-px w-3 shrink-0 transition-colors duration-300 ${i < stage ? 'bg-primary/30' : 'bg-outline-variant/50'}`} />
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Delayed state message */}
        {isDelayed && (
          <div className="mt-5 flex items-start gap-2.5 bg-surface-container/50 p-3 rounded-lg border border-outline-variant/50 animate-in fade-in duration-500">
            <Clock size={16} className="text-tertiary mt-0.5 shrink-0" aria-hidden="true" />
            <div>
              <p className="text-sm font-medium text-on-surface">Analysis is taking longer than expected.</p>
              <p className="text-xs text-on-surface-variant mt-0.5">We're checking multiple sources...</p>
            </div>
          </div>
        )}
      </div>

      {/* Skeleton — same proportions as real result */}
      <div className="space-y-4 animate-pulse">
        <div className="h-40 rounded-xl bg-surface-container-high w-full" />
        <div className="h-28 rounded-xl bg-surface-container-high w-full" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-32 rounded-xl bg-surface-container-high" />
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Source Card ──────────────────────────────────────────────────────────────
function SourceCard({ source }) {
  const [expanded, setExpanded] = useState(false);
  const score        = source.reliability_score ?? 0;
  const scorePercent = Math.round(score * 100);
  const cred         = score > 0.8 ? { label: 'High',   color: 'text-primary',   bar: 'bg-primary'   }
                     : score > 0.5 ? { label: 'Medium', color: 'text-tertiary',  bar: 'bg-tertiary'  }
                     :               { label: 'Low',    color: 'text-secondary', bar: 'bg-secondary' };
  const hasLongExcerpt = source.excerpt && source.excerpt.length > 130;

  return (
    <div className="bg-surface-container-lowest border border-outline-variant rounded-lg p-4 transition-shadow duration-150 hover:shadow-sm">
      {/* Header row: stance + domain + credibility */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          <span className={`shrink-0 text-xs font-bold tracking-wide px-2 py-0.5 rounded-full border uppercase ${getStanceStyle(source.stance)}`}>
            {source.stance || 'Neutral'}
          </span>
          {source.domain && (
            <span className="font-mono-technical text-xs text-outline truncate">{source.domain}</span>
          )}
        </div>
        {/* Credibility — compact */}
        <div className="shrink-0 flex items-center gap-1.5 mt-0.5">
          <span className={`text-xs font-bold ${cred.color}`}>{cred.label}</span>
          <div className="w-12 h-1.5 bg-surface-container-high rounded-full overflow-hidden">
            <div className={`h-full rounded-full ${cred.bar}`} style={{ width: `${scorePercent}%` }} />
          </div>
        </div>
      </div>

      {/* Title — primary interactive element */}
      {source.url ? (
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Open source: ${source.title}`}
          className="group inline-flex items-start gap-1.5 text-sm font-semibold text-on-surface hover:text-primary transition-colors leading-snug"
        >
          <span className="line-clamp-2">{source.title}</span>
          <ExternalLink
            size={12}
            className="shrink-0 text-outline opacity-0 group-hover:opacity-100 transition-opacity mt-0.5"
            aria-hidden="true"
          />
        </a>
      ) : (
        <p className="text-sm font-semibold text-on-surface line-clamp-2 leading-snug">{source.title}</p>
      )}

      {/* Excerpt */}
      {source.excerpt && (
        <div className="mt-2.5">
          <p className={`text-sm text-on-surface-variant leading-relaxed border-l-2 border-outline-variant pl-2.5 ${expanded ? '' : 'line-clamp-2'}`}>
            {source.excerpt}
          </p>
          {hasLongExcerpt && (
            <button
              className="mt-1.5 text-xs text-primary font-medium flex items-center gap-0.5 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded"
              onClick={() => setExpanded(e => !e)}
              aria-expanded={expanded}
            >
              {expanded ? <><ChevronUp size={11} /> Show less</> : <><ChevronDown size={11} /> Read more</>}
            </button>
          )}
        </div>
      )}

      {/* bias_label — only if meaningful and space allows */}
      {source.bias_label && source.bias_label !== 'Unknown' && (
        <p className="mt-2 text-xs text-outline">{source.bias_label}</p>
      )}
    </div>
  );
}

// ─── Evidence Explorer ────────────────────────────────────────────────────────
const STANCE_FILTERS = ['All', 'Supports', 'Refutes', 'Neutral'];
const SORT_OPTIONS   = [
  { value: 'credibility', label: 'Credibility' },
  { value: 'stance',      label: 'Stance'      },
];

function EvidenceExplorer({ sources }) {
  const [filter, setFilter]       = useState('All');
  const [sort,   setSort]         = useState('credibility');
  const [sortOpen, setSortOpen]   = useState(false);
  const sortRef = useRef(null);

  // Close sort dropdown when clicking outside
  useEffect(() => {
    if (!sortOpen) return;
    const handler = (e) => {
      if (sortRef.current && !sortRef.current.contains(e.target)) setSortOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [sortOpen]);

  const filtered = useMemo(() => {
    let list = [...sources];
    if (filter !== 'All') {
      list = list.filter(s => (s.stance || 'Neutral').toUpperCase() === filter.toUpperCase());
    }
    if (sort === 'credibility') {
      list.sort((a, b) => (b.reliability_score ?? 0) - (a.reliability_score ?? 0));
    } else {
      const order = { SUPPORTS: 0, REFUTES: 1, NEUTRAL: 2 };
      list.sort((a, b) => (order[(a.stance || 'NEUTRAL').toUpperCase()] ?? 2) - (order[(b.stance || 'NEUTRAL').toUpperCase()] ?? 2));
    }
    return list;
  }, [sources, filter, sort]);

  const counts = useMemo(() => ({
    All:      sources.length,
    Supports: sources.filter(s => (s.stance || '').toUpperCase() === 'SUPPORTS').length,
    Refutes:  sources.filter(s => (s.stance || '').toUpperCase() === 'REFUTES').length,
    Neutral:  sources.filter(s => !['SUPPORTS', 'REFUTES'].includes((s.stance || '').toUpperCase())).length,
  }), [sources]);

  return (
    <div>
      {/* Section heading + controls in one compact bar */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-4">
        {/* Filter tabs */}
        <div className="flex items-center gap-1" role="group" aria-label="Filter evidence by stance">
          {STANCE_FILTERS.map(f => {
            const count    = counts[f] ?? 0;
            const isActive = filter === f;
            return (
              <button
                key={f}
                onClick={() => setFilter(f)}
                aria-pressed={isActive}
                className={`px-2.5 py-1 rounded text-xs font-semibold transition-all duration-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary ${
                  isActive
                    ? 'bg-primary text-on-primary'
                    : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container'
                }`}
              >
                {f}
                <span className={`ml-1 font-mono-technical ${isActive ? 'opacity-75' : 'text-outline'}`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Sort */}
        <div className="relative" ref={sortRef}>
          <button
            onClick={() => setSortOpen(o => !o)}
            aria-haspopup="listbox"
            aria-expanded={sortOpen}
            className="inline-flex items-center gap-1 text-xs text-on-surface-variant hover:text-on-surface font-medium border border-outline-variant px-2.5 py-1 rounded-lg hover:bg-surface-container transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
          >
            <ArrowUpDown size={11} aria-hidden="true" />
            {SORT_OPTIONS.find(o => o.value === sort)?.label}
          </button>
          {sortOpen && (
            <div className="absolute right-0 top-full mt-1 bg-surface-container-lowest border border-outline-variant rounded-lg shadow-md z-10 min-w-[130px] py-1 overflow-hidden">
              {SORT_OPTIONS.map(o => (
                <button
                  key={o.value}
                  role="option"
                  aria-selected={sort === o.value}
                  onClick={() => { setSort(o.value); setSortOpen(false); }}
                  className={`w-full text-left px-3 py-1.5 text-xs font-medium hover:bg-surface-container transition-colors ${sort === o.value ? 'text-primary' : 'text-on-surface-variant'}`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Count label */}
      <p className="text-xs text-outline mb-3 font-mono-technical">
        Showing {filtered.length} of {sources.length} source{sources.length !== 1 ? 's' : ''}
      </p>

      {/* Cards */}
      {filtered.length === 0 ? (
        <p className="text-sm text-on-surface-variant py-6 text-center">No {filter.toLowerCase()} sources in this analysis.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {filtered.map((src, idx) => <SourceCard key={idx} source={src} />)}
        </div>
      )}
    </div>
  );
}

// ─── Results Display ──────────────────────────────────────────────────────────
function ResultsDisplay({ result, claim, onCheckAnother }) {
  const config        = getVerdictConfig(result.verdict);
  const evidenceList  = result.evidence_citations || [];
  const confidencePct = Math.round((result.confidence ?? 0.5) * 100);
  const confLabel     = getConfidenceLabel(confidencePct);
  const whatThisMeans = getWhatThisMeans(result.verdict, confidencePct);
  const reasoningNodes = renderMarkdownSafe(result.reasoning);
  const hasBullets     = result.reasoning && /^\s*[-*]\s/m.test(result.reasoning);

  return (
    <div className="space-y-5 animate-in fade-in duration-500">

      {/* ── Verdict block ── primary visual */}
      <div className={`rounded-xl border p-6 ${config.bg} ${config.border}`}>
        {/* Verdict + confidence in one row */}
        <div className="flex items-start gap-5 mb-5">
          {/* Icon */}
          <div className={`p-2.5 rounded-xl bg-white/50 ${config.color} shrink-0`}>
            <config.Icon size={26} strokeWidth={1.75} aria-hidden="true" />
          </div>

          {/* Verdict label */}
          <div className="flex-1 min-w-0">
            <p className="text-xs font-bold tracking-widest uppercase text-on-surface-variant mb-1">Verdict</p>
            <h3 className={`text-3xl md:text-4xl font-display-editorial font-bold leading-none ${config.color}`}>
              {config.label}
            </h3>
            <p className="text-sm text-on-surface-variant mt-1.5">{config.description}</p>
          </div>

          {/* Confidence — secondary, right-aligned */}
          <div className="shrink-0 text-right hidden sm:block">
            <p className="text-xs font-bold tracking-widest uppercase text-on-surface-variant mb-1">Confidence</p>
            <p className={`text-2xl font-display-editorial font-bold leading-none ${confLabel.color}`}>
              {confidencePct}%
            </p>
            <p className={`text-xs font-semibold mt-1 ${confLabel.color}`}>{confLabel.text}</p>
          </div>
        </div>

        {/* Confidence bar — visible always */}
        <div className="mb-4">
          <div className="h-1.5 w-full bg-surface-container-high rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${config.bar}`}
              style={{ width: `${confidencePct}%` }}
              role="progressbar"
              aria-valuenow={confidencePct}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`Confidence: ${confidencePct}%`}
            />
          </div>
          {/* Mobile confidence label */}
          <div className="flex justify-between items-center mt-1 sm:hidden">
            <span className="text-xs text-on-surface-variant">Confidence</span>
            <span className={`text-xs font-semibold ${confLabel.color}`}>{confidencePct}% · {confLabel.text}</span>
          </div>
        </div>

        {/* Submitted claim */}
        {claim && (
          <blockquote className="font-claim-text text-on-surface border-l-2 border-current/25 pl-4 leading-relaxed text-base opacity-75 mb-4">
            "{claim}"
          </blockquote>
        )}

        {/* What this means */}
        <p className="text-sm text-on-surface leading-relaxed">{whatThisMeans}</p>

        {/* Feature pills */}
        {(result.past_context_used || result.image_analyzed) && (
          <div className="flex flex-wrap gap-2 pt-4 mt-4 border-t border-current/15">
            {result.past_context_used && (
              <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-surface-container border border-outline-variant text-on-surface-variant font-medium">
                <Clock size={11} aria-hidden="true" /> Past context used
              </span>
            )}
            {result.image_analyzed && (
              <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-surface-container border border-outline-variant text-on-surface-variant font-medium">
                <Image size={11} aria-hidden="true" /> Image analysed
              </span>
            )}
          </div>
        )}
      </div>

      {/* ── Reasoning — visually secondary: no card border, uses surface bg ── */}
      {result.reasoning && (
        <div className="px-1">
          <h4 className="text-xs font-bold tracking-widest uppercase text-on-surface-variant mb-3">Analysis Summary</h4>
          <div className={`text-sm text-on-surface ${hasBullets ? '' : 'space-y-3'}`}>
            {hasBullets
              ? <ul className="space-y-1.5 pl-1">{reasoningNodes}</ul>
              : reasoningNodes
            }
          </div>
        </div>
      )}

      {/* ── Evidence — distinct section with its own card ── */}
      {evidenceList.length > 0 && (
        <div className="border-t border-outline-variant pt-5">
          <h4 className="text-xs font-bold tracking-widest uppercase text-on-surface-variant mb-4">
            Evidence &amp; Sources
          </h4>
          <EvidenceExplorer sources={evidenceList} />
        </div>
      )}

      {/* ── Check another claim ── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pt-4 border-t border-outline-variant">
        <p className="text-xs text-outline">Analysis complete · Results are generated by AI and should be independently verified for critical decisions.</p>
        <button
          onClick={onCheckAnother}
          className="shrink-0 inline-flex items-center gap-2 border border-primary text-primary font-ui-header font-semibold py-2 px-5 rounded-lg hover:bg-primary hover:text-on-primary transition-all duration-150 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
        >
          <RotateCcw size={14} aria-hidden="true" /> Check another claim
        </button>
      </div>
    </div>
  );
}

// ─── Error Display ────────────────────────────────────────────────────────────
function friendlyError(error) {
  if (error instanceof ApiError) {
    if (error.status === 408) return { headline: 'Request Timed Out', body: 'The server is taking longer than expected — this can happen on first load. Please wait a moment and try again.' };
    if (error.status === 429) return { headline: 'Too Many Requests', body: 'Please wait a moment before sending another request.' };
    if (error.status === 401) return { headline: 'Authentication Required', body: 'Your session has expired. Please sign in to continue.' };
    if (error.status >= 500)  return { headline: 'Service Unavailable', body: 'The verification service is temporarily unavailable. Please try again shortly.' };
  }
  return { headline: 'Analysis Failed', body: 'An unexpected issue occurred while verifying this claim. Please try again.' };
}

function ErrorDisplay({ error, onRetry }) {
  const { headline, body } = friendlyError(error);
  return (
    <div className="rounded-xl border border-secondary/25 bg-error-container/40 p-8 text-center">
      <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-surface-container text-secondary mb-4">
        <AlertCircle size={22} aria-hidden="true" />
      </div>
      <h3 className="font-display-editorial font-bold text-xl text-secondary mb-2">{headline}</h3>
      <p className="text-on-surface-variant text-sm max-w-sm mx-auto mb-6 leading-relaxed">{body}</p>
      <button
        onClick={onRetry}
        className="inline-flex items-center gap-2 border border-secondary text-secondary font-ui-header font-semibold py-2 px-5 rounded-lg hover:bg-secondary hover:text-on-secondary transition-all duration-150 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary focus-visible:ring-offset-2"
      >
        <RotateCcw size={14} aria-hidden="true" /> Try again
      </button>
    </div>
  );
}

// ─── Main Analysis Page ───────────────────────────────────────────────────────
export default function Analysis() {
  const location  = useLocation();
  const navigate  = useNavigate();
  const [claim,   setClaim]   = useState('');
  const [image,   setImage]   = useState(null);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result,  setResult]  = useState(null);
  const [error,   setError]   = useState(null);
  const [touched, setTouched] = useState(false); // track if user tried to submit empty
  const fileRef   = useRef(null);
  const resultRef = useRef(null);
  const inputRef  = useRef(null);

  const progressStage = useProgressStage(loading);
  const isDelayed = useDelayedState(loading, 30000);

  useEffect(() => { document.title = 'Claim Analysis — TruthMesh'; }, []);
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

  const hasFired = useRef(false);
  useEffect(() => {
    if (hasFired.current) return;
    const initial = location.state?.initialClaim;
    if (!initial) return;
    hasFired.current = true;
    navigate('.', { replace: true, state: {} });
    setClaim(initial);
    runAnalysis(initial);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const runAnalysis = async (text) => {
    if (!text?.trim() || loading) return;
    setLoading(true);
    setResult(null);
    setError(null);
    setTouched(false);
    try {
      const data = await checkClaim(text.trim(), image);
      setResult(data);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
    } catch (err) {
      setError(err);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!claim.trim()) { setTouched(true); inputRef.current?.focus(); return; }
    runAnalysis(claim);
  };

  const handleCheckAnother = () => {
    setResult(null);
    setError(null);
    setClaim('');
    clearImage();
    setTouched(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    setTimeout(() => inputRef.current?.focus(), 120);
  };

  const showEmptyValidation = touched && !claim.trim() && !loading;

  return (
    <div className="space-y-6 py-2 md:py-6">
      {/* Page heading */}
      <div>
        <h2 className="text-3xl md:text-4xl font-display-editorial font-bold text-on-surface">Claim Analysis</h2>
        <p className="text-on-surface-variant text-sm mt-1">
          Enter any factual claim and TruthMesh will verify it against multiple sources.
        </p>
      </div>

      {/* ── Input form ── */}
      <form onSubmit={handleSubmit} noValidate>
        <div
          className={`bg-surface-container-lowest border-2 rounded-xl transition-all duration-150 deep-shadow ${
            showEmptyValidation
              ? 'border-secondary/60'
              : 'border-outline-variant focus-within:border-primary focus-within:shadow-[0_0_0_3px_rgba(0,83,91,0.09)]'
          }`}
        >
          <div className="flex flex-col md:flex-row gap-0">
            {/* Textarea side */}
            <div className="flex-1 relative">
              <Search
                className="absolute left-4 top-4 text-outline pointer-events-none"
                size={20}
                aria-hidden="true"
              />
              <textarea
                ref={inputRef}
                value={claim}
                onChange={e => {
                  setClaim(e.target.value);
                  if (touched && e.target.value.trim()) setTouched(false);
                  e.target.style.height = 'auto';
                  e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px';
                }}
                disabled={loading}
                rows={3}
                aria-label="Claim to fact-check"
                aria-invalid={showEmptyValidation}
                aria-describedby={showEmptyValidation ? 'claim-error' : undefined}
                className="w-full min-h-[72px] max-h-[200px] pl-12 pr-4 py-4 bg-transparent border-none outline-none font-body-main text-on-surface placeholder-outline focus:ring-0 resize-none disabled:opacity-60 overflow-y-auto leading-relaxed"
                placeholder="e.g. The Earth's average temperature has risen by 1.1°C since the pre-industrial era…"
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(e); }
                }}
              />

              {/* Image preview */}
              {preview && (
                <div className="mx-3 mb-3 flex items-center gap-2.5 bg-surface-container rounded-lg px-3 py-2 border border-outline-variant">
                  <img src={preview} alt="Attached" className="h-10 w-10 object-cover rounded flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-on-surface truncate">{image?.name}</p>
                    <p className="text-xs text-outline">Image attached</p>
                  </div>
                  <button
                    type="button"
                    onClick={clearImage}
                    className="text-outline hover:text-secondary transition-colors p-1 rounded focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-secondary"
                    aria-label="Remove attached image"
                  >
                    <XIcon size={15} />
                  </button>
                </div>
              )}
            </div>

            {/* md+ vertical divider */}
            {!preview && <div className="hidden md:block w-px bg-outline-variant/60 self-stretch my-3" />}

            {/* Controls column */}
            <div className="flex items-end md:flex-col justify-end gap-2 p-2.5">
              {/* Image attach */}
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={e => handleImageSelect(e.target.files?.[0])}
                aria-label="Attach an image"
              />
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                disabled={loading}
                title={image ? 'Image attached — click to replace' : 'Attach an image for analysis'}
                aria-label={image ? 'Image attached — click to replace' : 'Attach an image'}
                className={`p-2 rounded-lg border transition-all duration-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary ${
                  image
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-outline-variant text-outline hover:text-primary hover:border-primary/50'
                } disabled:opacity-40`}
              >
                <ImagePlus size={16} aria-hidden="true" />
              </button>

              {/* Submit */}
              <button
                type="submit"
                disabled={loading}
                className="bg-primary text-on-primary font-ui-header font-semibold h-10 px-6 rounded-lg hover:opacity-90 active:opacity-80 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-150 flex items-center gap-2 text-sm whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
              >
                {loading
                  ? <><Loader2 size={15} className="animate-spin" aria-hidden="true" /> Analysing…</>
                  : <><Zap size={15} aria-hidden="true" /> Analyse</>
                }
              </button>
            </div>
          </div>
        </div>

        {/* Validation message or keyboard hint */}
        <div className="mt-1.5 min-h-[18px]">
          {showEmptyValidation ? (
            <p id="claim-error" className="text-xs text-secondary font-medium" role="alert">
              Please enter a claim before submitting.
            </p>
          ) : (
            <p className="text-xs text-outline">
              <kbd className="font-mono-technical bg-surface-container px-1 py-0.5 rounded border border-outline-variant">Enter</kbd> to submit
              {' · '}
              <kbd className="font-mono-technical bg-surface-container px-1 py-0.5 rounded border border-outline-variant">Shift+Enter</kbd> for new line
            </p>
          )}
        </div>
      </form>

      {/* ── Results / loading / error area ── */}
      <div ref={resultRef}>
        {loading && <AnalysisProgress stage={progressStage} isDelayed={isDelayed} />}
        {error  && !loading && <ErrorDisplay error={error} onRetry={() => runAnalysis(claim)} />}
        {result && !loading && !error && (
          <ResultsDisplay result={result} claim={claim} onCheckAnother={handleCheckAnother} />
        )}
      </div>

      {/* ── Empty state ── */}
      {!loading && !result && !error && (
        <div className="flex flex-col items-center justify-center py-10 text-center gap-2.5" aria-hidden="true">
          <div className="w-12 h-12 rounded-full bg-surface-container flex items-center justify-center">
            <Search size={22} className="text-outline" />
          </div>
          <p className="text-base font-display-editorial text-on-surface-variant">Enter a claim above to begin</p>
          <p className="text-sm text-outline max-w-xs">
            TruthMesh searches multiple sources and returns a structured, evidence-backed verdict.
          </p>
        </div>
      )}
    </div>
  );
}
