import { useState, useEffect, useRef, useCallback } from 'react'
import { supabase } from '../lib/supabase'
import { FileText, CheckCircle, AlertCircle, Clock, Loader2, Trash2, Upload, AlertTriangle } from 'lucide-react'
import UploadZone from '../components/UploadZone'
import { toast } from 'sonner'
import ConfirmModal from '../components/ConfirmModal'

const API_BASE = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'

const statusConfig = {
    ready: { icon: CheckCircle, color: 'text-success', bg: 'bg-green-50', label: 'Ready' },
    indexing: { icon: Loader2, color: 'text-accent', bg: 'bg-accent-light', label: 'Indexing' },
    pending: { icon: Clock, color: 'text-warning', bg: 'bg-yellow-50', label: 'Pending' },
    error: { icon: AlertCircle, color: 'text-danger', bg: 'bg-red-50', label: 'Error' },
}

// Per-file statuses for the upload queue
const queueStatusConfig = {
    queued:       { icon: Clock,        color: 'text-text-muted', bg: 'bg-bg-tertiary',   label: 'Queued' },
    uploading:    { icon: Loader2,      color: 'text-accent',     bg: 'bg-accent-light',  label: 'Uploading' },
    processing:   { icon: Loader2,      color: 'text-accent',     bg: 'bg-accent-light',  label: 'Processing' },
    indexing:     { icon: Loader2,      color: 'text-accent',     bg: 'bg-accent-light',  label: 'Indexing' },
    indexing_ocr: { icon: Loader2,      color: 'text-amber-600',  bg: 'bg-amber-50',      label: 'OCR Processing' },
    ready:        { icon: CheckCircle,  color: 'text-success',    bg: 'bg-green-50',      label: 'Ready' },
    failed:       { icon: AlertCircle,  color: 'text-danger',     bg: 'bg-red-50',        label: 'Failed' },
    error:        { icon: AlertCircle,  color: 'text-danger',     bg: 'bg-red-50',        label: 'Failed' },
}

