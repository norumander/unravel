import { useCallback, useEffect, useState } from 'react'

export interface ToastMessage {
  id: number
  type: 'warning' | 'error'
  message: string
}

let nextId = 0

export function useToast() {
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  const addToast = useCallback((type: 'warning' | 'error', message: string) => {
    const id = nextId++
    setToasts((prev) => [...prev, { id, type, message }])

    // Auto-dismiss warnings after 8 seconds
    if (type === 'warning') {
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id))
      }, 8000)
    }
  }, [])

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return { toasts, addToast, dismissToast }
}

interface ToastContainerProps {
  toasts: ToastMessage[]
  onDismiss: (id: number) => void
}

export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  if (toasts.length === 0) return null

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2" style={{ maxWidth: '420px' }}>
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  )
}

function ToastItem({ toast, onDismiss }: { toast: ToastMessage; onDismiss: (id: number) => void }) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    // Trigger entrance animation
    requestAnimationFrame(() => setVisible(true))
  }, [])

  const isWarning = toast.type === 'warning'

  return (
    <div
      className={`flex items-start gap-3 rounded-lg border px-4 py-3 text-sm shadow-lg transition-all duration-300 ${
        visible ? 'translate-x-0 opacity-100' : 'translate-x-4 opacity-0'
      } ${
        isWarning
          ? 'border-amber-500/30 bg-amber-950/90 text-amber-200'
          : 'border-red-500/30 bg-red-950/90 text-red-200'
      }`}
    >
      <span className={`mt-0.5 flex-shrink-0 text-base ${isWarning ? 'text-amber-400' : 'text-red-400'}`}>
        {isWarning ? '⚠' : '✕'}
      </span>
      <p className="flex-1 leading-relaxed">{toast.message}</p>
      <button
        onClick={() => onDismiss(toast.id)}
        className="flex-shrink-0 p-0.5 text-zinc-500 hover:text-zinc-300"
        aria-label="Dismiss"
      >
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" className="h-3 w-3">
          <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
        </svg>
      </button>
    </div>
  )
}
