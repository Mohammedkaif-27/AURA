export default function TypingIndicator() {
  return (
    <div className="flex items-center gap-2.5 sm:gap-3 px-3 sm:px-4 md:px-6 py-2 sm:py-3 msg-enter">
      <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-xl bg-accent flex items-center justify-center flex-shrink-0 shadow-sm">
        <span className="text-white text-xs font-bold">A</span>
      </div>
      <div className="flex gap-1 items-center bg-bg-secondary border border-border rounded-2xl px-4 py-3">
        <span className="w-1.5 h-1.5 rounded-full bg-text-muted bounce-dot" style={{ animationDelay: '0ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-text-muted bounce-dot" style={{ animationDelay: '200ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-text-muted bounce-dot" style={{ animationDelay: '400ms' }} />
      </div>
    </div>
  );
}
