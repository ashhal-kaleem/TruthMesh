import React from 'react';
import { ShieldCheck, ShieldX, HelpCircle, ArrowRight } from 'lucide-react';

// Maps the canonical verdict strings (SUPPORTS | REFUTES | NOT ENOUGH INFO)
// to the design token system used across Analysis, History, and Home.
function getVerdictConfig(verdict) {
  switch ((verdict || '').toUpperCase().trim()) {
    case 'SUPPORTS':
      return {
        badgeClass: 'bg-primary/10 border-primary/30 text-primary',
        dotClass:   'bg-primary',
        Icon:       ShieldCheck,
        iconColor:  'text-primary',
        label:      'Supports',
      };
    case 'REFUTES':
      return {
        badgeClass: 'bg-error-container border-secondary/20 text-secondary',
        dotClass:   'bg-secondary',
        Icon:       ShieldX,
        iconColor:  'text-secondary',
        label:      'Refutes',
      };
    default:
      // NOT ENOUGH INFO
      return {
        badgeClass: 'bg-surface-container-low border-outline-variant text-on-surface-variant',
        dotClass:   'bg-tertiary',
        Icon:       HelpCircle,
        iconColor:  'text-tertiary',
        label:      'Not Enough Info',
      };
  }
}

export default function FactCard({ verdict, title, onClick }) {
  const config = getVerdictConfig(verdict);

  return (
    <button
      type="button"
      onClick={onClick}
      className="group w-full text-left bg-surface-container-lowest border border-outline-variant rounded-lg px-4 py-3.5 transition-all duration-150 hover:border-primary/40 hover:bg-surface-container-low hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1"
    >
      <div className="flex items-center gap-3 min-w-0">
        {/* Verdict badge */}
        <span
          className={`shrink-0 inline-flex items-center gap-1 px-2 py-0.5 border rounded text-xs font-bold tracking-wide uppercase ${config.badgeClass}`}
          aria-label={`Verdict: ${config.label}`}
        >
          <config.Icon size={12} className={config.iconColor} aria-hidden="true" />
          {config.label}
        </span>

        {/* Claim text */}
        <p className="flex-1 min-w-0 text-sm text-on-surface font-ui-header line-clamp-1 leading-snug">
          {title}
        </p>

        {/* Arrow — appears on hover */}
        <ArrowRight
          size={14}
          className="shrink-0 text-outline opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 transition-opacity duration-150"
          aria-hidden="true"
        />
      </div>
    </button>
  );
}
