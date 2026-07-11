export default function ActionCard({ action, actionLog }) {
  if (!action || action === 'none' || !actionLog) return null;

  const labels = {
    initiate_refund: { title: 'Refund Initiated', icon: '↩' },
    initiate_replacement: { title: 'Replacement Initiated', icon: '🔄' },
    book_service: { title: 'Service Booked', icon: '🔧' },
  };

  const info = labels[action] || { title: 'Action Processed', icon: '✓' };
  const actionId = actionLog?.action_id || 'N/A';
  const status = actionLog?.status || 'unknown';

  return (
    <div className="mx-4 md:mx-6 my-2 msg-enter">
      <div className="rounded-xl border border-border bg-bg-secondary p-4">
        {/* Header */}
        <div className="flex items-center gap-3 mb-3">
          <div className="w-8 h-8 rounded-lg bg-bg-tertiary flex items-center justify-center text-base">
            {info.icon}
          </div>
          <div>
            <h4 className="text-sm font-semibold text-text-primary">{info.title}</h4>
            <p className="text-xs text-text-muted">Action completed</p>
          </div>
          <div className="ml-auto">
            <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium
                            ${status === 'success'
                              ? 'bg-green-50 text-green-700 border border-green-200'
                              : 'bg-yellow-50 text-yellow-700 border border-yellow-200'}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${status === 'success' ? 'bg-green-500' : 'bg-yellow-500'}`} />
              {status}
            </span>
          </div>
        </div>

        {/* Details */}
        <div className="bg-bg rounded-lg p-3 border border-border">
          <div className="flex justify-between items-center">
            <span className="text-xs text-text-muted">Request ID</span>
            <span className="text-xs font-mono text-accent">{actionId}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
