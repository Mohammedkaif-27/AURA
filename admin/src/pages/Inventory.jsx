import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabase'
import { Search, Plus, Pencil, Trash2, FileText, X, Check, Loader2, AlertCircle, ChevronDown } from 'lucide-react'
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

export default function Inventory() {
    const [products, setProducts] = useState([])
    const [search, setSearch] = useState('')
    const [editingId, setEditingId] = useState(null)
    const [editData, setEditData] = useState({})
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [isAdding, setIsAdding] = useState(false)
    const [validationErrors, setValidationErrors] = useState({})
    const [knowledgeDocs, setKnowledgeDocs] = useState([])
    const [categories, setCategories] = useState([])
    const [saving, setSaving] = useState(false)

    useEffect(() => {
        fetchProducts()
        fetchKnowledgeDocs()
    }, [])

    useEffect(() => {
        const cats = [...new Set(products.map(p => p.category).filter(Boolean))]
        setCategories(cats)
    }, [products])

    const fetchProducts = async () => {
        try {
            setLoading(true)
            const { data, error } = await supabase
                .from('products')
                .select('*')
                .order('created_at', { ascending: false })
            if (error) throw error
            setProducts(data || [])
        } catch (err) {
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    const fetchKnowledgeDocs = async () => {
        try {
            const { data } = await supabase
                .from('knowledge_base')
                .select('file_name, status')
                .eq('status', 'ready')
                .order('created_at', { ascending: false })
            setKnowledgeDocs(data || [])
        } catch { }
    }

    const filtered = products.filter(
        (p) =>
            p.name?.toLowerCase().includes(search.toLowerCase()) ||
            p.id?.toLowerCase().includes(search.toLowerCase()) ||
            p.category?.toLowerCase().includes(search.toLowerCase())
    )

    const validate = () => {
        const errs = {}
        if (!editData.name || !editData.name.trim()) errs.name = 'Name is required'
        if (!editData.category || !editData.category.trim()) errs.category = 'Category is required'
        if (!editData.price || Number(editData.price) <= 0) errs.price = 'Price must be > 0'
        if (editData.warranty_years !== undefined && Number(editData.warranty_years) < 0) errs.warranty_years = 'Must be ≥ 0'
        setValidationErrors(errs)
        return Object.keys(errs).length === 0
    }

    const startEdit = (product) => {
        setEditingId(product.id)
        setEditData({ ...product })
        setValidationErrors({})
    }

    const saveEdit = async () => {
        if (!validate()) return
        setSaving(true)
        try {
            if (isAdding) {
                await apiFetch('/admin/products', {
                    method: 'POST',
                    body: JSON.stringify(editData),
                })
            } else {
                await apiFetch(`/admin/products/${editingId}`, {
                    method: 'PUT',
                    body: JSON.stringify(editData),
                })
            }
            await fetchProducts()
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
            setProducts(prev => prev.filter(p => p.id !== editingId))
            setIsAdding(false)
        }
        setEditingId(null)
        setEditData({})
        setValidationErrors({})
    }

    const [itemToDelete, setItemToDelete] = useState(null)

    const deleteProduct = async () => {
        if (!itemToDelete) return
        try {
            await apiFetch(`/admin/products/${itemToDelete}`, { method: 'DELETE' })
            await fetchProducts()
            toast.success('Product deleted successfully')
        } catch (err) {
            toast.error(err.message)
        } finally {
            setItemToDelete(null)
        }
    }

    const handleAddProduct = () => {
        const newId = `PROD-${Date.now()}`
        const newProduct = {
            id: newId,
            name: '',
            brand: '',
            category: '',
            price: 0,
            warranty_years: 1,
            manual_url: ''
        }
        setProducts([newProduct, ...products])
        setEditingId(newId)
        setEditData(newProduct)
        setIsAdding(true)
        setValidationErrors({})
    }

    const inputClass = "w-full px-2.5 py-1.5 rounded-md bg-bg border border-border text-sm text-text-primary focus:outline-none focus:border-accent transition-colors"
    const errorInputClass = "w-full px-2.5 py-1.5 rounded-md bg-bg border border-danger text-sm text-text-primary focus:outline-none focus:border-danger transition-colors"

    if (loading && products.length === 0) {
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
                    <h1 className="text-xl font-semibold text-text-primary">Inventory</h1>
                    <p className="text-sm text-text-muted mt-0.5">Manage products, prices, and manuals</p>
                </div>
                <button 
                    onClick={handleAddProduct}
                    disabled={editingId !== null}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent hover:bg-accent-hover text-white text-sm font-medium transition-colors self-start disabled:opacity-50"
                >
                    <Plus className="w-4 h-4" />
                    Add Product
                </button>
            </div>

            {/* Search */}
            <div className="relative max-w-sm">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
                <input
                    type="text"
                    placeholder="Search products..."
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

            {/* Product table */}
            <div className="card overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-border bg-bg-secondary">
                                {['Product ID', 'Name', 'Category', 'Price (₹)', 'Warranty', 'Manual', 'Actions'].map(
                                    (h) => (
                                        <th
                                            key={h}
                                            className="px-4 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider"
                                        >
                                            {h}
                                        </th>
                                    )
                                )}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                            {filtered.map((product) => {
                                const isEditing = editingId === product.id

                                return (
                                    <tr
                                        key={product.id}
                                        className={`hover:bg-bg-secondary transition-colors ${isEditing ? 'bg-accent-light/30' : ''}`}
                                    >
                                        <td className="px-4 py-3 font-mono text-xs text-accent">
                                            {isEditing && isAdding ? (
                                                <input
                                                    value={editData.id}
                                                    onChange={(e) => setEditData({ ...editData, id: e.target.value })}
                                                    className={`${inputClass} w-28`}
                                                    placeholder="ID"
                                                />
                                            ) : (
                                                product.id
                                            )}
                                        </td>

                                        <td className="px-4 py-3">
                                            {isEditing ? (
                                                <div>
                                                    <input
                                                        value={editData.name || ''}
                                                        onChange={(e) => setEditData({ ...editData, name: e.target.value })}
                                                        className={validationErrors.name ? errorInputClass : inputClass}
                                                        placeholder="Product name *"
                                                    />
                                                    {validationErrors.name && (
                                                        <p className="text-danger text-xs mt-0.5">{validationErrors.name}</p>
                                                    )}
                                                </div>
                                            ) : (
                                                <span className="font-medium text-text-primary">{product.name}</span>
                                            )}
                                        </td>

                                        <td className="px-4 py-3">
                                            {isEditing ? (
                                                <div>
                                                    <div className="relative">
                                                        <input
                                                            list="category-options"
                                                            value={editData.category || ''}
                                                            onChange={(e) => setEditData({ ...editData, category: e.target.value })}
                                                            className={validationErrors.category ? errorInputClass : inputClass}
                                                            placeholder="Select or type *"
                                                        />
                                                        <datalist id="category-options">
                                                            {categories.map(c => <option key={c} value={c} />)}
                                                        </datalist>
                                                    </div>
                                                    {validationErrors.category && (
                                                        <p className="text-danger text-xs mt-0.5">{validationErrors.category}</p>
                                                    )}
                                                </div>
                                            ) : (
                                                <span className="inline-block px-2 py-0.5 rounded-md bg-bg-tertiary text-text-secondary text-xs font-medium">
                                                    {product.category || 'Uncategorized'}
                                                </span>
                                            )}
                                        </td>

                                        <td className="px-4 py-3">
                                            {isEditing ? (
                                                <div>
                                                    <input
                                                        type="number"
                                                        value={editData.price || ''}
                                                        onChange={(e) => setEditData({ ...editData, price: Number(e.target.value) })}
                                                        className={`${validationErrors.price ? errorInputClass : inputClass} w-24`}
                                                        placeholder="Price *"
                                                        min="0.01"
                                                        step="0.01"
                                                    />
                                                    {validationErrors.price && (
                                                        <p className="text-danger text-xs mt-0.5">{validationErrors.price}</p>
                                                    )}
                                                </div>
                                            ) : (
                                                <span className="text-text-secondary">₹{product.price?.toLocaleString() || 0}</span>
                                            )}
                                        </td>

                                        <td className="px-4 py-3 text-text-secondary">
                                            {isEditing ? (
                                                <div>
                                                    <input
                                                        type="number"
                                                        value={editData.warranty_years ?? 0}
                                                        onChange={(e) => setEditData({ ...editData, warranty_years: Number(e.target.value) })}
                                                        className={`${validationErrors.warranty_years ? errorInputClass : inputClass} w-16`}
                                                        min="0"
                                                    />
                                                    {validationErrors.warranty_years && (
                                                        <p className="text-danger text-xs mt-0.5">{validationErrors.warranty_years}</p>
                                                    )}
                                                </div>
                                            ) : (
                                                `${product.warranty_years || 0}yr`
                                            )}
                                        </td>

                                        <td className="px-4 py-3">
                                            {isEditing ? (
                                                <select
                                                    value={editData.manual_url || ''}
                                                    onChange={(e) => setEditData({ ...editData, manual_url: e.target.value })}
                                                    className={`${inputClass} w-40`}
                                                >
                                                    <option value="">— None —</option>
                                                    {knowledgeDocs.map(doc => (
                                                        <option key={doc.file_name} value={doc.file_name}>
                                                            {doc.file_name}
                                                        </option>
                                                    ))}
                                                </select>
                                            ) : product.manual_url ? (
                                                <span className="flex items-center gap-1 text-success text-xs">
                                                    <FileText className="w-3.5 h-3.5" />
                                                    {product.manual_url}
                                                </span>
                                            ) : (
                                                <span className="text-text-muted text-xs">—</span>
                                            )}
                                        </td>

                                        <td className="px-4 py-3">
                                            <div className="flex items-center gap-1">
                                                {isEditing ? (
                                                    <>
                                                        <button
                                                            onClick={saveEdit}
                                                            disabled={saving}
                                                            className="p-1.5 rounded-md text-success hover:bg-green-50 transition-colors disabled:opacity-50"
                                                            title="Save"
                                                        >
                                                            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                                                        </button>
                                                        <button
                                                            onClick={cancelEdit}
                                                            className="p-1.5 rounded-md text-text-muted hover:bg-bg-tertiary transition-colors"
                                                            title="Cancel"
                                                        >
                                                            <X className="w-4 h-4" />
                                                        </button>
                                                    </>
                                                ) : (
                                                    <>
                                                        <button
                                                            onClick={() => startEdit(product)}
                                                            disabled={editingId !== null}
                                                            className="p-1.5 rounded-md text-text-muted hover:text-accent hover:bg-accent-light transition-colors disabled:opacity-30"
                                                            title="Edit"
                                                        >
                                                            <Pencil className="w-4 h-4" />
                                                        </button>
                                                        <button
                                                            onClick={() => setItemToDelete(product.id)}
                                                            disabled={editingId !== null}
                                                            className="p-1.5 rounded-md text-text-muted hover:text-danger hover:bg-red-50 transition-colors disabled:opacity-30"
                                                            title="Delete"
                                                        >
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
                                    <td colSpan={7} className="px-4 py-10 text-center text-text-muted text-sm">
                                        No products found
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
                onConfirm={deleteProduct}
                title="Delete Product"
                message="Are you sure you want to delete this product? This action cannot be undone."
                confirmText="Delete Product"
            />
        </div>
    )
}
