import { useState, useEffect, useRef } from 'react'
import { supabase } from '../lib/supabase'
import { Search, Plus, Pencil, Trash2, X, Check, Loader2, AlertCircle, Upload, ShoppingCart } from 'lucide-react'
import { toast } from 'sonner'
import ConfirmModal from '../components/ConfirmModal'

const API_BASE = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'

async function apiFetch(path, options = {}) {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) throw new Error('Not authenticated')
    const res = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${session.access_token}`,
            ...(options.headers || {}),
        },
    })
    const json = await res.json()
    if (!res.ok) throw new Error(json.detail || 'Request failed')
    return json
}

const STATUS_OPTIONS = ['Pending', 'Processing', 'In-Transit', 'Delivered', 'Cancelled']
const STATUS_COLORS = {
    'Pending': 'bg-yellow-50 text-yellow-700',
    'Processing': 'bg-blue-50 text-blue-700',
    'In-Transit': 'bg-purple-50 text-purple-700',
    'Delivered': 'bg-green-50 text-green-700',
    'Cancelled': 'bg-red-50 text-red-700',
}

export default function Orders() {
    const [orders, setOrders] = useState([])
    const [products, setProducts] = useState([])
    const [search, setSearch] = useState('')
    const [editingId, setEditingId] = useState(null)
    const [editData, setEditData] = useState({})
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [isAdding, setIsAdding] = useState(false)
    const [validationErrors, setValidationErrors] = useState({})
    const [saving, setSaving] = useState(false)
    const [isUploading, setIsUploading] = useState(false)
    const fileInputRef = useRef(null)

    useEffect(() => {
        fetchOrders()
        fetchProducts()
    }, [])

    const fetchOrders = async () => {
        try {
            setLoading(true)
            const { data, error } = await supabase
                .from('orders')
                .select('*')
                .order('created_at', { ascending: false })
            if (error) throw error
            setOrders(data || [])
        } catch (err) {
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    const fetchProducts = async () => {
        try {
            const { data } = await supabase.from('products').select('id, name, manual_url, warranty_years').order('name')
            setProducts(data || [])
        } catch { }
    }

    const filtered = orders.filter(o =>
        o.id?.toLowerCase().includes(search.toLowerCase()) ||
        o.customer_name?.toLowerCase().includes(search.toLowerCase()) ||
        o.product_name?.toLowerCase().includes(search.toLowerCase()) ||
        o.customer_phone?.includes(search)
    )

    const validate = () => {
        const errs = {}
        if (!editData.customer_name || !editData.customer_name.trim()) errs.customer_name = 'Required'
        if (!editData.product_name || !editData.product_name.trim()) errs.product_name = 'Required'
        setValidationErrors(errs)
        return Object.keys(errs).length === 0
    }

    const startEdit = (order) => {
        setEditingId(order.id)
        setEditData({ ...order })
        setValidationErrors({})
    }

    const handleProductSelect = (productId) => {
        const product = products.find(p => p.id === productId)
        if (product) {
            setEditData(prev => ({
                ...prev,
                product_id: product.id,
                product_name: product.name,
                warranty_years: product.warranty_years || 1,
            }))
        }
    }

    const saveEdit = async () => {
        if (!validate()) return
        setSaving(true)
        try {
            if (isAdding) {
                await apiFetch('/admin/orders', {
                    method: 'POST',
                    body: JSON.stringify(editData),
                })
            } else {
                await apiFetch(`/admin/orders/${editingId}`, {
                    method: 'PUT',
                    body: JSON.stringify(editData),
                })
            }
            await fetchOrders()
            setEditingId(null)
            setIsAdding(false)
            setEditData({})
            setValidationErrors({})
        } catch (err) {
            setError(err.message)
        } finally {
            setSaving(false)
        }
    }

    const cancelEdit = () => {
        if (isAdding) {
            setOrders(prev => prev.filter(o => o.id !== editingId))
            setIsAdding(false)
        }
        setEditingId(null)
        setEditData({})
        setValidationErrors({})
    }

    const [itemToDelete, setItemToDelete] = useState(null)

    const deleteOrder = async () => {
        if (!itemToDelete) return
        try {
            await apiFetch(`/admin/orders/${itemToDelete}`, { method: 'DELETE' })
            await fetchOrders()
            toast.success('Order deleted successfully')
        } catch (err) {
            toast.error(err.message)
        } finally {
            setItemToDelete(null)
        }
    }

    const handleAddOrder = () => {
        const newId = `ORD-${Date.now()}`
        const newOrder = {
            id: newId,
            customer_name: '',
            customer_phone: '',
            product_id: '',
            product_name: '',
            status: 'Pending',
            purchase_date: new Date().toISOString().split('T')[0],
            warranty_years: 1,
            serial_number: '',
        }
        setOrders([newOrder, ...orders])
        setEditingId(newId)
        setEditData(newOrder)
        setIsAdding(true)
        setValidationErrors({})
    }

    const handleImportOrders = async (e) => {
        const file = e.target.files?.[0]
        if (!file) return
        setIsUploading(true)
        try {
            const { data: { session } } = await supabase.auth.getSession()
            if (!session) throw new Error('No active session')
            const formData = new FormData()
            formData.append('file', file)
            const res = await fetch(`${API_BASE}/admin/import-orders`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${session.access_token}` },
                body: formData,
            })
            const data = await res.json()
            if (!res.ok) throw new Error(data.detail || 'Failed to import')
            await fetchOrders()
            toast.success(data.message || 'Orders imported successfully')
        } catch (err) {
            toast.error(err.message)
        } finally {
            setIsUploading(false)
            if (fileInputRef.current) fileInputRef.current.value = ''
        }
    }

    const inputClass = "w-full px-2.5 py-1.5 rounded-md bg-bg border border-border text-sm text-text-primary focus:outline-none focus:border-accent transition-colors"
    const errorInputClass = "w-full px-2.5 py-1.5 rounded-md bg-bg border border-danger text-sm text-text-primary focus:outline-none focus:border-danger transition-colors"

    if (loading && orders.length === 0) {
        return (
            <div className="flex h-full items-center justify-center">
                <Loader2 className="w-6 h-6 animate-spin text-accent" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                    <h1 className="text-xl font-semibold text-text-primary">Orders</h1>
                    <p className="text-sm text-text-muted mt-0.5">Manage customer orders and shipments</p>
                </div>
                <div className="flex items-center gap-2">
                    <input type="file" ref={fileInputRef} onChange={handleImportOrders} accept=".xlsx,.xls,.json" className="hidden" />
                    <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={isUploading}
                        className="flex items-center gap-2 px-3 py-2 border border-border hover:bg-bg-tertiary rounded-lg text-sm font-medium text-text-primary transition-colors disabled:opacity-50"
                    >
                        <Upload className={`w-4 h-4 ${isUploading ? 'animate-bounce text-accent' : 'text-text-muted'}`} />
                        {isUploading ? 'Importing...' : 'Import Orders'}
                    </button>
                    <button
                        onClick={handleAddOrder}
                        disabled={editingId !== null}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent hover:bg-accent-hover text-white text-sm font-medium transition-colors disabled:opacity-50"
                    >
                        <Plus className="w-4 h-4" />
                        Add Order
                    </button>
                </div>
            </div>

            {/* Search */}
            <div className="relative max-w-sm">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
                <input
                    type="text"
                    placeholder="Search orders..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-full pl-9 pr-4 py-2 rounded-lg bg-bg border border-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20 transition-all"
                />
            </div>

            {error && (
                <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    {error}
                    <button onClick={() => setError(null)} className="ml-auto"><X className="w-3.5 h-3.5" /></button>
                </div>
            )}

            {/* Stats row */}
            <div className="flex flex-wrap gap-3">
                {[
                    { label: 'Total', value: orders.length },
                    { label: 'Delivered', value: orders.filter(o => o.status === 'Delivered').length },
                    { label: 'Pending', value: orders.filter(o => o.status === 'Pending').length },
                    { label: 'In Transit', value: orders.filter(o => o.status === 'In-Transit').length },
                ].map(s => (
                    <div key={s.label} className="card px-4 py-3 flex items-center gap-3">
                        <div>
                            <p className="text-lg font-semibold text-text-primary">{s.value}</p>
                            <p className="text-xs text-text-muted">{s.label}</p>
                        </div>
                    </div>
                ))}
            </div>

            {/* Orders table */}
            <div className="card overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-border bg-bg-secondary">
                                {['Order ID', 'Customer', 'Phone', 'Product', 'Date', 'Status', 'Warranty', 'Actions'].map(h => (
                                    <th key={h} className="px-4 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                            {filtered.map(order => {
                                const isEditing = editingId === order.id

                                return (
                                    <tr key={order.id} className={`hover:bg-bg-secondary transition-colors ${isEditing ? 'bg-accent-light/30' : ''}`}>
                                        {/* Order ID */}
                                        <td className="px-4 py-3 font-mono text-xs text-accent">
                                            {isEditing && isAdding ? (
                                                <input value={editData.id} onChange={e => setEditData({ ...editData, id: e.target.value })} className={`${inputClass} w-28`} placeholder="ID" />
                                            ) : order.id}
                                        </td>

                                        {/* Customer Name */}
                                        <td className="px-4 py-3">
                                            {isEditing ? (
                                                <div>
                                                    <input value={editData.customer_name || ''} onChange={e => setEditData({ ...editData, customer_name: e.target.value })} className={validationErrors.customer_name ? errorInputClass : inputClass} placeholder="Customer name *" />
                                                    {validationErrors.customer_name && <p className="text-danger text-xs mt-0.5">{validationErrors.customer_name}</p>}
                                                </div>
                                            ) : <span className="font-medium text-text-primary">{order.customer_name}</span>}
                                        </td>

                                        {/* Phone */}
                                        <td className="px-4 py-3 text-text-secondary">
                                            {isEditing ? (
                                                <input value={editData.customer_phone || ''} onChange={e => setEditData({ ...editData, customer_phone: e.target.value })} className={`${inputClass} w-28`} placeholder="Phone" />
                                            ) : (order.customer_phone || '—')}
                                        </td>

                                        {/* Product */}
                                        <td className="px-4 py-3">
                                            {isEditing ? (
                                                <div>
                                                    <select
                                                        value={editData.product_id || ''}
                                                        onChange={e => handleProductSelect(e.target.value)}
                                                        className={validationErrors.product_name ? errorInputClass : `${inputClass} w-40`}
                                                    >
                                                        <option value="">Select product *</option>
                                                        {products.map(p => (
                                                            <option key={p.id} value={p.id}>{p.name}</option>
                                                        ))}
                                                    </select>
                                                    {validationErrors.product_name && <p className="text-danger text-xs mt-0.5">{validationErrors.product_name}</p>}
                                                </div>
                                            ) : <span className="text-text-primary">{order.product_name}</span>}
                                        </td>

                                        {/* Date */}
                                        <td className="px-4 py-3 text-text-secondary text-xs">
                                            {isEditing ? (
                                                <input type="date" value={editData.purchase_date || ''} onChange={e => setEditData({ ...editData, purchase_date: e.target.value })} className={`${inputClass} w-32`} />
                                            ) : (order.purchase_date ? new Date(order.purchase_date).toLocaleDateString() : '—')}
                                        </td>

                                        {/* Status */}
                                        <td className="px-4 py-3">
                                            {isEditing ? (
                                                <select value={editData.status || 'Pending'} onChange={e => setEditData({ ...editData, status: e.target.value })} className={`${inputClass} w-28`}>
                                                    {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                                                </select>
                                            ) : (
                                                <span className={`inline-block px-2 py-0.5 rounded-md text-xs font-medium ${STATUS_COLORS[order.status] || 'bg-bg-tertiary text-text-secondary'}`}>
                                                    {order.status}
                                                </span>
                                            )}
                                        </td>

                                        {/* Warranty */}
                                        <td className="px-4 py-3 text-text-secondary text-xs">
                                            {isEditing ? (
                                                <input type="number" value={editData.warranty_years ?? 1} onChange={e => setEditData({ ...editData, warranty_years: Number(e.target.value) })} className={`${inputClass} w-14`} min="0" />
                                            ) : `${order.warranty_years || 0}yr`}
                                        </td>

                                        {/* Actions */}
                                        <td className="px-4 py-3">
                                            <div className="flex items-center gap-1">
                                                {isEditing ? (
                                                    <>
                                                        <button onClick={saveEdit} disabled={saving} className="p-1.5 rounded-md text-success hover:bg-green-50 transition-colors disabled:opacity-50" title="Save">
                                                            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                                                        </button>
                                                        <button onClick={cancelEdit} className="p-1.5 rounded-md text-text-muted hover:bg-bg-tertiary transition-colors" title="Cancel">
                                                            <X className="w-4 h-4" />
                                                        </button>
                                                    </>
                                                ) : (
                                                    <>
                                                        <button onClick={() => startEdit(order)} disabled={editingId !== null} className="p-1.5 rounded-md text-text-muted hover:text-accent hover:bg-accent-light transition-colors disabled:opacity-30" title="Edit">
                                                            <Pencil className="w-4 h-4" />
                                                        </button>
                                                        <button onClick={() => setItemToDelete(order.id)} disabled={editingId !== null} className="p-1.5 rounded-md text-text-muted hover:text-danger hover:bg-red-50 transition-colors disabled:opacity-30" title="Delete">
                                                            <Trash2 className="w-4 h-4" />
                                                        </button>
                                                    </>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                )
                            })}
                            {filtered.length === 0 && (
                                <tr>
                                    <td colSpan={8} className="px-4 py-10 text-center text-text-muted text-sm">
                                        No orders found. Add an order or import from a file.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            <ConfirmModal 
                isOpen={!!itemToDelete}
                onClose={() => setItemToDelete(null)}
                onConfirm={deleteOrder}
                title="Delete Order"
                message="Are you sure you want to delete this order? This action cannot be undone."
                confirmText="Delete Order"
            />
        </div>
    )
}
