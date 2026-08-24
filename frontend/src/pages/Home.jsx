import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Zap, ArrowRight, ShieldCheck, Search, Database, Layers, ChevronRight } from 'lucide-react';
import FactCard from '../components/FactCard';

// ─── Example claims shown on the home page ────────────────────────────────────
// These are curated suggestions only — NOT live results.
// Clicking a card navigates to /analysis with the claim pre-filled for live verification.
const EXAMPLE_CLAIMS = [
  {
    verdict: 'SUPPORTS',
    title: 'Global supply chain disruptions projected to ease by Q3 based on leading maritime shipping indexes.',
  },
  {
    verdict: 'REFUTES',
    title: 'New breakthrough battery tech promises 1000x capacity increase with zero rare earth metals.',
  },
  {
    verdict: 'NOT ENOUGH INFO',
    title: 'Proposed central bank digital currency (CBDC) implementation timeline shifted to late 2026.',
  },
];

// ─── Capability cards ─────────────────────────────────────────────────────────
const CAPABILITIES = [
  {
    Icon: Search,
    title: 'Multi-source retrieval',
    body: 'Queries multiple independent sources per subclaim, cross-referencing evidence before rendering a verdict.',
  },
  {
    Icon: Layers,
    title: 'Three-call agent pipeline',
    body: 'Decompose → Retrieve → Synthesise. Each stage uses a dedicated LLM call with structured outputs.',
  },
  {
    Icon: Database,
    title: 'RAG + vector store',
    body: 'Augments web retrieval with a local FEVEROUS/SciFact vector store for domain-specific grounding.',
  },
  {
    Icon: ShieldCheck,
    title: 'Credibility scoring',
    body: 'Each source is rated High / Medium / Low based on domain authority, bias label, and excerpt relevance.',
  },
];

export default function Home() {
  const [claim, setClaim] = useState('');
  const navigate = useNavigate();

  useEffect(() => { document.title = 'TruthMesh AI — Fact Checker'; }, []);

  const handleAnalyze = (e) => {
    e.preventDefault();
    if (!claim.trim()) return;
    navigate('/analysis', { state: { initialClaim: claim } });
  };

  const handleExampleClick = (title) => {
    navigate('/analysis', { state: { initialClaim: title } });
  };

  return (
    <div className="space-y-10 animate-in fade-in duration-500">
      {/* ── Hero ── */}
      <section className="pt-6 md:pt-14">
        {/* Eyebrow */}
        <p className="text-xs font-bold tracking-widest uppercase text-primary mb-4 font-ui-header">
          AI Fact-Checking · Multi-Agent Verification
        </p>

        <h2 className="text-4xl md:text-5xl font-display-editorial font-bold text-on-surface mb-4 leading-tight">
          Verify the{' '}
          <span className="text-primary">Unverifiable.</span>
        </h2>
        <p className="text-base text-on-surface-variant max-w-xl mb-8 leading-relaxed">
          Paste any claim. TruthMesh retrieves evidence from multiple independent sources, evaluates credibility, and returns a structured verdict.
        </p>

        {/* Claim input */}
        <div className="max-w-3xl">
          <form
            onSubmit={handleAnalyze}
            className="bg-surface-container-lowest border-2 border-outline-variant rounded-xl transition-all duration-150 focus-within:border-primary focus-within:shadow-[0_0_0_3px_rgba(0,83,91,0.10)] deep-shadow"
          >
            <div className="flex flex-col md:flex-row gap-0">
              <div className="flex-1 relative">
                <Search
                  className="absolute left-4 top-1/2 -translate-y-1/2 text-outline pointer-events-none"
                  size={20}
                  aria-hidden="true"
                />
                <input
                  type="text"
                  value={claim}
                  onChange={(e) => setClaim(e.target.value)}
                  className="w-full h-14 pl-12 pr-4 bg-transparent border-none outline-none font-body-main text-base text-on-surface placeholder-outline focus:ring-0"
                  placeholder="e.g. The Great Wall of China is visible from space…"
                  aria-label="Enter a claim to fact-check"
                  autoComplete="off"
                />
              </div>
              {/* Divider on md+ */}
              <div className="hidden md:block w-px bg-outline-variant self-stretch my-2" />
              <div className="p-2 flex md:items-center">
                <button
                  type="submit"
                  disabled={!claim.trim()}
                  className="w-full md:w-auto bg-primary text-on-primary font-ui-header font-semibold h-10 px-6 rounded-lg hover:opacity-90 active:opacity-80 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 text-sm whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
                >
                  <Zap size={16} aria-hidden="true" />
                  Fact-check
                </button>
              </div>
            </div>
          </form>
          <p className="text-xs text-outline mt-2 ml-1">
            Press <kbd className="font-mono-technical bg-surface-container px-1 py-0.5 rounded border border-outline-variant">Enter</kbd> to submit
          </p>
        </div>
      </section>

      {/* ── Main grid ── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Example claims column */}
        <div className="lg:col-span-7 space-y-5">
          <div className="flex items-baseline justify-between">
            <h3 className="text-xs font-bold tracking-widest uppercase text-on-surface-variant">
              Try a claim
            </h3>
            <button
              onClick={() => navigate('/analysis')}
              className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded"
              aria-label="Go to analysis page to enter your own claim"
            >
              Use your own <ChevronRight size={12} />
            </button>
          </div>

          <div className="space-y-3">
            {EXAMPLE_CLAIMS.map((c, i) => (
              <FactCard
                key={i}
                title={c.title}
                verdict={c.verdict}
                onClick={() => handleExampleClick(c.title)}
              />
            ))}
          </div>
        </div>

        {/* Capabilities column */}
        <div className="lg:col-span-5">
          <div className="bg-primary-container rounded-xl p-6 deep-shadow relative overflow-hidden h-full flex flex-col">
            <div className="absolute -right-12 -top-12 w-48 h-48 bg-primary-fixed opacity-10 rounded-full blur-2xl" aria-hidden="true" />
            <p className="text-xs font-bold tracking-widest uppercase text-on-primary-fixed/60 mb-4 relative z-10">
              How it works
            </p>
            <div className="space-y-4 relative z-10 flex-1">
              {CAPABILITIES.map(({ Icon, title, body }) => (
                <div key={title} className="flex gap-3">
                  <div className="shrink-0 w-8 h-8 rounded-lg bg-primary-fixed/20 flex items-center justify-center mt-0.5">
                    <Icon size={15} className="text-on-primary-fixed" aria-hidden="true" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-on-primary-fixed">{title}</p>
                    <p className="text-xs text-on-primary-fixed/70 mt-0.5 leading-relaxed">{body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
