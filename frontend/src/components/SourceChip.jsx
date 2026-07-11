import { useState } from 'react';

export default function SourceChip({ sources }) {
  const [expanded, setExpanded] = useState(false);

  if (!sources || sources.length === 0) return null;

  const unique = [];
  const seen = new Set();
  for (const s of sources) {
    const key = `${s.source}-p${s.page}`;
    if (!seen.has(key)) {
      seen.add(key);
      unique.push(s);
    }
  }

  return (
    <div className="mt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-accent
                   transition-colors cursor-pointer"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        {unique.length} source{unique.length > 1 ? 's' : ''}
        <svg className={`w-3 h-3 transition-transform ${expanded ? 'rotate-180' : ''}`}
             fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {unique.map((s, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md
                         bg-bg-secondary text-xs text-text-secondary border border-border"
            >
              <span className="text-accent font-medium">{s.source}</span>
              {s.page > 0 && <span className="text-text-muted">p.{s.page}</span>}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
