import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { Link } from 'react-router-dom'
import { uploadReceipt } from '../api'

const PHOTO_TYPES = 'image/jpeg,image/png,image/webp'
const ACCEPT = `${PHOTO_TYPES},application/pdf`

interface UploadState {
  key: string
  name: string
  status: 'uploading' | 'done' | 'error'
  receiptId?: number
  needsReview?: boolean
  error?: string
}

export function UploadDropzone() {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const cameraRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [uploads, setUploads] = useState<UploadState[]>([])

  const update = (key: string, changes: Partial<UploadState>) =>
    setUploads((current) => current.map((u) => (u.key === key ? { ...u, ...changes } : u)))

  async function uploadAll(files: File[]) {
    const batch = files.map((file) => ({ file, key: crypto.randomUUID() }))
    setUploads((current) => [
      ...batch.map(({ file, key }) => ({ key, name: file.name, status: 'uploading' as const })),
      ...current,
    ])
    // One at a time: each upload waits for extraction, and the LLM has rate limits.
    for (const { file, key } of batch) {
      try {
        const receipt = await uploadReceipt(file)
        update(key, { status: 'done', receiptId: receipt.id, needsReview: receipt.needs_review })
      } catch (error) {
        update(key, { status: 'error', error: (error as Error).message })
      }
    }
    await queryClient.invalidateQueries({ queryKey: ['receipts'] })
    await queryClient.invalidateQueries({ queryKey: ['spending'] })
    await queryClient.invalidateQueries({ queryKey: ['me'] }) // demo request count
  }

  function onDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    uploadAll([...event.dataTransfer.files])
  }

  function onChoose(event: ChangeEvent<HTMLInputElement>) {
    uploadAll([...(event.target.files ?? [])])
    event.target.value = '' // allow choosing the same file again
  }

  return (
    <section>
      <div
        className={`dropzone${dragging ? ' dragging' : ''}`}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <p>
          <strong>Drop receipts here</strong> or{' '}
          <button type="button" className="link-button" onClick={() => inputRef.current?.click()}>
            choose files
          </button>
        </p>
        <p className="muted">Photos, screenshots, or PDFs, up to 10 MB each.</p>
        {/* Touch screens only: desktop browsers ignore `capture` and would show a file picker. */}
        <button type="button" className="primary touch-only" onClick={() => cameraRef.current?.click()}>
          Take photo
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          hidden
          aria-label="Upload receipts"
          onChange={onChoose}
        />
        <input
          ref={cameraRef}
          type="file"
          accept={PHOTO_TYPES}
          capture="environment"
          hidden
          aria-label="Take a photo of a receipt"
          onChange={onChoose}
        />
      </div>

      {uploads.length > 0 && (
        <ul className="upload-list" aria-live="polite">
          {uploads.map((upload) => (
            <li key={upload.key}>
              <span className="upload-name">{upload.name}</span>
              {upload.status === 'uploading' && <span className="muted">Reading receipt…</span>}
              {upload.status === 'done' && (
                <Link to={`/receipts/${upload.receiptId}`}>
                  {upload.needsReview ? 'Added, needs review' : 'Added'}
                </Link>
              )}
              {upload.status === 'error' && <span className="error-text">{upload.error}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
