import { useEffect, useRef, useState } from 'react'
import type { LogEntry } from '../types'

const LEVEL_COLOR: Record<string, string> = {
  DEBUG: 'text-gray-600',
  INFO: 'text-cyan-400',
  WARNING: 'text-yellow-400',
  ERROR: 'text-red-400',
  CRITICAL: 'text-red-400 font-bold',
}

const LEVEL_FILTER_OPTIONS = ['ALL', 'INFO', 'WARNING', 'ERROR'] as const
type LevelFilter = (typeof LEVEL_FILTER_OPTIONS)[number]

function fmtTs(ts: number): string {
  return new Date(ts * 1000).toTimeString().slice(0, 8)
}

interface Props {
  logs: LogEntry[]
}

export function LogFeed({ logs }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [levelFilter, setLevelFilter] = useState<LevelFilter>('ALL')
  const [search, setSearch] = useState('')
  // Track whether the *user* initiated the last scroll
  const userScrolling = useRef(false)
  const scrollTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

  const filtered = logs.filter((l) => {
    if (levelFilter !== 'ALL' && l.level !== levelFilter) return false
    if (search && !l.message.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  // Auto-scroll: runs after each render when enabled
  useEffect(() => {
    if (!autoScroll) return
    const el = containerRef.current
    if (!el) return
    // Instant scroll — no smooth, so it doesn't fight user scroll
    el.scrollTop = el.scrollHeight
  })

  // Detect user scrolling up → pause auto-scroll
  function onScroll() {
    const el = containerRef.current
    if (!el) return

    // If this scroll was triggered by our auto-scroll code, ignore it
    if (!userScrolling.current) return

    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    const atBottom = distanceFromBottom < 60

    if (!atBottom && autoScroll) {
      setAutoScroll(false)
    } else if (atBottom && !autoScroll) {
      setAutoScroll(true)
    }
  }

  // Mark user-initiated scrolls
  function onWheel() {
    userScrolling.current = true
    if (scrollTimeout.current) clearTimeout(scrollTimeout.current)
    scrollTimeout.current = setTimeout(() => {
      userScrolling.current = false
    }, 150)
  }

  function scrollToBottom() {
    const el = containerRef.current
    if (el) el.scrollTop = el.scrollHeight
    setAutoScroll(true)
  }

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-gray-950 border border-gray-800 rounded-lg overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-800 bg-gray-900 shrink-0">
        <span className="text-xs text-gray-500 uppercase tracking-widest font-mono mr-1">
          Log
        </span>

        {LEVEL_FILTER_OPTIONS.map((l) => (
          <button
            key={l}
            onClick={() => setLevelFilter(l)}
            className={`text-[10px] px-2 py-0.5 rounded font-mono transition-colors ${
              levelFilter === l
                ? 'bg-gray-700 text-gray-100'
                : 'text-gray-600 hover:text-gray-400'
            }`}
          >
            {l}
          </button>
        ))}

        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="filter…"
          className="ml-auto bg-gray-800 border border-gray-700 rounded px-2 py-0.5
                     text-xs font-mono text-gray-300 placeholder-gray-600
                     focus:outline-none focus:border-gray-600 w-32"
        />

        <span className="text-gray-700 text-[10px] font-mono shrink-0">
          {filtered.length}/{logs.length}
        </span>
      </div>

      {/* Log lines */}
      <div className="relative flex-1 overflow-hidden">
        <div
          ref={containerRef}
          onScroll={onScroll}
          onWheel={onWheel}
          className="h-full overflow-y-auto font-mono text-xs leading-relaxed"
          style={{ scrollbarWidth: 'thin', scrollbarColor: '#374151 transparent' }}
        >
          {filtered.length === 0 ? (
            <div className="text-gray-700 text-center py-8">
              {logs.length === 0 ? 'waiting for logs…' : 'no matching entries'}
            </div>
          ) : (
            filtered.map((log, i) => (
              <div
                key={i}
                className="flex gap-3 px-3 py-0.5 hover:bg-gray-900/50"
              >
                <span className="text-gray-700 shrink-0 select-none">{fmtTs(log.ts)}</span>
                <span className={`w-7 shrink-0 ${LEVEL_COLOR[log.level] ?? 'text-gray-400'}`}>
                  {log.level.slice(0, 4)}
                </span>
                <span className="text-gray-400 break-all">{log.message}</span>
              </div>
            ))
          )}
        </div>

        {/* "Back to bottom" button — only visible when paused */}
        {!autoScroll && (
          <button
            onClick={scrollToBottom}
            className="absolute bottom-3 right-4 flex items-center gap-1.5 px-3 py-1.5
                       bg-gray-800 border border-gray-600 rounded-full
                       text-xs font-mono text-gray-300 hover:text-white hover:border-green-500
                       shadow-lg transition-colors"
          >
            <span>↓</span>
            <span>resume</span>
          </button>
        )}
      </div>
    </div>
  )
}
