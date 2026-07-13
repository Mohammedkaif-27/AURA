import { useState, useRef, useEffect, useCallback } from 'react';
import { sendMessage, fetchSessions, fetchSessionMessages, deleteSession } from '../api';
import MessageBubble from './MessageBubble';
import TypingIndicator from './TypingIndicator';
import ActionCard from './ActionCard';
import { LogOut, Plus, MessageSquare, Trash2, Menu, X, Send } from 'lucide-react';
import { toast } from 'sonner';
import ConfirmModal from './ConfirmModal';

const WELCOME_MSG = {
  role: 'bot',
  text: "Hello! I'm AURA, your AI support assistant. How can I help you today?",
  sources: [],
};

export default function ChatWindow({ session: authSession, onLogout }) {
  const token = authSession?.access_token;
  
  const [sessions, setSessions] = useState([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isFetchingHistory, setIsFetchingHistory] = useState(false);
  
  const [messages, setMessages] = useState([WELCOME_MSG]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [streamingIdx, setStreamingIdx] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const textareaRef = useRef(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  // Fetch session list
  const loadSessions = useCallback(async () => {
    if (!token) return;
    try {
      const data = await fetchSessions(token);
      setSessions(data || []);
    } catch (err) {
      console.error('Failed to load sessions:', err);
    }
  }, [token]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // Load specific session
  const selectSession = async (sid) => {
    setSessionId(sid);
    setIsFetchingHistory(true);
    setSidebarOpen(false);
    try {
      const msgs = await fetchSessionMessages(sid, token);
      if (msgs && msgs.length > 0) {
        setMessages(msgs.map(m => ({
          role: m.role,
          text: m.content,
          sources: m.sources || []
        })));
      } else {
        setMessages([WELCOME_MSG]);
      }
    } catch (err) {
      console.error('Failed to load session messages:', err);
      setMessages([WELCOME_MSG]);
    } finally {
      setIsFetchingHistory(false);
    }
  };

  const startNewChat = () => {
    setSessionId(null);
    setMessages([WELCOME_MSG]);
    setSidebarOpen(false);
  };

  const [sessionToDelete, setSessionToDelete] = useState(null);

  const executeDeleteSession = async () => {
    if (!sessionToDelete) return;
    try {
      await deleteSession(sessionToDelete, token);
      if (sessionId === sessionToDelete) {
        startNewChat();
      }
      loadSessions();
      toast.success('Chat deleted');
    } catch (err) {
      console.error('Failed to delete session:', err);
      toast.error('Failed to delete chat');
    } finally {
      setSessionToDelete(null);
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, isFetchingHistory, scrollToBottom]);

  // Auto-resize textarea
  const adjustTextarea = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    }
  };

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    const userMsg = { role: 'user', text: trimmed };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    try {
      const data = await sendMessage(trimmed, sessionId, token);

      if (data.session_id && !sessionId) {
        setSessionId(data.session_id);
        loadSessions();
      }

      const botMsg = {
        role: 'bot',
        text: data.answer || 'I could not generate a response.',
        sources: data.sources || [],
        action: data.action,
        actionLog: data.action_log,
        intent: data.intent,
      };

      setMessages(prev => [...prev, botMsg]);
      setStreamingIdx(messages.length + 1);

      const charCount = botMsg.text.length;
      const streamDuration = Math.min((charCount / 2) * 12, 3000);
      setTimeout(() => setStreamingIdx(null), streamDuration + 100);

    } catch (err) {
      setMessages(prev => [
        ...prev,
        {
          role: 'bot',
          text: `Sorry, something went wrong: ${err.message}. Please try again.`,
          sources: [],
        },
      ]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex h-full bg-bg overflow-hidden">
      
      {/* ── Mobile Sidebar Backdrop ── */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/30 backdrop-blur-sm z-40 lg:hidden transition-opacity"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Sidebar ── */}
      <aside className={`
        fixed inset-y-0 left-0 z-50 w-72 sm:w-80 bg-sidebar-bg border-r border-border
        flex flex-col
        transition-transform duration-300 ease-out
        lg:relative lg:z-auto lg:translate-x-0 lg:w-72
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        {/* Sidebar header */}
        <div className="p-4 flex items-center gap-3 flex-shrink-0 safe-top">
          <button
            onClick={startNewChat}
            className="flex-1 flex items-center gap-2 justify-center border border-border hover:bg-sidebar-hover
                       text-text-primary rounded-xl py-3 px-4 transition-colors text-sm font-medium press-scale"
          >
            <Plus className="w-4 h-4" />
            New Chat
          </button>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden p-2 rounded-xl text-text-secondary hover:bg-sidebar-hover transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        
        {/* Session list */}
        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-0.5">
          <div className="text-xs font-medium text-text-muted mb-3 px-2 uppercase tracking-wider">History</div>
          {sessions.map(s => (
            <div 
              key={s.session_id}
              onClick={() => selectSession(s.session_id)}
              className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl cursor-pointer group transition-all press-scale
                ${sessionId === s.session_id 
                  ? 'bg-accent-light text-accent shadow-sm' 
                  : 'hover:bg-sidebar-hover text-text-secondary'}`}
            >
              <MessageSquare className={`w-4 h-4 flex-shrink-0 ${sessionId === s.session_id ? 'text-accent' : 'text-text-muted'}`} />
              <span className="text-sm truncate flex-1">{s.title || 'New Chat'}</span>
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  setSessionToDelete(s.session_id);
                }}
                className="opacity-0 group-hover:opacity-100 p-1.5 hover:text-danger text-text-muted transition-all rounded-lg hover:bg-bg-tertiary"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
          {sessions.length === 0 && (
            <div className="text-center text-text-muted text-sm mt-10 px-4">
              <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p>No chats yet</p>
              <p className="text-xs mt-1">Start a conversation!</p>
            </div>
          )}
        </div>
        
        {/* User info + logout */}
        <div className="p-4 border-t border-border flex-shrink-0">
          <div className="flex items-center gap-2.5 px-2 py-2 mb-2 rounded-xl bg-bg-tertiary/50">
            <div className="w-8 h-8 rounded-full bg-accent/10 flex items-center justify-center flex-shrink-0">
              <span className="text-xs text-accent font-semibold">{authSession?.user?.email?.charAt(0).toUpperCase()}</span>
            </div>
            <div className="text-xs text-text-secondary truncate flex-1">
              {authSession?.user?.email}
            </div>
          </div>
          <button
            onClick={onLogout}
            className="w-full flex items-center gap-2 px-3 py-2.5 text-sm text-text-secondary hover:text-text-primary 
                       hover:bg-sidebar-hover rounded-xl transition-colors press-scale"
          >
            <LogOut className="w-4 h-4" />
            Sign out
          </button>
        </div>
      </aside>

      {/* ── Main Chat Area ── */}
      <div className="flex-1 flex flex-col h-full min-w-0">
        {/* Header */}
        <header className="px-4 sm:px-6 py-3 sm:py-4 flex-shrink-0 flex items-center border-b border-border bg-bg/95 glass safe-top z-10">
          <button 
            className="mr-3 p-2 rounded-xl lg:hidden text-text-secondary hover:text-text-primary hover:bg-bg-secondary transition-colors press-scale"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-accent flex items-center justify-center shadow-sm">
              <span className="text-white font-bold text-sm sm:text-base">A</span>
            </div>
            <div>
              <h1 className="text-sm sm:text-base font-semibold text-text-primary leading-tight">AURA</h1>
              <p className="text-xs text-text-muted">Support Assistant</p>
            </div>
          </div>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto bg-bg py-3 sm:py-4 space-y-1 relative scroll-smooth">
          {isFetchingHistory ? (
            <div className="absolute inset-0 flex items-center justify-center bg-bg/80 z-10">
              <div className="w-7 h-7 border-2 border-accent border-t-transparent rounded-full animate-spin" />
            </div>
          ) : null}

          {/* Center messages on desktop */}
          <div className="max-w-3xl mx-auto w-full">
            {messages.map((msg, i) => (
              <div key={i}>
                <MessageBubble
                  message={msg}
                  isStreaming={i === streamingIdx}
                />
                {msg.action && msg.action !== 'none' && msg.actionLog && (
                  <ActionCard action={msg.action} actionLog={msg.actionLog} />
                )}
              </div>
            ))}
            {isLoading && <TypingIndicator />}
            <div ref={messagesEndRef} className="h-1" />
          </div>
        </div>

        {/* Input */}
        <div className="flex-shrink-0 border-t border-border bg-bg px-3 sm:px-4 py-2 sm:py-3 safe-bottom">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-end gap-2 bg-bg-secondary rounded-2xl border border-border
                            focus-within:border-accent focus-within:ring-2 focus-within:ring-accent-glow 
                            transition-all px-3 sm:px-4 py-2">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => { setInput(e.target.value); adjustTextarea(); }}
                onKeyDown={handleKeyDown}
                placeholder="Type your message..."
                disabled={isLoading}
                rows={1}
                className="flex-1 bg-transparent text-sm sm:text-base text-text-primary placeholder-text-muted
                           outline-none disabled:opacity-50 resize-none leading-relaxed max-h-[120px]"
                style={{ minHeight: '24px' }}
              />
              <button
                onClick={handleSend}
                disabled={isLoading || !input.trim()}
                className={`w-9 h-9 sm:w-10 sm:h-10 rounded-xl flex items-center justify-center transition-all flex-shrink-0 press-scale
                           ${input.trim() && !isLoading
                             ? 'bg-accent hover:bg-accent-hover text-white shadow-sm cursor-pointer'
                             : 'bg-bg-tertiary text-text-muted cursor-not-allowed'}`}
              >
                {isLoading ? (
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </button>
            </div>
            <p className="text-center text-[11px] text-text-muted mt-1.5 hidden sm:block">
              Powered by AURA · AI responses may contain errors
            </p>
          </div>
        </div>
      </div>

      <ConfirmModal 
        isOpen={!!sessionToDelete}
        onClose={() => setSessionToDelete(null)}
        onConfirm={executeDeleteSession}
        title="Delete Chat"
        message="Are you sure you want to delete this chat? This action cannot be undone."
        confirmText="Delete Chat"
      />
    </div>
  );
}
