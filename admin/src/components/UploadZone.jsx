import { useState, useRef } from 'react'
import { Upload, FileText, X, AlertCircle } from 'lucide-react'

const VALID_EXTENSIONS = ['pdf', 'docx', 'pptx', 'txt']
const VALID_MIME_TYPES = [
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'text/plain',
]
const MAX_FILE_SIZE = 50 * 1024 * 1024 // 50 MB

function validateFile(file) {
    const ext = file.name.split('.').pop().toLowerCase()
    if (!VALID_MIME_TYPES.includes(file.type) && !VALID_EXTENSIONS.includes(ext)) {
        return `Unsupported file type (.${ext}). Only PDF, DOCX, PPTX, TXT allowed.`
    }
    if (file.size > MAX_FILE_SIZE) {
        return `File too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Max 50 MB.`
    }
    return null
}

export default function UploadZone({ onUpload, disabled = false }) {
    const [dragActive, setDragActive] = useState(false)
    const [selectedFiles, setSelectedFiles] = useState([]) // { file, error? }[]
    const inputRef = useRef(null)

    const addFiles = (fileList) => {
        const incoming = Array.from(fileList).map((file) => ({
            file,
            error: validateFile(file),
        }))
        setSelectedFiles((prev) => [...prev, ...incoming])
    }

    const handleDrag = (e) => {
        e.preventDefault()
        e.stopPropagation()
        if (e.type === 'dragenter' || e.type === 'dragover') {
            setDragActive(true)
        } else if (e.type === 'dragleave') {
            setDragActive(false)
        }
    }

    const handleDrop = (e) => {
        e.preventDefault()
        e.stopPropagation()
        setDragActive(false)
        if (e.dataTransfer.files?.length) {
            addFiles(e.dataTransfer.files)
        }
    }

    const handleChange = (e) => {
        if (e.target.files?.length) {
            addFiles(e.target.files)
        }
        // Reset input so the same files can be re-selected if removed
        if (inputRef.current) inputRef.current.value = ''
    }

    const removeFile = (index) => {
        setSelectedFiles((prev) => prev.filter((_, i) => i !== index))
    }

    const validFiles = selectedFiles.filter((f) => !f.error)

    const handleSubmit = () => {
        if (validFiles.length > 0 && onUpload) {
            onUpload(validFiles.map((f) => f.file))
            setSelectedFiles([])
        }
    }

    const clearAll = () => {
        setSelectedFiles([])
        if (inputRef.current) inputRef.current.value = ''
    }

    return (
        <div className="space-y-3">
            {/* Drop zone */}
            <div
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={() => !disabled && inputRef.current?.click()}
                className={`
          relative flex flex-col items-center justify-center gap-3 p-8
          rounded-xl border-2 border-dashed cursor-pointer transition-colors
          ${dragActive
                        ? 'border-accent bg-accent-light'
                        : 'border-border hover:border-text-muted bg-bg-secondary'
                    }
          ${disabled ? 'opacity-50 pointer-events-none' : ''}
        `}
            >
                <input
                    ref={inputRef}
                    type="file"
                    accept=".pdf,.docx,.pptx,.txt"
                    multiple
                    className="hidden"
                    onChange={handleChange}
                />

                <div className={`w-10 h-10 rounded-lg flex items-center justify-center transition-colors
          ${dragActive ? 'bg-accent/10' : 'bg-bg-tertiary'}`}>
                    <Upload className={`w-5 h-5 ${dragActive ? 'text-accent' : 'text-text-muted'}`} />
                </div>

                <div className="text-center">
                    <p className="text-sm font-medium text-text-primary">
                        {dragActive ? 'Drop documents here' : 'Drag & drop documents'}
                    </p>
                    <p className="text-xs text-text-muted mt-1">
                        or click to browse · PDF, DOCX, PPTX, TXT · max 50 MB each
                    </p>
                </div>
            </div>

            {/* Selected files list */}
            {selectedFiles.length > 0 && (
                <div className="space-y-2">
                    <div className="flex items-center justify-between">
                        <p className="text-xs font-medium text-text-secondary">
                            {validFiles.length} file{validFiles.length !== 1 ? 's' : ''} ready
                            {selectedFiles.length - validFiles.length > 0 &&
                                ` · ${selectedFiles.length - validFiles.length} rejected`}
                        </p>
                        <button
                            onClick={(e) => { e.stopPropagation(); clearAll() }}
                            className="text-xs text-text-muted hover:text-danger transition-colors"
                        >
                            Clear all
                        </button>
                    </div>

                    <div className="max-h-60 overflow-y-auto space-y-1.5 pr-1">
                        {selectedFiles.map((entry, idx) => (
                            <div
                                key={`${entry.file.name}-${idx}`}
                                className={`card p-2.5 flex items-center gap-3 animate-fade-in ${entry.error ? 'border border-red-300 bg-red-50/50' : ''
                                    }`}
                            >
                                <div className="w-8 h-8 rounded-lg bg-bg-tertiary flex items-center justify-center shrink-0">
                                    {entry.error ? (
                                        <AlertCircle className="w-4 h-4 text-danger" />
                                    ) : (
                                        <FileText className="w-4 h-4 text-text-muted" />
                                    )}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium text-text-primary truncate">
                                        {entry.file.name}
                                    </p>
                                    {entry.error ? (
                                        <p className="text-xs text-danger">{entry.error}</p>
                                    ) : (
                                        <p className="text-xs text-text-muted">
                                            {(entry.file.size / 1024 / 1024).toFixed(2)} MB
                                        </p>
                                    )}
                                </div>
                                <button
                                    onClick={(e) => { e.stopPropagation(); removeFile(idx) }}
                                    className="p-1 rounded-md hover:bg-bg-tertiary text-text-muted hover:text-danger transition-colors"
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>
                        ))}
                    </div>

                    {validFiles.length > 0 && (
                        <button
                            onClick={handleSubmit}
                            disabled={disabled}
                            className="w-full px-4 py-2.5 rounded-lg bg-accent hover:bg-accent-hover text-white text-sm font-medium transition-colors disabled:opacity-50"
                        >
                            Upload {validFiles.length} document{validFiles.length !== 1 ? 's' : ''}
                        </button>
                    )}
                </div>
            )}
        </div>
    )
}
