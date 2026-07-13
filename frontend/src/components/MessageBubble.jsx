import { useState, useEffect } from 'react';
import SourceChip from './SourceChip';

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

  // Render text with basic markdown (bold, newlines, lists)
  const renderText = (text) => {
    const lines = text.split('\n');
    return lines.map((line, lineIdx) => {
      // Numbered list: "1. something" or "1) something"
      const numberedMatch = line.match(/^(\d+)[.)]\s+(.*)/);
      // Bullet list: "- something" or "• something" or "* something"
      const bulletMatch = line.match(/^[-•*]\s+(.*)/);

      let content;
      if (numberedMatch) {
        content = (
          <div key={lineIdx} className="flex gap-2 ml-1 my-0.5">
            <span className="text-text-muted flex-shrink-0 font-medium min-w-[1.2em] text-right">{numberedMatch[1]}.</span>
            <span>{renderInline(numberedMatch[2])}</span>
          </div>
        );
      } else if (bulletMatch) {
        content = (
          <div key={lineIdx} className="flex gap-2 ml-1 my-0.5">
            <span className="text-accent flex-shrink-0 mt-0.5">•</span>
            <span>{renderInline(bulletMatch[1])}</span>
          </div>
        );
      } else {
        content = (
          <span key={lineIdx}>
            {lineIdx > 0 && <br />}
            {renderInline(line)}
          </span>
        );
      }
      return content;
    });
  };

  // Render inline formatting: **bold**
  const renderInline = (text) => {
    return text.split(/(\*\*[^*]+\*\*)/).map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>;
      }
      return <span key={i}>{part}</span>;
    });
  };

  return (
    <div className={`flex gap-2.5 sm:gap-3 px-3 sm:px-4 md:px-6 py-1.5 sm:py-2 msg-enter ${isUser ? 'justify-end' : 'justify-start'}`}>
      {/* Bot avatar */}
      {!isUser && (
        <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-xl bg-accent flex items-center justify-center flex-shrink-0 mt-0.5 shadow-sm">
          <span className="text-white text-xs font-bold">A</span>
        </div>
      )}

      <div className={`max-w-[85%] sm:max-w-[80%] md:max-w-[70%] ${isUser ? 'order-first' : ''}`}>
        <div
          className={`rounded-2xl px-3.5 sm:px-4 py-2.5 sm:py-3 text-sm sm:text-[15px] leading-relaxed break-words
            ${isUser
              ? 'bg-accent text-white shadow-sm shadow-accent/20'
              : 'bg-bg-secondary text-text-primary border border-border'
            }`}
        >
          <span className={!streamDone ? 'typing-cursor' : ''}>
            {renderText(displayText)}
          </span>
        </div>
        
        {/* Source chips below bot messages */}
        {!isUser && streamDone && message.sources && message.sources.length > 0 && (
          <div className="ml-1 mt-1">
            <SourceChip sources={message.sources} />
          </div>
        )}
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-xl bg-bg-tertiary flex items-center justify-center flex-shrink-0 mt-0.5">
          <span className="text-text-secondary text-xs font-medium">U</span>
        </div>
      )}
    </div>
  );
}
