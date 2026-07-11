export default function TypingIndicator() {
  return (
    <div className="flex items-center gap-3 px-4 md:px-6 py-3 msg-enter">
      <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center flex-shrink-0">
        <span className="text-white text-xs font-semibold">A</span>
      </div>
      <div className="flex gap-1 items-center">
        <span className="w-1.5 h-1.5 rounded-full bg-text-muted animate-bounce" style={{ animationDelay: '0ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-text-muted animate-bounce" style={{ animationDelay: '150ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-text-muted animate-bounce" style={{ animationDelay: '300ms' }} />
      </div>
    </div>
  );
}
