import { User, Bot } from 'lucide-react'

export default function ChatFeed({ messages = [] }) {
    if (messages.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-12 text-text-muted">
                <Bot className="w-8 h-8 mb-3 opacity-30" />
                <p className="text-sm">No messages in this session</p>
            </div>
        )
    }

    return (
        <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
            {messages.map((msg, i) => (
                <div
                    key={i}
                    className={`flex gap-2.5 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                >
                    <div
                        className={`w-6 h-6 rounded-md flex items-center justify-center shrink-0 ${msg.role === 'user'
                                ? 'bg-bg-tertiary'
                                : 'bg-accent-light'
                            }`}
                    >
                        {msg.role === 'user' ? (
                            <User className="w-3 h-3 text-text-muted" />
                        ) : (
                            <Bot className="w-3 h-3 text-accent" />
                        )}
                    </div>

                    <div
                        className={`max-w-[75%] px-3 py-2 rounded-xl text-sm leading-relaxed ${msg.role === 'user'
                                ? 'bg-accent text-white'
                                : 'bg-bg-secondary text-text-primary border border-border'
                            }`}
                    >
                        {msg.content}
                    </div>
                </div>
            ))}
        </div>
    )
}
