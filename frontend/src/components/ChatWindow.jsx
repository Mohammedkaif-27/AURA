import { useState, useRef, useEffect, useCallback } from 'react';
import { sendMessage, fetchSessions, fetchSessionMessages, deleteSession } from '../api';
import MessageBubble from './MessageBubble';
import TypingIndicator from './TypingIndicator';
import ActionCard from './ActionCard';
import { LogOut, Plus, MessageSquare, Trash2, Menu, X } from 'lucide-react';
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

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    const userMsg = { role: 'user', text: trimmed };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

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
    <div className="flex h-screen bg-bg overflow-hidden">
      
      {/* ── Sidebar ── */}
      <div className={`fixed inset-y-0 left-0 z-40 w-64 bg-bg border-r border-border transform transition-transform duration-200 ease-in-out md:relative md:translate-x-0 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex flex-col h-full">
          <div className="p-4 flex-shrink-0">
            <button
              onClick={startNewChat}
              className="w-full flex items-center gap-2 justify-center border border-border hover:bg-bg-secondary text-text-primary rounded-lg py-2.5 px-4 transition-colors text-sm font-medium"
            >
              <Plus className="w-4 h-4" />
              New Chat
            </button>
          </div>
          
          <div className="flex-1 overflow-y-auto px-3 py-2 space-y-0.5">
            <div className="text-xs font-medium text-text-muted mb-3 px-2 uppercase tracking-wider">History</div>
            {sessions.map(s => (
              <div 
                key={s.session_id}
                onClick={() => selectSession(s.session_id)}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg cursor-pointer group transition-colors ${sessionId === s.session_id ? 'bg-accent-light text-accent' : 'hover:bg-bg-secondary text-text-secondary'}`}
              >
                <MessageSquare className={`w-3.5 h-3.5 flex-shrink-0 ${sessionId === s.session_id ? 'text-accent' : 'text-text-muted'}`} />
                <span className="text-sm truncate flex-1">{s.title || 'New Chat'}</span>
                <button 
                  onClick={(e) => {
                    e.stopPropagation();
                    setSessionToDelete(s.session_id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:text-danger text-text-muted transition-all"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
            {sessions.length === 0 && (
              <div className="text-center text-text-muted text-sm mt-10">No chats yet</div>
            )}
          </div>
          
          <div className="p-4 border-t border-border flex-shrink-0">
            <div className="flex items-center gap-2.5 px-2 py-1.5 mb-2">
              <div className="w-7 h-7 rounded-full bg-bg-tertiary flex items-center justify-center flex-shrink-0">
                <span className="text-xs text-text-secondary font-medium">{authSession?.user?.email?.charAt(0).toUpperCase()}</span>
              </div>
              <div className="text-xs text-text-secondary truncate flex-1">
                {authSession?.user?.email}
              </div>
            </div>
            <button
              onClick={onLogout}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-bg-secondary rounded-lg transition-colors"
            >
              <LogOut className="w-3.5 h-3.5" />
              Sign out
            </button>
          </div>
        </div>
      </div>
      
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/20 z-30 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Main Chat Area ── */}
      <div className="flex-1 flex flex-col h-full max-w-3xl mx-auto w-full">
        {/* Header */}
        <div className="px-4 md:px-6 py-4 flex-shrink-0 flex items-center border-b border-border bg-bg">
          <button 
            className="mr-3 p-1.5 rounded-lg md:hidden text-text-secondary hover:text-text-primary hover:bg-bg-secondary"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center">
              <span className="text-white font-semibold text-sm">A</span>
            </div>
            <div>
              <h1 className="text-sm font-semibold text-text-primary">AURA</h1>
              <p className="text-xs text-text-muted">Support Assistant</p>
            </div>
          </div>
        </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto bg-bg py-4 space-y-1 relative">
        {isFetchingHistory ? (
          <div className="absolute inset-0 flex items-center justify-center bg-bg/80 z-10">
            <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          </div>
        ) : null}
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
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="flex-shrink-0 border-t border-border bg-bg px-4 py-3">
        <div className="flex items-center gap-2 bg-bg-secondary rounded-lg border border-border
                        focus-within:border-accent focus-within:ring-1 focus-within:ring-accent/20 transition-all px-4 py-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your message..."
            disabled={isLoading}
            className="flex-1 bg-transparent text-sm text-text-primary placeholder-text-muted
                       outline-none disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
            className={`w-8 h-8 rounded-lg flex items-center justify-center transition-all
                       ${input.trim() && !isLoading
                         ? 'bg-accent hover:bg-accent-hover text-white cursor-pointer'
                         : 'bg-bg-tertiary text-text-muted cursor-not-allowed'}`}
          >
            {isLoading ? (
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M12 19V5m0 0l-7 7m7-7l7 7" />
              </svg>
            )}
          </button>
        </div>
        <p className="text-center text-xs text-text-muted mt-2">
          Powered by AURA · AI responses may contain errors
        </p>
      </div>
    </div>

      <ConfirmModal 
        isOpen={!!sessionToDelete}
        onClose={() => setSessionToDelete(null)}
        onConfirm={executeDeleteSession}
        title="Delete Chat"
        message="Are you sure you want to delete this chat?"
        confirmText="Delete Chat"
      />
    </div>
  );
}
