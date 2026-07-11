import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabase'
import { Radio, User, ToggleLeft, ToggleRight, Eye, Clock, Loader2 } from 'lucide-react'
import ChatFeed from '../components/ChatFeed'

export default function LiveCenter() {
    const [sessions, setSessions] = useState([])
    const [selectedId, setSelectedId] = useState(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchSessions()
        
        const subscription = supabase
            .channel('public:chat_messages')
            .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'chat_messages' }, () => {
                fetchSessions()
            })
            .subscribe()

        return () => supabase.removeChannel(subscription)
    }, [])

    const fetchSessions = async () => {
        try {
            const { data, error } = await supabase
                .from('chat_sessions')
                .select('*, chat_messages(*)')
                .order('updated_at', { ascending: false })
            
            if (error) throw error
            
            const formatted = data.map(session => ({
                ...session,
                customer_name: `User ${session.user_id ? session.user_id.substring(0,6) : 'Anon'}`,
                messages: session.chat_messages.sort((a,b) => new Date(a.created_at) - new Date(b.created_at)),
                handedOver: session.status === 'handed_over'
            }))
            
            setSessions(formatted)
            if (formatted.length > 0 && !selectedId) {
                setSelectedId(formatted[0].id)
            }
            setLoading(false)
        } catch (err) {
            console.error('Error fetching sessions:', err)
            setLoading(false)
        }
    }

    const selectedSession = sessions.find((s) => s.id === selectedId)

    const toggleHandover = async (id, currentHandedOver) => {
        try {
            const newStatus = currentHandedOver ? 'active' : 'handed_over'
            const { error } = await supabase
                .from('chat_sessions')
                .update({ status: newStatus })
                .eq('id', id)
            
            if (error) throw error
            
            setSessions((prev) =>
                prev.map((s) =>
                    s.id === id ? { ...s, handedOver: !currentHandedOver, status: newStatus } : s
                )
            )
        } catch (err) {
            console.error('Error updating handover:', err)
        }
    }

    if (loading && sessions.length === 0) {
        return (
            <div className="flex h-full items-center justify-center">
                <Loader2 className="w-5 h-5 animate-spin text-accent" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-semibold text-text-primary flex items-center gap-2">
                        <Radio className="w-4 h-4 text-success" />
                        Live Center
                    </h1>
                    <p className="text-sm text-text-muted mt-0.5">
                        Monitor active conversations
                    </p>
                </div>
                <div className="flex items-center gap-2 card px-3 py-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-success" />
                    <span className="text-sm text-text-secondary">
                        <span className="font-semibold text-text-primary">{sessions.filter(s => s.status === 'active').length}</span> active
                    </span>
                </div>
            </div>

            {/* Two-column layout */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 min-h-[500px] h-[calc(100vh-160px)]">
                {/* Session list */}
                <div className="card overflow-hidden flex flex-col h-full">
                    <div className="px-4 py-3 border-b border-border">
                        <h2 className="text-xs font-medium text-text-muted uppercase tracking-wider">
                            Sessions
                        </h2>
                    </div>

                    <div className="flex-1 overflow-y-auto divide-y divide-border">
                        {sessions.length === 0 ? (
                            <div className="p-8 text-center text-text-muted text-sm">
                                No active sessions.
                            </div>
                        ) : (
                            sessions.map((session) => (
                                <button
                                    key={session.id}
                                    onClick={() => setSelectedId(session.id)}
                                    className={`w-full text-left px-4 py-3 transition-colors ${selectedId === session.id
                                            ? 'bg-accent-light border-l-2 border-accent'
                                            : 'hover:bg-bg-secondary border-l-2 border-transparent'
                                        }`}
                                >
                                    <div className="flex items-center justify-between mb-1">
                                        <div className="flex items-center gap-2">
                                            <div className="w-6 h-6 rounded-md bg-bg-tertiary flex items-center justify-center shrink-0">
                                                <User className="w-3 h-3 text-text-muted" />
                                            </div>
                                            <span className="text-sm font-medium text-text-primary truncate max-w-[120px]">{session.customer_name}</span>
                                        </div>
                                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${session.handedOver ? 'bg-warning' : 'bg-success'
                                            }`} />
                                    </div>
                                    <div className="flex items-center gap-2 ml-8">
                                        <Clock className="w-3 h-3 text-text-muted" />
                                        <span className="text-xs text-text-muted">
                                            {new Date(session.updated_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                                        </span>
                                        <span className="text-xs text-text-muted">·</span>
                                        <span className="text-xs text-text-muted">{session.messages.length} msgs</span>
                                    </div>
                                </button>
                            ))
                        )}
                    </div>
                </div>

                {/* Conversation detail */}
                <div className="lg:col-span-2 card overflow-hidden flex flex-col h-full">
                    {selectedSession ? (
                        <>
                            <div className="px-4 py-3 border-b border-border flex items-center justify-between shrink-0">
                                <div className="flex items-center gap-3">
                                    <div className="w-8 h-8 rounded-lg bg-bg-tertiary flex items-center justify-center">
                                        <User className="w-4 h-4 text-text-muted" />
                                    </div>
                                    <div>
                                        <p className="text-sm font-medium text-text-primary">{selectedSession.customer_name}</p>
                                        <p className="text-xs text-text-muted font-mono">{selectedSession.session_id}</p>
                                    </div>
                                </div>

                                <button
                                    onClick={() => toggleHandover(selectedSession.id, selectedSession.handedOver)}
                                    className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${selectedSession.handedOver
                                            ? 'bg-yellow-50 text-warning border border-yellow-200'
                                            : 'bg-bg-secondary text-text-secondary hover:bg-bg-tertiary border border-border'
                                        }`}
                                >
                                    {selectedSession.handedOver ? (
                                        <>
                                            <ToggleRight className="w-4 h-4" />
                                            <span>Human Mode</span>
                                        </>
                                    ) : (
                                        <>
                                            <ToggleLeft className="w-4 h-4" />
                                            <span>Handover</span>
                                        </>
                                    )}
                                </button>
                            </div>

                            <div className="flex-1 overflow-y-auto p-4">
                                <ChatFeed messages={selectedSession.messages} />
                            </div>

                            <div className="px-4 py-2.5 border-t border-border flex items-center gap-2 shrink-0">
                                <Eye className="w-3.5 h-3.5 text-text-muted" />
                                <span className="text-xs text-text-muted">
                                    {selectedSession.handedOver
                                        ? 'Human agent has taken over'
                                        : 'AURA is handling automatically'}
                                </span>
                            </div>
                        </>
                    ) : (
                        <div className="flex-1 flex items-center justify-center text-text-muted text-sm">
                            Select a session to view
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
