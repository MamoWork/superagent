import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'

type ToastTone = 'info' | 'error'

interface ToastState {
  id: number
  message: string
  tone: ToastTone
}

interface ToastContextValue {
  toast: (message: string, tone?: ToastTone) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState<ToastState | null>(null)
  const timer = useRef<number | null>(null)
  const nextId = useRef(0)

  const toast = useCallback((message: string, tone: ToastTone = 'info') => {
    nextId.current += 1
    setCurrent({ id: nextId.current, message, tone })
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      setCurrent(null)
      timer.current = null
    }, 2_400)
  }, [])

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current)
    },
    [],
  )

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div
        className={`toast${current ? ' show' : ''}${current?.tone === 'error' ? ' error' : ''}`}
        role="status"
        aria-live="polite"
      >
        {current?.message || ''}
      </div>
    </ToastContext.Provider>
  )
}

// The hook shares this module with the provider; splitting it would only add
// indirection, so opt out of the fast-refresh boundary check here.
// eslint-disable-next-line react-refresh/only-export-components
export function useToast(): ToastContextValue {
  const value = useContext(ToastContext)
  if (!value) throw new Error('useToast must be used inside ToastProvider')
  return value
}
