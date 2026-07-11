import { useState, useEffect, useRef } from 'react'
import { supabase } from '../lib/supabase'
import { Package, ShoppingCart, Radio, Brain, Activity, RefreshCw, Upload } from 'lucide-react'
import StatCard from '../components/StatCard'
import { toast } from 'sonner'

export default function Dashboard() {
    const [stats, setStats] = useState([
        { id: 'products', icon: Package, label: 'Total Products', value: '-' },
        { id: 'orders', icon: ShoppingCart, label: 'Total Orders', value: '-' },
        { id: 'sessions', icon: Radio, label: 'Live Conversations', value: '-' },
        { id: 'knowledge', icon: Brain, label: 'Knowledge Files', value: '-' },
    ])
    
    const [recentActivity, setRecentActivity] = useState([
        { id: '1', text: 'Welcome to AURA Admin.', time: 'Just now' }
    ])

    const [isUploading, setIsUploading] = useState(false)
    const fileInputRef = useRef(null)

    useEffect(() => {
        fetchDashboardData()
    }, [])

    const fetchDashboardData = async () => {
        try {
            const { count: productCount } = await supabase
                .from('products')
                .select('*', { count: 'exact', head: true })
            
            const { count: orderCount } = await supabase
                .from('orders')
                .select('*', { count: 'exact', head: true })

            const { count: sessionCount } = await supabase
                .from('chat_sessions')
                .select('*', { count: 'exact', head: true })
                .eq('status', 'active')

            const { count: kbCount } = await supabase
                .from('knowledge_base')
                .select('*', { count: 'exact', head: true })

            setStats(prev => prev.map(s => {
                if (s.id === 'products') return { ...s, value: productCount || 0 }
                if (s.id === 'orders') return { ...s, value: orderCount || 0 }
                if (s.id === 'sessions') return { ...s, value: sessionCount || 0 }
                if (s.id === 'knowledge') return { ...s, value: kbCount || 0 }
                return s
            }))
            
            const { data: latestSessions } = await supabase
                .from('chat_sessions')
                .select('*')
                .order('created_at', { ascending: false })
                .limit(5)
                
            if (latestSessions && latestSessions.length > 0) {
                setRecentActivity(latestSessions.map((session) => ({
                    id: session.id,
                    text: `Chat session: ${session.title || session.session_id}`,
                    time: new Date(session.created_at).toLocaleString(),
                })))
            }

        } catch (err) {
            console.error('Error fetching dashboard stats:', err)
        }
    }

    const handleImportOrders = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setIsUploading(true);
        try {
            const { data: { session } } = await supabase.auth.getSession();
            if (!session) throw new Error("No active session");

            const formData = new FormData();
            formData.append('file', file);

            const res = await fetch(`${import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'}/admin/import-orders`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${session.access_token}`
                },
                body: formData
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to import orders');

            fetchDashboardData();
            
            setRecentActivity(prev => [
                {
                    id: Date.now().toString(),
                    text: data.message || 'Orders imported successfully',
                    time: 'Just now',
                },
                ...prev.slice(0, 4)
            ]);

            toast.success(data.message || 'Orders imported successfully');
        } catch (err) {
            console.error('Import error:', err);
            toast.error(`Error importing orders: ${err.message}`);
        } finally {
            setIsUploading(false);
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h1 className="text-xl font-semibold text-text-primary">Dashboard</h1>
                    <p className="text-sm text-text-muted mt-0.5">Overview of your AURA system</p>
                </div>
                
                <div className="flex items-center gap-2">
                    <input 
                        type="file" 
                        ref={fileInputRef} 
                        onChange={handleImportOrders} 
                        accept=".xlsx,.xls,.json" 
                        className="hidden" 
                    />
                    <button 
                        onClick={() => fileInputRef.current?.click()}
                        disabled={isUploading}
                        className="flex items-center gap-2 px-3 py-2 border border-border hover:bg-bg-tertiary rounded-lg text-sm font-medium text-text-primary transition-colors disabled:opacity-50"
                    >
                        <Upload className={`w-4 h-4 ${isUploading ? 'animate-bounce text-accent' : 'text-text-muted'}`} />
                        {isUploading ? 'Importing...' : 'Import Orders'}
                    </button>
                </div>
            </div>

            {/* Stat cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                {stats.map((s) => (
                    <StatCard key={s.label} {...s} />
                ))}
            </div>

            {/* Lower area */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {/* Recent Activity */}
                <div className="lg:col-span-2 card p-5">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                            <Activity className="w-4 h-4 text-text-muted" />
                            Recent Activity
                        </h2>
                        <button onClick={fetchDashboardData} className="text-xs text-text-muted hover:text-accent transition-colors flex items-center gap-1">
                            <RefreshCw className="w-3 h-3" /> Refresh
                        </button>
                    </div>

                    <div className="space-y-2">
                        {recentActivity.map((item) => (
                            <div
                                key={item.id}
                                className="flex items-start gap-3 p-3 rounded-lg hover:bg-bg-secondary transition-colors"
                            >
                                <span className="w-1.5 h-1.5 rounded-full bg-accent mt-1.5 shrink-0" />
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm text-text-primary leading-snug">{item.text}</p>
                                    <p className="text-xs text-text-muted mt-0.5">{item.time}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* System Health */}
                <div className="card p-5">
                    <h2 className="text-sm font-semibold text-text-primary mb-4">System Status</h2>

                    <div className="space-y-3">
                        {[
                            { label: 'Backend API', status: 'online' },
                            { label: 'RAG Engine', status: 'online' },
                            { label: 'Supabase', status: 'online' },
                            { label: 'Email Service', status: 'online' },
                        ].map((svc) => (
                            <div key={svc.label} className="flex items-center justify-between">
                                <span className="text-sm text-text-secondary">{svc.label}</span>
                                <div className="flex items-center gap-1.5">
                                    <span className="w-1.5 h-1.5 rounded-full bg-success" />
                                    <span className="text-xs text-text-muted capitalize">{svc.status}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    )
}
