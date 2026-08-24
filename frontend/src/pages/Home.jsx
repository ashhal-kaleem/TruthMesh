import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Globe, Zap, ArrowRight, ShieldCheck, Search, Database, Layers } from 'lucide-react';
import FactCard from '../components/FactCard';

// ─── Sample claims shown on the home page ─────────────────────────────────────
// These are curated demo examples — NOT live API results.
// verdict matches the real system (SUPPORTS | REFUTES | NOT ENOUGH INFO).
// sourceCount is intentionally omitted — these are not real retrieved results.
// Clicking a card navigates to /analysis with the claim pre-filled for live verification.
const DEMO_CLAIMS = [
  {
    verdict: 'SUPPORTS',
    id: 'DEMO-1',
    title: 'Global supply chain disruptions projected to ease by Q3 based on leading maritime shipping indexes.',
  },
  {
    verdict: 'REFUTES',
    id: 'DEMO-2',
    title: 'New breakthrough battery tech promises 1000x capacity increase with zero rare earth metals.',
  },
  {
    verdict: 'NOT ENOUGH INFO',
    id: 'DEMO-3',
    title: 'Proposed central bank digital currency (CBDC) implementation timeline shifted to late 2026.',
  },
];

// ─── Capability cards replacing fake platform stats ───────────────────────────
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

  const handleDemoClick = (title) => {
    navigate('/analysis', { state: { initialClaim: title } });
  };

  return (
    <div className="space-y-12 animate-in fade-in duration-500">
      {/* Hero */}
      <section className="text-center md:text-left pt-8 md:pt-16">
        <h2 className="text-4xl md:text-5xl font-display-editorial font-bold text-primary mb-6 leading-tight">
          Verify the <span className="text-primary-container">Unverifiable.</span>
        </h2>
        <p className="text-lg text-on-surface-variant max-w-2xl mb-8 font-ui-header">
          TruthMesh leverages a multi-agent system with advanced evidence retrieval to fact-check claims across diverse domains.
        </p>

        <form onSubmit={handleAnalyze} className="max-w-3xl bg-surface-container-lowest border border-outline-variant rounded-xl p-2 flex flex-col md:flex-row gap-2 deep-shadow focus-within:border-primary-container focus-within:ring-1 focus-within:ring-primary-container transition-all">
          <div className="flex-1 relative">
            <Globe className="absolute left-4 top-1/2 -translate-y-1/2 text-outline" size={24} />
            <input
              type="text"
              value={claim}
              onChange={(e) => setClaim(e.target.value)}
              className="w-full h-full min-h-[56px] pl-14 pr-4 bg-transparent border-none outline-none font-body-main text-lg text-on-surface placeholder-outline focus:ring-0"
              placeholder="Paste a claim or statement to analyse…"
            />
          </div>
          <button
            type="submit"
            disabled={!claim.trim()}
            className="bg-primary text-on-primary font-ui-header font-semibold py-3 px-8 rounded-lg hover:opacity-90 disabled:opacity-50 transition-all flex items-center justify-center gap-2 whitespace-nowrap"
          >
            <Zap size={20} />
            Launch Analysis
          </button>
        </form>
      </section>

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Demo claims column */}
        <div className="lg:col-span-8 space-y-8">
          <section>
            <div className="flex justify-between items-end mb-6 border-b border-outline-variant pb-3">
              <div>
                <h3 className="text-2xl font-display-editorial font-bold text-primary">Example Claims</h3>
                <p className="text-xs text-on-surface-variant mt-0.5">Sample claims — click any card to analyse it live.</p>
              </div>
              <button
                onClick={() => navigate('/analysis')}
                className="text-xs font-bold uppercase tracking-wider text-secondary hover:underline flex items-center gap-1"
              >
                Analyse your own <ArrowRight size={14} />
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {DEMO_CLAIMS.slice(0, 2).map(c => (
                <FactCard
                  key={c.id}
                  id={c.id}
                  title={c.title}
                  verdict={c.verdict}
                  demo
                  onClick={() => handleDemoClick(c.title)}
                />
              ))}
              <div className="md:col-span-2">
                <FactCard
                  id={DEMO_CLAIMS[2].id}
                  title={DEMO_CLAIMS[2].title}
                  verdict={DEMO_CLAIMS[2].verdict}
                  demo
                  onClick={() => handleDemoClick(DEMO_CLAIMS[2].title)}
                />
              </div>
            </div>
          </section>
        </div>

        {/* Capabilities column */}
        <div className="lg:col-span-4">
          <div className="bg-primary-container text-on-primary-container rounded-xl p-6 deep-shadow relative overflow-hidden h-full flex flex-col">
            <div className="absolute -right-12 -top-12 w-48 h-48 bg-primary-fixed opacity-10 rounded-full blur-2xl" />
            <h3 className="text-lg font-ui-header font-bold text-on-primary-fixed mb-6 relative z-10">How it works</h3>
            <div className="space-y-5 relative z-10 flex-1">
              {CAPABILITIES.map(({ Icon, title, body }) => (
                <div key={title} className="flex gap-3">
                  <div className="shrink-0 w-8 h-8 rounded-lg bg-primary-fixed/20 flex items-center justify-center mt-0.5">
                    <Icon size={16} className="text-on-primary-fixed" />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-on-primary-fixed">{title}</p>
                    <p className="text-xs opacity-75 mt-0.5 leading-relaxed">{body}</p>
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
