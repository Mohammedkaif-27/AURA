import { useState } from 'react';
import { FileText, ChevronDown } from 'lucide-react';

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
    <div className="mt-1.5">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-accent
                   transition-colors cursor-pointer py-1 px-1 -ml-1 rounded-lg"
      >
        <FileText className="w-3.5 h-3.5" />
        <span>{unique.length} source{unique.length > 1 ? 's' : ''}</span>
        <ChevronDown className={`w-3 h-3 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`} />
      </button>

      {expanded && (
        <div className="mt-1.5 flex flex-wrap gap-1.5 overflow-x-auto pb-1">
          {unique.map((s, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg
                         bg-bg-secondary text-xs text-text-secondary border border-border
                         flex-shrink-0 whitespace-nowrap"
            >
              <span className="text-accent font-medium truncate max-w-[150px]">{s.source}</span>
              {s.page > 0 && <span className="text-text-muted">p.{s.page}</span>}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
