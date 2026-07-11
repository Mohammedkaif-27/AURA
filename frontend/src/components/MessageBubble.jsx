import { useState, useEffect } from 'react';

export default function MessageBubble({ message, isStreaming }) {
  const isUser = message.role === 'user';
  const [displayText, setDisplayText] = useState(isUser ? message.text : '');
  const [streamDone, setStreamDone] = useState(isUser);

  useEffect(() => {
    if (isUser || !isStreaming) {
      setDisplayText(message.text);
      setStreamDone(true);
      return;
    }

    let i = 0;
    const text = message.text;
    const interval = setInterval(() => {
      i += 2;
      if (i >= text.length) {
        setDisplayText(text);
        setStreamDone(true);
        clearInterval(interval);
      } else {
        setDisplayText(text.slice(0, i));
      }
    }, 12);

    return () => clearInterval(interval);
  }, [message.text, isUser, isStreaming]);

  return (
    <div className={`flex gap-3 px-4 md:px-6 py-2 msg-enter ${isUser ? 'justify-end' : 'justify-start'}`}>
      {/* Bot avatar */}
      {!isUser && (
        <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center flex-shrink-0 mt-0.5">
          <span className="text-white text-xs font-semibold">A</span>
        </div>
      )}

      <div className={`max-w-[80%] ${isUser ? 'order-first' : ''}`}>
        <div
          className={`rounded-xl px-4 py-2.5 text-sm leading-relaxed
            ${isUser
              ? 'bg-accent text-white'
              : 'bg-bg-secondary text-text-primary border border-border'
            }`}
        >
          <span className={!streamDone ? 'typing-cursor' : ''}>
            {displayText.split(/(\*\*[^*]+\*\*)/).map((part, i) => {
              if (part.startsWith('**') && part.endsWith('**')) {
                return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>;
              }
              return part.split('\n').map((line, j) => (
                <span key={`${i}-${j}`}>
                  {j > 0 && <br />}
                  {line}
                </span>
              ));
            })}
          </span>
        </div>
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="w-7 h-7 rounded-lg bg-bg-tertiary flex items-center justify-center flex-shrink-0 mt-0.5">
          <span className="text-text-secondary text-xs font-medium">U</span>
        </div>
      )}
    </div>
  );
}
