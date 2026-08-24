import React, { useState, useEffect } from 'react';
import { Zap, Globe, ShieldCheck, Moon, Sun, Monitor, Sliders, Info,
         Wifi, WifiOff, Loader2, CheckCircle2, Clock } from 'lucide-react';
import { pingApi, ApiError } from '../api';

const IS_MOCK_MODE = import.meta.env.VITE_MOCK_MODE === 'true';

// ─── localStorage helpers ──────────────────────────────────────────────────────
const STORAGE_KEY = 'truthmesh_prefs';
function loadPrefs() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); }
  catch { return {}; }
}
function savePrefs(prefs) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
}

// ─── Sub-components ────────────────────────────────────────────────────────────
function SettingRow({ label, description, children, tag }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 py-5 border-b border-outline-variant last:border-none">
      <div className="flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="font-ui-header font-semibold text-on-surface text-sm">{label}</p>
          {tag === 'coming-soon' && (
            <span className="text-xs px-2 py-0.5 rounded-full border bg-tertiary-container/20 border-tertiary/20 text-tertiary-container font-bold tracking-wider uppercase">
              Coming soon
            </span>
          )}
          {tag === 'local' && (
            <span className="text-xs px-2 py-0.5 rounded-full border bg-surface-container border-outline-variant text-outline font-semibold">
              local only
            </span>
          )}
        </div>
        {description && <p className="text-on-surface-variant text-sm mt-0.5">{description}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

function Toggle({ value, onChange, disabled }) {
  return (
    <button
      role="switch"
      aria-checked={value}
      disabled={disabled}
      onClick={() => !disabled && onChange(!value)}
      className={`relative w-12 h-6 rounded-full transition-colors ${
        disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'
      } ${value ? 'bg-primary' : 'bg-surface-container-high border border-outline-variant'}`}
    >
      <span
        className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${value ? 'translate-x-6' : 'translate-x-0'}`}
      />
    </button>
  );
}

// ─── API health check button ───────────────────────────────────────────────────
function PingButton() {
  const [state, setState] = useState('idle'); // idle | loading | ok | error
  const [info,  setInfo]  = useState('');

  const handlePing = async () => {
    setState('loading');
    setInfo('');
    try {
      const { latencyMs } = await pingApi();
      setState('ok');
      setInfo(`${latencyMs} ms`);
    } catch (err) {
      setState('error');
      setInfo(err instanceof ApiError ? `${err.status}` : 'network error');
    }
  };

  return (
    <div className="flex items-center gap-3">
      {state === 'ok'    && <span className="flex items-center gap-1 text-xs text-cyan-700 font-semibold"><CheckCircle2 size={14}/> Online · {info}</span>}
      {state === 'error' && <span className="flex items-center gap-1 text-xs text-secondary font-semibold"><WifiOff size={14}/> Unreachable {info && `(${info})`}</span>}
      <button
        onClick={handlePing}
        disabled={state === 'loading'}
        className="inline-flex items-center gap-2 text-sm font-semibold border border-outline-variant px-3 py-1.5 rounded-lg hover:bg-surface-container transition-colors disabled:opacity-50"
      >
        {state === 'loading'
          ? <><Loader2 size={14} className="animate-spin"/> Pinging…</>
          : <><Wifi size={14}/> Ping API</>}
      </button>
    </div>
  );
}

// ─── Main Settings page ────────────────────────────────────────────────────────
export default function Settings() {
  useEffect(() => { document.title = 'Settings — TruthMesh'; }, []);

  // Coming Soon controls are read-only — values are seeded from localStorage for
  // display but no setter is exposed, so they can never be mutated or re-persisted.
  const saved = loadPrefs();
  const autoSave         = saved.autoSave         ?? true;
  const notifications    = saved.notifications    ?? false;
  const confidenceFilter = saved.confidenceFilter ?? 0.5;

  // Theme application removed — dark mode not yet implemented in the design system.
  // The theme control is disabled in the UI (Coming Soon).

  return (
    <div className="space-y-8 py-2 md:py-6">
      <div>
        <h2 className="text-3xl md:text-4xl font-display-editorial font-bold text-primary">Settings</h2>
        <p className="text-on-surface-variant mt-1">Manage your TruthMesh preferences.</p>
      </div>

      {/* API / System Info */}
      <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-6 deep-shadow">
        <h3 className="font-display-editorial text-xl font-bold text-primary mb-1 flex items-center gap-2">
          <Globe size={20} /> API Configuration
        </h3>
        <p className="text-on-surface-variant text-sm mb-6">Connection details for the TruthMesh verification API.</p>

        <SettingRow label="API Endpoint" description="The backend claim-verification endpoint.">
          <span className="font-mono-technical text-xs bg-surface-container px-3 py-1.5 rounded border border-outline-variant text-on-surface-variant break-all text-right max-w-xs block">
            https://truthmesh-api.onrender.com
          </span>
        </SettingRow>

        <SettingRow label="API Status" description="Check whether the live API is reachable and warm.">
          <PingButton />
        </SettingRow>

        <SettingRow label="Developer Mock Mode" description="When enabled, returns realistic mock data instead of calling the live API. Toggle via VITE_MOCK_MODE in .env and restart the dev server.">
          <div className="flex items-center gap-2">
            <span className={`text-xs font-bold tracking-wider px-2 py-1 rounded-full border uppercase ${IS_MOCK_MODE ? 'bg-tertiary-container/30 border-tertiary/30 text-tertiary-container' : 'bg-cyan-50 border-cyan-200 text-cyan-700'}`}>
              {IS_MOCK_MODE ? 'Mock Mode ON' : 'Live API ON'}
            </span>
            <Info size={16} className="text-outline" title="Change VITE_MOCK_MODE in your .env file and restart the dev server." />
          </div>
        </SettingRow>

        <SettingRow label="Request Timeout" description="Maximum wait time before a request is aborted. Free-tier cold starts may take up to 60 s.">
          <span className="font-mono-technical text-sm text-on-surface-variant bg-surface-container px-3 py-1.5 rounded border border-outline-variant">
            60 s (check_claim) · 15 s (auth)
          </span>
        </SettingRow>
      </div>

      {/* Preferences */}
      <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-6 deep-shadow">
        <h3 className="font-display-editorial text-xl font-bold text-primary mb-1 flex items-center gap-2">
          <Sliders size={20} /> Preferences
        </h3>
        <p className="text-on-surface-variant text-sm mb-6">These preferences are saved locally in your browser.</p>

        <SettingRow
          label="Theme"
          description="Dark mode is not yet implemented in the design system. Light mode only."
          tag="coming-soon"
        >
          <div className="flex gap-2 opacity-50 pointer-events-none" aria-disabled="true">
            {[['light', Sun], ['dark', Moon], ['system', Monitor]].map(([val, Icon]) => (
              <button
                key={val}
                disabled
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm font-semibold cursor-not-allowed ${
                  val === 'light'
                    ? 'bg-primary text-on-primary border-primary'
                    : 'bg-surface-container border-outline-variant text-on-surface-variant'
                }`}
              >
                <Icon size={15} />
                <span className="capitalize">{val}</span>
              </button>
            ))}
          </div>
        </SettingRow>

        <SettingRow
          label="Auto-save analyses"
          description="Backend saves every verified claim automatically (authenticated users). This toggle is reserved for a future client-side opt-out."
          tag="coming-soon"
        >
          <Toggle value={autoSave} onChange={() => {}} disabled />
        </SettingRow>

        <SettingRow
          label="Browser notifications"
          description="Show a notification when a long analysis finishes. Requires browser permission grant."
          tag="coming-soon"
        >
          <Toggle value={notifications} onChange={() => {}} disabled />
        </SettingRow>

        <SettingRow
          label="Minimum reliability filter"
          description={`Hide evidence sources with a reliability score below ${Math.round(confidenceFilter * 100)}%. Saved locally — not yet applied to API results.`}
          tag="coming-soon"
        >
          <div className="flex items-center gap-3 w-48">
            <input
              type="range" min={0} max={1} step={0.05}
              value={confidenceFilter}
              onChange={() => {}}
              className="flex-1 accent-primary opacity-50 cursor-not-allowed"
              disabled
            />
            <span className="font-mono-technical text-sm text-on-surface w-10 text-right">
              {Math.round(confidenceFilter * 100)}%
            </span>
          </div>
        </SettingRow>
      </div>

      {/* About */}
      <div className="bg-primary-container text-on-primary-container rounded-xl p-6 deep-shadow relative overflow-hidden">
        <div className="absolute -right-8 -top-8 w-40 h-40 bg-primary-fixed opacity-10 rounded-full blur-2xl" />
        <div className="relative z-10">
          <h3 className="font-display-editorial text-xl font-bold text-on-primary-fixed mb-2 flex items-center gap-2">
            <ShieldCheck size={20} /> About TruthMesh
          </h3>
          <p className="text-sm opacity-80 leading-relaxed mb-4">
            A multi-agent AI fact-checking system combining advanced evidence retrieval to verify factual claims across diverse domains.
          </p>
          <div className="flex flex-wrap gap-4 text-xs font-mono-technical opacity-70">
            <span>API: v3.0</span>
            <span>Frontend: React 18 + Vite</span>
            <span>Author: Ashhal Kaleem</span>
          </div>
          <a
            href="https://github.com/ashhal-kaleem/TruthMesh"
            target="_blank"
            rel="noopener noreferrer"
            className="mt-4 inline-flex items-center gap-1.5 text-xs font-bold text-on-primary-fixed underline hover:no-underline"
          >
            <Zap size={12} /> View on GitHub →
          </a>
        </div>
      </div>
    </div>
  );
}
