import { useCallback, useEffect, useRef, useState } from 'react'
import { createWebSocket } from '../api/client'
import type { ClosedTrade, LogEntry, StrategyCatalog, WSMessage, WorkspaceState } from '../types'

const MAX_LOGS = 500
const RECONNECT_DELAY_MS = 3000

export function useWebSocket() {
  const [connected, setConnected] = useState(false)
  const [workspaceState, setWorkspaceState] = useState<WorkspaceState | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [history, setHistory] = useState<ClosedTrade[]>([])
  const [catalog, setCatalog] = useState<StrategyCatalog | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  const connect = useCallback(() => {
    if (!mountedRef.current) return

    try {
      const ws = createWebSocket()
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        // Send heartbeat every 20s
        const ping = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send('ping')
          else clearInterval(ping)
        }, 20_000)
      }

      ws.onmessage = (e) => {
        try {
          const msg: WSMessage = JSON.parse(e.data)
          if (msg.type === 'log') {
            setLogs((prev) => {
              const next = [...prev, msg.data]
              return next.length > MAX_LOGS ? next.slice(next.length - MAX_LOGS) : next
            })
          } else if (msg.type === 'state') {
            setWorkspaceState(msg.data)
          } else if (msg.type === 'history') {
            setHistory(msg.data)
          }
        } catch {
          // ignore malformed messages
        }
      }

      ws.onerror = () => {
        // onerror is always followed by onclose
      }

      ws.onclose = () => {
        setConnected(false)
        if (mountedRef.current) {
          reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)
        }
      }
    } catch {
      if (mountedRef.current) {
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)
      }
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { connected, workspaceState, setWorkspaceState, logs, history, catalog, setCatalog }
}
