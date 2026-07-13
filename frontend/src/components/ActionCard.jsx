export default function ActionCard({ action, actionLog }) {
  if (!action || action === 'none' || !actionLog) return null;

  const labels = {
    initiate_refund: { title: 'Refund Initiated', icon: '↩', color: 'text-blue-600 bg-blue-50 border-blue-200' },
    initiate_replacement: { title: 'Replacement Initiated', icon: '🔄', color: 'text-purple-600 bg-purple-50 border-purple-200' },
    book_service: { title: 'Service Booked', icon: '🔧', color: 'text-orange-600 bg-orange-50 border-orange-200' },
  };

  const info = labels[action] || { title: 'Action Processed', icon: '✓', color: 'text-gray-600 bg-gray-50 border-gray-200' };
  const actionId = actionLog?.action_id || 'N/A';
  const status = actionLog?.status || 'unknown';

  return (
    <div className="mx-3 sm:mx-4 md:mx-6 my-2 msg-enter">
      <div className="max-w-3xl mx-auto">
        <div className="rounded-2xl border border-border bg-bg-secondary p-3.5 sm:p-4">
          {/* Header */}
          <div className="flex items-center gap-3 mb-3">
            <div className={`w-9 h-9 sm:w-10 sm:h-10 rounded-xl flex items-center justify-center text-base sm:text-lg ${info.color} border`}>
              {info.icon}
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-semibold text-text-primary">{info.title}</h4>
              <p className="text-xs text-text-muted">Action completed</p>
            </div>
            <div className="flex-shrink-0">
              <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium
                              ${status === 'success'
                                ? 'bg-green-50 text-green-700 border border-green-200'
                                : 'bg-yellow-50 text-yellow-700 border border-yellow-200'}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${status === 'success' ? 'bg-green-500' : 'bg-yellow-500'}`} />
                {status}
              </span>
            </div>
          </div>

          {/* Details */}
          <div className="bg-bg rounded-xl p-3 border border-border">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-1">
              <span className="text-xs text-text-muted">Request ID</span>
              <span className="text-xs font-mono text-accent break-all">{actionId}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