export default function Knowledge() {
    const [docs, setDocs] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    // Upload queue: { id, fileName, status, jobId?, error? }[]
    const [uploadQueue, setUploadQueue] = useState([])
    const pollingRef = useRef(null)

    useEffect(() => {
        fetchDocs()
        return () => {
            if (pollingRef.current) clearInterval(pollingRef.current)
        }
    }, [])

    const fetchDocs = async () => {
        try {
            setLoading(true)
            const { data, error } = await supabase
                .from('knowledge_base')
                .select('*')
                .order('created_at', { ascending: false })

            if (error) throw error
            setDocs(data || [])
        } catch (err) {
            console.error('Error fetching knowledge base:', err)
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    // Poll for job statuses until all are terminal (ready / error / failed)
    const startPolling = useCallback((queueItems) => {
        if (pollingRef.current) clearInterval(pollingRef.current)

        pollingRef.current = setInterval(async () => {
            const { data: { session } } = await supabase.auth.getSession()
            if (!session) return

            let allDone = true
            const updates = {}

            for (const item of queueItems) {
                if (!item.jobId) continue
                if (['ready', 'failed', 'error'].includes(item.status)) continue

                allDone = false
                try {
                    const res = await fetch(`${API_BASE}/admin/upload/status/${item.jobId}`, {
                        headers: { 'Authorization': `Bearer ${session.access_token}` },
                    })
                    if (res.ok) {
                        const data = await res.json()
                        // Use a special status for OCR-in-progress documents
                        let displayStatus = data.status
                        if (data.ocr_required && data.status === 'indexing') {
                            displayStatus = 'indexing_ocr'
                        }
                        updates[item.id] = {
                            status: displayStatus,
                            error: data.error || null,
                            ocrWarning: data.ocr_warning || null,
                        }
                    }
                } catch (e) {
                    console.error(`Poll error for ${item.jobId}:`, e)
                }
            }

            if (Object.keys(updates).length > 0) {
                setUploadQueue((prev) => {
                    const next = prev.map((q) => {
                        if (updates[q.id]) {
                            return { ...q, ...updates[q.id] }
                        }
                        return q
                    })
                    // Update queueItems reference for next poll iteration
                    queueItems = next
                    return next
                })

                // Refresh doc list if any became ready
                const anyReady = Object.values(updates).some((u) => u.status === 'ready')
                if (anyReady) fetchDocs()
            }

            // Check if all items in the queue are done
            const currentQueue = queueItems
            const stillPending = currentQueue.some(
                (q) => q.jobId && !['ready', 'failed', 'error'].includes(q.status)
            )
            if (!stillPending) {
                clearInterval(pollingRef.current)
                pollingRef.current = null
                fetchDocs()
            }
        }, 2500)
    }, [])

    const handleUpload = async (files) => {
        setError(null)

        // Build queue entries
        const newQueue = files.map((file, idx) => ({
            id: `upload-${Date.now()}-${idx}`,
            fileName: file.name,
            fileSize: file.size,
            status: 'queued',
            jobId: null,
            error: null,
        }))

        setUploadQueue((prev) => [...newQueue, ...prev])

        // Mark all as uploading
        setUploadQueue((prev) =>
            prev.map((q) =>
                newQueue.find((n) => n.id === q.id) ? { ...q, status: 'uploading' } : q
            )
        )

        try {
            const { data: { session } } = await supabase.auth.getSession()
            if (!session) throw new Error('Not authenticated')

            const formData = new FormData()
            files.forEach((file) => formData.append('files', file))

            const res = await fetch(`${API_BASE}/admin/upload/batch`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${session.access_token}` },
                body: formData,
            })

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}))
                throw new Error(errData.detail || `Upload failed (${res.status})`)
            }

            const results = await res.json()

            // Map backend results back to queue items
            setUploadQueue((prev) => {
                const updated = prev.map((q) => {
                    const match = results.find((r) => r.filename === q.fileName)
                    if (match && newQueue.find((n) => n.id === q.id)) {
                        return {
                            ...q,
                            jobId: match.job_id || null,
                            status: match.status === 'failed' ? 'failed' : 'processing',
                            error: match.error || null,
                            storedFilename: match.stored_filename || q.fileName,
                        }
                    }
                    return q
                })

                // Start polling for jobs that are processing
                const toTrack = updated.filter(
                    (q) => q.jobId && !['ready', 'failed', 'error'].includes(q.status)
                )
                if (toTrack.length > 0) {
                    startPolling(updated)
                } else {
                    // All done already (all failed at validation)
                    fetchDocs()
                }

                return updated
            })
        } catch (err) {
            console.error('Batch upload error:', err)
            setError(err.message || 'Failed to upload documents')
            // Mark all as failed
            setUploadQueue((prev) =>
                prev.map((q) =>
                    newQueue.find((n) => n.id === q.id)
                        ? { ...q, status: 'failed', error: err.message }
                        : q
                )
            )
        }
    }

    const clearQueueItem = (id) => {
        setUploadQueue((prev) => prev.filter((q) => q.id !== id))
    }

    const clearFinishedQueue = () => {
        setUploadQueue((prev) => prev.filter((q) => !['ready', 'failed', 'error'].includes(q.status)))
    }

    const [itemToDelete, setItemToDelete] = useState(null)

    const handleDelete = async () => {
        if (!itemToDelete) return;
        const { id, fileName } = itemToDelete;
        
        try {
            const { error } = await supabase
                .from('knowledge_base')
                .delete()
                .eq('id', id)
            if (error) throw error

            await supabase.storage.from('manuals').remove([fileName])
            setDocs(prev => prev.filter(d => d.id !== id))
            toast.success(`Successfully deleted ${fileName}`)
        } catch (err) {
            toast.error('Failed to delete: ' + err.message)
        } finally {
            setItemToDelete(null)
        }
    }

    const totalChunks = docs.reduce((sum, d) => sum + (d.chunks_count || 0), 0)
    const hasActiveUploads = uploadQueue.some((q) => !['ready', 'failed', 'error'].includes(q.status))
    const hasFinishedItems = uploadQueue.some((q) => ['ready', 'failed', 'error'].includes(q.status))

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-xl font-semibold text-text-primary">Knowledge Base</h1>
                <p className="text-sm text-text-muted mt-0.5">
                    Upload manuals & policies to power AURA's responses
                </p>
            </div>

            {error && (
                <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg">
                    {error}
                </div>
            )}

            {/* Stats row */}
            <div className="flex flex-wrap gap-3">
                {[
                    { label: 'Documents', value: docs.length },
                    { label: 'Chunks', value: totalChunks },
                    { label: 'Ready', value: docs.filter(d => d.status === 'ready').length },
                ].map((s) => (
                    <div key={s.label} className="card px-4 py-3 flex items-center gap-3">
                        <div>
                            <p className="text-lg font-semibold text-text-primary">{s.value}</p>
                            <p className="text-xs text-text-muted">{s.label}</p>
                        </div>
                    </div>
                ))}
            </div>

            {/* Upload zone */}
            <div className="card p-5">
                <h2 className="text-sm font-medium text-text-secondary mb-3">
                    Upload Documents
                </h2>
                <UploadZone onUpload={handleUpload} disabled={hasActiveUploads} />
            </div>

            {/* Upload queue */}
            {uploadQueue.length > 0 && (
                <div className="card overflow-hidden">
                    <div className="px-5 py-4 border-b border-border flex items-center justify-between">
                        <h2 className="text-sm font-semibold text-text-primary">
                            Upload Queue
                            {hasActiveUploads && (
                                <span className="ml-2 text-xs font-normal text-text-muted">
                                    ({uploadQueue.filter(q => !['ready', 'failed', 'error'].includes(q.status)).length} in progress)
                                </span>
                            )}
                        </h2>
                        {hasFinishedItems && !hasActiveUploads && (
                            <button
                                onClick={clearFinishedQueue}
                                className="text-xs text-text-muted hover:text-text-primary transition-colors"
                            >
                                Clear finished
                            </button>
                        )}
                    </div>
                    <div className="divide-y divide-border">
                        {uploadQueue.map((item) => {
                            const cfg = queueStatusConfig[item.status] || queueStatusConfig.queued
                            const QueueIcon = cfg.icon

                            return (
                                <div
                                    key={item.id}
                                    className="flex items-center gap-4 px-5 py-3 hover:bg-bg-secondary transition-colors"
                                >
                                    <div className="w-8 h-8 rounded-lg bg-bg-tertiary flex items-center justify-center shrink-0">
                                        <Upload className="w-4 h-4 text-text-muted" />
                                    </div>

                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium text-text-primary truncate">
                                            {item.storedFilename || item.fileName}
                                        </p>
                                        {item.error && (
                                            <p className="text-xs text-danger truncate">{item.error}</p>
                                        )}
                                        {item.ocrWarning && !item.error && (
                                            <p className="text-xs text-amber-600 flex items-center gap-1 mt-0.5">
                                                <AlertTriangle className="w-3 h-3 shrink-0" />
                                                {item.ocrWarning}
                                            </p>
                                        )}
                                        {!item.error && !item.ocrWarning && item.fileSize && (
                                            <p className="text-xs text-text-muted">
                                                {(item.fileSize / 1024 / 1024).toFixed(2)} MB
                                            </p>
                                        )}
                                    </div>

                                    <div className={`flex items-center gap-1.5 px-2 py-1 rounded-md ${cfg.bg}`}>
                                        <QueueIcon
                                            className={`w-3.5 h-3.5 ${cfg.color} ${
                                                ['uploading', 'processing', 'indexing', 'indexing_ocr'].includes(item.status) ? 'animate-spin' : ''
                                            }`}
                                        />
                                        <span className={`text-xs font-medium ${cfg.color}`}>{cfg.label}</span>
                                    </div>

                                    {['ready', 'failed', 'error'].includes(item.status) && (
                                        <button
                                            onClick={() => clearQueueItem(item.id)}
                                            className="p-1 rounded-md text-text-muted hover:text-text-primary transition-colors"
                                            title="Dismiss"
                                        >
                                            <span className="text-xs">✕</span>
                                        </button>
                                    )}
                                </div>
                            )
                        })}
                    </div>
                </div>
            )}

            {/* Knowledge list */}
            <div className="card overflow-hidden">
                <div className="px-5 py-4 border-b border-border">
                    <h2 className="text-sm font-semibold text-text-primary">Indexed Documents</h2>
                </div>
                {loading && docs.length === 0 ? (
                    <div className="p-8 flex justify-center">
                        <Loader2 className="w-5 h-5 animate-spin text-accent" />
                    </div>
                ) : (
                    <div className="divide-y divide-border">
                        {docs.length === 0 ? (
                            <div className="p-8 text-center text-text-muted text-sm">
                                No documents indexed yet. Upload a file above.
                            </div>
                        ) : (
                            docs.map((doc) => {
                                const cfg = statusConfig[doc.status] || statusConfig.pending
                                const StatusIcon = cfg.icon

                                return (
                                    <div
                                        key={doc.id}
                                        className="flex items-center gap-4 px-5 py-3 hover:bg-bg-secondary transition-colors"
                                    >
                                        <div className="w-8 h-8 rounded-lg bg-bg-tertiary flex items-center justify-center shrink-0">
                                            <FileText className="w-4 h-4 text-text-muted" />
                                        </div>

                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium text-text-primary truncate">{doc.file_name}</p>
                                            <p className="text-xs text-text-muted">
                                                {doc.document_type} · {doc.chunks_count || 0} chunks
                                                {doc.last_indexed && ` · ${new Date(doc.last_indexed).toLocaleDateString()}`}
                                            </p>
                                        </div>

                                        <div className={`flex items-center gap-1.5 px-2 py-1 rounded-md ${cfg.bg}`}>
                                            <StatusIcon className={`w-3.5 h-3.5 ${cfg.color} ${doc.status === 'indexing' ? 'animate-spin' : ''}`} />
                                            <span className={`text-xs font-medium ${cfg.color}`}>{cfg.label}</span>
                                        </div>

                                        <button
                                            onClick={() => setItemToDelete({ id: doc.id, fileName: doc.file_name })}
                                            className="p-1.5 rounded-lg text-text-muted hover:text-danger hover:bg-red-50 transition-colors"
                                            title="Delete"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                )
                            })
                        )}
                    </div>
                )}
            </div>

            <ConfirmModal 
                isOpen={!!itemToDelete}
                onClose={() => setItemToDelete(null)}
                onConfirm={handleDelete}
                title="Delete Document"
                message={`Are you sure you want to delete ${itemToDelete?.fileName}? This action cannot be undone.`}
                confirmText="Delete Document"
            />
        </div>
    )
}
