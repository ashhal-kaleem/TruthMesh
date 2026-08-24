import React, { useState, useEffect } from 'react';
import { Globe, ShieldCheck, Wifi, WifiOff, Loader2, CheckCircle2, Info } from 'lucide-react';
import { pingApi } from '../api';

// ─── Runtime config (never hardcoded) ────────────────────────────────────────
const API_BASE     = import.meta.env.VITE_API_BASE     || 'http://localhost:8000';
const IS_MOCK_MODE = import.meta.env.VITE_MOCK_MODE === 'true';

// ─── API health check ─────────────────────────────────────────────────────────
function PingButton() {
  const [state, setState] = useState('loading'); // idle | loading | ok | error
  const [info,  setInfo]  = useState('');

  const doPing = async () => {
    setState('loading');
    setInfo('');
    try {
      const { latencyMs } = await pingApi();
      setState('ok');
      setInfo(`${latencyMs} ms`);
    } catch (err) {
      setState('error');
      setInfo('');
    }
  };

  // Auto-check on first render so the status is immediately visible.
  useEffect(() => { doPing(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handlePing = () => doPing();

  return (
    <div className="flex items-center gap-3 bg-surface-container-low border border-outline-variant rounded-lg p-1 pr-4 transition-all">
      <button
        onClick={handlePing}
        disabled={state === 'loading'}
        aria-label="Ping API"
        className="inline-flex items-center justify-center gap-2 text-sm font-semibold border border-outline-variant bg-surface-container-lowest px-3 py-1.5 rounded hover:border-primary/50 hover:text-primary transition-all disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary shadow-sm"
      >
        {state === 'loading'
          ? <><Loader2 size={14} className="animate-spin" aria-hidden="true" /> Pinging…</>
          : <><Wifi size={14} aria-hidden="true" /> Ping API</>
        }
      </button>

      {/* Result indicator */}
      {state === 'idle' && (
        <span className="text-xs font-mono-technical text-outline">Ready</span>
      )}
      {state === 'ok' && (
        <span className="flex items-center gap-1 text-xs text-primary font-bold">
          <CheckCircle2 size={14} aria-hidden="true" /> Online <span className="font-mono-technical opacity-70 ml-1">{info}</span>
        </span>
      )}
      {state === 'error' && (
        <span className="flex items-center gap-1 text-xs text-secondary font-bold">
          <WifiOff size={14} aria-hidden="true" /> Unreachable
        </span>
      )}
    </div>
  );
}

// ─── Setting row layout ───────────────────────────────────────────────────────
function SettingRow({ label, description, children }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 py-5 border-b border-outline-variant last:border-none">
      <div className="flex-1 min-w-0">
        <p className="font-ui-header font-semibold text-on-surface text-sm">{label}</p>
        {description && <p className="text-on-surface-variant text-sm mt-0.5">{description}</p>}
      </div>
      <div className="shrink-0 min-w-0 max-w-full sm:max-w-[260px] overflow-hidden">{children}</div>
    </div>
  );
}

// ─── Main Settings page ───────────────────────────────────────────────────────
export default function Settings() {
  useEffect(() => { document.title = 'Settings — TruthMesh'; }, []);

  return (
    <div className="space-y-6 py-2 md:py-6 animate-in fade-in duration-500">
      <div>
        <h2 className="text-3xl md:text-4xl font-display-editorial font-bold text-on-surface">Settings</h2>
        <p className="text-on-surface-variant text-sm mt-1">API configuration and system information.</p>
      </div>

      {/* API Configuration */}
      <div className="bg-surface-container-lowest border border-outline-variant rounded-xl px-5 sm:px-6 deep-shadow">
        <div className="py-5 border-b border-outline-variant">
          <h3 className="font-display-editorial text-lg font-bold text-on-surface flex items-center gap-2">
            <Globe size={18} className="text-outline" aria-hidden="true" /> API Configuration
          </h3>
          <p className="text-on-surface-variant text-sm mt-1">Connection details for the TruthMesh backend.</p>
        </div>

        <SettingRow
          label="API Endpoint"
          description="The active claim-verification backend URL."
        >
          <span
            title={API_BASE}
            className="font-mono-technical text-xs bg-surface-container px-3 py-1.5 rounded border border-outline-variant text-on-surface block truncate w-full"
          >
            {API_BASE}
          </span>
        </SettingRow>

        <SettingRow
          label="API Status"
          description="Check whether the backend is reachable and responsive."
        >
          <PingButton />
        </SettingRow>

        <SettingRow
          label="Request Timeout"
          description="Maximum wait time before a request is aborted."
        >
          <span className="font-mono-technical text-xs text-on-surface bg-surface-container px-3 py-1.5 rounded border border-outline-variant inline-block text-right">
            120s <span className="opacity-60">(analysis)</span> · 15s <span className="opacity-60">(auth)</span>
          </span>
        </SettingRow>

        {IS_MOCK_MODE && (
          <SettingRow
            label="Mock Mode Active"
            description="The API is currently returning mock responses. Disable in .env to use the real API."
          >
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold tracking-wider px-2 py-1 rounded border uppercase bg-tertiary-container/30 border-tertiary/30 text-tertiary-container">
                Mock Mode
              </span>
              <Info size={16} className="text-outline" aria-label="Controlled by VITE_MOCK_MODE" />
            </div>
          </SettingRow>
        )}
      </div>

      {/* About */}
      <div className="bg-primary-container text-on-primary-container rounded-xl p-6 deep-shadow relative overflow-hidden">
        <div className="absolute -right-8 -top-8 w-40 h-40 bg-primary-fixed opacity-10 rounded-full blur-2xl" aria-hidden="true" />
        <div className="relative z-10">
          <h3 className="font-display-editorial text-lg font-bold text-on-primary-fixed mb-2 flex items-center gap-2">
            <ShieldCheck size={18} aria-hidden="true" /> About TruthMesh
          </h3>
          <p className="text-sm opacity-80 leading-relaxed mb-5 max-w-2xl">
            A multi-agent AI fact-checking system combining advanced evidence retrieval to verify factual claims across diverse domains.
            Built with a three-stage pipeline: claim decomposition, multi-source retrieval, and LLM-based synthesis.
          </p>
          <div className="flex flex-wrap gap-4 text-xs font-mono-technical opacity-75">
            <span>React 18 + Vite</span>
            <span>FastAPI backend</span>
          </div>
          <a
            href="https://github.com/ashhal-kaleem/TruthMesh"
            target="_blank"
            rel="noopener noreferrer"
            className="mt-4 inline-flex items-center gap-1.5 text-xs font-bold text-on-primary-fixed hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-on-primary-fixed rounded"
          >
            View on GitHub →
          </a>
        </div>
      </div>
    </div>
  );
}
