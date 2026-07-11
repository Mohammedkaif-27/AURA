import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabase'
import { Plus, Pencil, Trash2, X, Check, Loader2, AlertCircle, Shield, Globe, Tag } from 'lucide-react'
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

const POLICY_TYPES = ['refund', 'replacement', 'warranty']
const SCOPE_OPTIONS = ['global', 'category']

const TYPE_COLORS = {
    refund: 'bg-orange-50 text-orange-700',
    replacement: 'bg-purple-50 text-purple-700',
    warranty: 'bg-blue-50 text-blue-700',
}

// Default rule templates per policy type
const RULE_TEMPLATES = {
    refund: { window_days: 30, requires_original_packaging: true, restocking_fee_percent: 0 },
    replacement: { window_days: 15, requires_defect_proof: true, max_replacements: 1 },
    warranty: { duration_months: 12, covers_accidental_damage: false, requires_registration: false },
}

export default function Policies() {
    const [policies, setPolicies] = useState([])
    const [categories, setCategories] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [editingId, setEditingId] = useState(null)
    const [editData, setEditData] = useState({})
    const [isAdding, setIsAdding] = useState(false)
    const [validationErrors, setValidationErrors] = useState({})
    const [saving, setSaving] = useState(false)

    useEffect(() => {
        fetchPolicies()
        fetchCategories()
    }, [])

    const fetchPolicies = async () => {
        try {
            setLoading(true)
            const data = await apiFetch('/admin/policies')
            setPolicies(Array.isArray(data) ? data : [])
        } catch (err) {
            // Table may not exist yet, that's OK
            setPolicies([])
            if (!err.message?.includes('does not exist')) {
                setError(err.message)
            }
        } finally {
            setLoading(false)
        }
    }

    const fetchCategories = async () => {
        try {
            const { data } = await supabase.from('products').select('category')
            const cats = [...new Set((data || []).map(p => p.category).filter(Boolean))]
            setCategories(cats)
        } catch { }
    }

    const validate = () => {
        const errs = {}
        if (!editData.policy_type) errs.policy_type = 'Required'
        if (!editData.scope) errs.scope = 'Required'
        if (editData.scope === 'category' && (!editData.category || !editData.category.trim())) errs.category = 'Required for category scope'
        if (!editData.description || !editData.description.trim()) errs.description = 'Description is required for RAG'
        setValidationErrors(errs)
        return Object.keys(errs).length === 0
    }

    const startEdit = (policy) => {
        setEditingId(policy.id)
        setEditData({ ...policy, rules: policy.rules || {} })
        setValidationErrors({})
    }

    const saveEdit = async () => {
        if (!validate()) return
        setSaving(true)
        try {
            const payload = {
                ...editData,
                category: editData.scope === 'global' ? null : editData.category,
            }
            if (isAdding) {
                await apiFetch('/admin/policies', { method: 'POST', body: JSON.stringify(payload) })
            } else {
                await apiFetch(`/admin/policies/${editingId}`, { method: 'PUT', body: JSON.stringify(payload) })
            }
            await fetchPolicies()
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
        if (isAdding) setPolicies(prev => prev.filter(p => p.id !== editingId))
        setIsAdding(false)
        setEditingId(null)
        setEditData({})
        setValidationErrors({})
    }

    const [itemToDelete, setItemToDelete] = useState(null)

    const deletePolicy = async () => {
        if (!itemToDelete) return
        try {
            await apiFetch(`/admin/policies/${itemToDelete}`, { method: 'DELETE' })
            await fetchPolicies()
            toast.success('Policy deleted successfully')
        } catch (err) {
            toast.error(err.message)
        } finally {
            setItemToDelete(null)
        }
    }

    const handleAdd = () => {
        const newId = `POL-${Date.now()}`
        const newPolicy = {
            id: newId,
            policy_type: 'refund',
            scope: 'global',
            category: '',
            rules: { ...RULE_TEMPLATES.refund },
            description: '',
        }
        setPolicies([newPolicy, ...policies])
        setEditingId(newId)
        setEditData(newPolicy)
        setIsAdding(true)
        setValidationErrors({})
    }

    const handleTypeChange = (type) => {
        setEditData(prev => ({
            ...prev,
            policy_type: type,
            rules: { ...RULE_TEMPLATES[type] },
        }))
    }

    const updateRule = (key, value) => {
        setEditData(prev => ({
            ...prev,
            rules: { ...(prev.rules || {}), [key]: value },
        }))
    }

    const inputClass = "w-full px-2.5 py-1.5 rounded-md bg-bg border border-border text-sm text-text-primary focus:outline-none focus:border-accent transition-colors"
    const errorInputClass = "w-full px-2.5 py-1.5 rounded-md bg-bg border border-danger text-sm text-text-primary focus:outline-none focus:border-danger transition-colors"

    if (loading) {
        return (
            <div className="flex h-full items-center justify-center">
                <Loader2 className="w-6 h-6 animate-spin text-accent" />
            </div>
        )
    }

    // Group policies for summary
    const globalPolicies = policies.filter(p => p.scope === 'global')
    const categoryOverrides = policies.filter(p => p.scope === 'category')

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                    <h1 className="text-xl font-semibold text-text-primary">Policies</h1>
                    <p className="text-sm text-text-muted mt-0.5">Define refund, replacement & warranty rules. Category overrides take priority over global defaults.</p>
                </div>
                <button
                    onClick={handleAdd}
                    disabled={editingId !== null}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent hover:bg-accent-hover text-white text-sm font-medium transition-colors self-start disabled:opacity-50"
                >
                    <Plus className="w-4 h-4" />
                    Add Policy
                </button>
            </div>

            {error && (
                <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    {error}
                    <button onClick={() => setError(null)} className="ml-auto"><X className="w-3.5 h-3.5" /></button>
                </div>
            )}

            {/* Summary cards */}
            <div className="flex flex-wrap gap-3">
                <div className="card px-4 py-3">
                    <div className="flex items-center gap-2">
                        <Globe className="w-4 h-4 text-text-muted" />
                        <div>
                            <p className="text-lg font-semibold text-text-primary">{globalPolicies.length}</p>
                            <p className="text-xs text-text-muted">Global Policies</p>
                        </div>
                    </div>
                </div>
                <div className="card px-4 py-3">
                    <div className="flex items-center gap-2">
                        <Tag className="w-4 h-4 text-text-muted" />
                        <div>
                            <p className="text-lg font-semibold text-text-primary">{categoryOverrides.length}</p>
                            <p className="text-xs text-text-muted">Category Overrides</p>
                        </div>
                    </div>
                </div>
            </div>

            {/* Policies list */}
            <div className="space-y-4">
                {policies.map(policy => {
                    const isEditing = editingId === policy.id

                    if (isEditing) {
                        return (
                            <div key={policy.id} className="card p-5 border-accent/30 bg-accent-light/10 space-y-4">
                                <div className="flex items-center justify-between">
                                    <h3 className="text-sm font-semibold text-text-primary">
                                        {isAdding ? 'New Policy' : `Edit Policy: ${policy.id}`}
                                    </h3>
                                    <div className="flex items-center gap-1">
                                        <button onClick={saveEdit} disabled={saving} className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-accent text-white text-xs font-medium hover:bg-accent-hover transition-colors disabled:opacity-50">
                                            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                                            Save
                                        </button>
                                        <button onClick={cancelEdit} className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border text-text-secondary text-xs font-medium hover:bg-bg-tertiary transition-colors">
                                            <X className="w-3.5 h-3.5" /> Cancel
                                        </button>
                                    </div>
                                </div>

                                {/* Type + Scope row */}
                                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                                    <div>
                                        <label className="block text-xs font-medium text-text-muted mb-1">Policy Type *</label>
                                        <select value={editData.policy_type || ''} onChange={e => handleTypeChange(e.target.value)} className={validationErrors.policy_type ? errorInputClass : inputClass}>
                                            {POLICY_TYPES.map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
                                        </select>
                                        {validationErrors.policy_type && <p className="text-danger text-xs mt-0.5">{validationErrors.policy_type}</p>}
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-text-muted mb-1">Scope *</label>
                                        <select value={editData.scope || 'global'} onChange={e => setEditData({ ...editData, scope: e.target.value })} className={validationErrors.scope ? errorInputClass : inputClass}>
                                            {SCOPE_OPTIONS.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
                                        </select>
                                    </div>
                                    {editData.scope === 'category' && (
                                        <div>
                                            <label className="block text-xs font-medium text-text-muted mb-1">Category *</label>
                                            <div>
                                                <input
                                                    list="policy-categories"
                                                    value={editData.category || ''}
                                                    onChange={e => setEditData({ ...editData, category: e.target.value })}
                                                    className={validationErrors.category ? errorInputClass : inputClass}
                                                    placeholder="Select or type category"
                                                />
                                                <datalist id="policy-categories">
                                                    {categories.map(c => <option key={c} value={c} />)}
                                                </datalist>
                                            </div>
                                            {validationErrors.category && <p className="text-danger text-xs mt-0.5">{validationErrors.category}</p>}
                                        </div>
                                    )}
                                </div>

                                {/* Rules */}
                                <div>
                                    <label className="block text-xs font-medium text-text-muted mb-2">Rules (structured data for code enforcement)</label>
                                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                        {Object.entries(editData.rules || {}).map(([key, val]) => (
                                            <div key={key} className="flex items-center gap-2">
                                                <label className="text-xs text-text-secondary whitespace-nowrap min-w-[120px]">{key.replace(/_/g, ' ')}:</label>
                                                {typeof val === 'boolean' ? (
                                                    <button
                                                        type="button"
                                                        onClick={() => updateRule(key, !val)}
                                                        className={`px-2 py-1 rounded text-xs font-medium transition-colors ${val ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}
                                                    >
                                                        {val ? 'Yes' : 'No'}
                                                    </button>
                                                ) : (
                                                    <input
                                                        type="number"
                                                        value={val}
                                                        onChange={e => updateRule(key, Number(e.target.value))}
                                                        className={`${inputClass} w-20`}
                                                    />
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                {/* Description for RAG */}
                                <div>
                                    <label className="block text-xs font-medium text-text-muted mb-1">Description (indexed into RAG for chatbot retrieval) *</label>
                                    <textarea
                                        value={editData.description || ''}
                                        onChange={e => setEditData({ ...editData, description: e.target.value })}
                                        className={`${validationErrors.description ? errorInputClass : inputClass} min-h-[80px]`}
                                        rows={3}
                                        placeholder="E.g. 'Customers may request a refund within 30 days of purchase. Original packaging is required. No restocking fee applies.'"
                                    />
                                    {validationErrors.description && <p className="text-danger text-xs mt-0.5">{validationErrors.description}</p>}
                                </div>
                            </div>
                        )
                    }

                    // Read-only card
                    return (
                        <div key={policy.id} className="card p-5 hover:shadow-sm transition-shadow">
                            <div className="flex items-start justify-between gap-4">
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap mb-2">
                                        <span className={`inline-block px-2 py-0.5 rounded-md text-xs font-medium ${TYPE_COLORS[policy.policy_type] || 'bg-bg-tertiary text-text-secondary'}`}>
                                            {policy.policy_type}
                                        </span>
                                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium ${policy.scope === 'global' ? 'bg-blue-50 text-blue-600' : 'bg-green-50 text-green-600'}`}>
                                            {policy.scope === 'global' ? <Globe className="w-3 h-3" /> : <Tag className="w-3 h-3" />}
                                            {policy.scope === 'global' ? 'Global' : policy.category}
                                        </span>
                                        <span className="text-xs text-text-muted font-mono">{policy.id}</span>
                                    </div>

                                    {/* Rules preview */}
                                    {policy.rules && Object.keys(policy.rules).length > 0 && (
                                        <div className="flex flex-wrap gap-2 mb-2">
                                            {Object.entries(policy.rules).map(([k, v]) => (
                                                <span key={k} className="inline-block px-1.5 py-0.5 rounded bg-bg-tertiary text-xs text-text-secondary">
                                                    {k.replace(/_/g, ' ')}: <strong>{typeof v === 'boolean' ? (v ? '✓' : '✗') : v}</strong>
                                                </span>
                                            ))}
                                        </div>
                                    )}

                                    {policy.description && (
                                        <p className="text-sm text-text-secondary line-clamp-2">{policy.description}</p>
                                    )}
                                </div>

                                <div className="flex items-center gap-1 shrink-0">
                                    <button onClick={() => startEdit(policy)} disabled={editingId !== null} className="p-1.5 rounded-md text-text-muted hover:text-accent hover:bg-accent-light transition-colors disabled:opacity-30" title="Edit">
                                        <Pencil className="w-4 h-4" />
                                    </button>
                                    <button onClick={() => setItemToDelete(policy.id)} disabled={editingId !== null} className="p-1.5 rounded-md text-text-muted hover:text-danger hover:bg-red-50 transition-colors disabled:opacity-30" title="Delete">
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    )
                })}

                {policies.length === 0 && !isAdding && (
                    <div className="card p-10 text-center">
                        <Shield className="w-10 h-10 text-text-muted mx-auto mb-3" />
                        <p className="text-sm text-text-muted">No policies defined yet. Add a global policy to get started.</p>
                    </div>
                )}
            </div>

            <ConfirmModal 
                isOpen={!!itemToDelete}
                onClose={() => setItemToDelete(null)}
                onConfirm={deletePolicy}
                title="Delete Policy"
                message="Are you sure you want to delete this policy? This action cannot be undone."
                confirmText="Delete Policy"
            />
        </div>
    )
}
