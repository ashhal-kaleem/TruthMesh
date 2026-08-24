import React from 'react';
import { ShieldCheck, ShieldX, HelpCircle, FlaskConical } from 'lucide-react';

// Maps the canonical verdict strings (SUPPORTS | REFUTES | NOT ENOUGH INFO)
// to the Stitch accent system used across Analysis, History, and Home.
// The old `veracity: high | low | critical` prop is no longer used.
function getVerdictConfig(verdict) {
  switch ((verdict || '').toUpperCase().trim()) {
    case 'SUPPORTS':
      return {
        cardClass:  'veracity-high',
        badgeClass: 'bg-cyan-50 border-cyan-200 text-cyan-700',
        Icon:       ShieldCheck,
        iconColor:  'text-cyan-600',
        label:      'Supports',
      };
    case 'REFUTES':
      return {
        cardClass:  'veracity-critical',
        badgeClass: 'bg-error-container border-secondary/20 text-secondary',
        Icon:       ShieldX,
        iconColor:  'text-secondary',
        label:      'Refutes',
      };
    default:
      // NOT ENOUGH INFO
      return {
        cardClass:  'veracity-low',
        badgeClass: 'bg-surface-container-low border-outline-variant text-on-surface-variant',
        Icon:       HelpCircle,
        iconColor:  'text-tertiary',
        label:      'Not Enough Info',
      };
  }
}

export default function FactCard({ verdict, id, title, demo, onClick }) {
  const config = getVerdictConfig(verdict);

  return (
    <article
      onClick={onClick}
      className={`bg-surface-container-lowest border border-outline-variant rounded-lg p-6 deep-shadow fact-card ${config.cardClass} flex flex-col h-full transition-all ${onClick ? 'cursor-pointer hover-lift' : ''}`}
    >
      <div className="flex justify-between items-start mb-3 gap-2 flex-wrap">
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 border rounded text-xs font-bold tracking-wider uppercase ${config.badgeClass}`}>
          <config.Icon size={14} className={config.iconColor} />
          {config.label}
        </span>
        <div className="flex items-center gap-2">
          {demo && (
            <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border bg-tertiary-container/20 border-tertiary/20 text-tertiary-container font-semibold">
              <FlaskConical size={11} /> Demo
            </span>
          )}
          {id && <span className="font-mono-technical text-xs text-outline">ID: {id}</span>}
        </div>
      </div>

      <h4 className="font-claim-text text-xl text-primary mb-4 flex-1 line-clamp-3 leading-snug">
        {title}
      </h4>

      <div className="flex justify-between items-center mt-auto pt-4 border-t border-outline-variant">
        {demo
          ? <span className="text-xs text-primary font-semibold">Click to analyse →</span>
          : <span className="text-sm text-on-surface-variant font-ui-header">Analysis complete</span>
        }
      </div>
    </article>
  );
}
