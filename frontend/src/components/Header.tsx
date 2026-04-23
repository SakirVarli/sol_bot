import { useState } from 'react'
import { api } from '../api/client'
import type { WorkspaceState } from '../types'

interface Props {
  connected: boolean
  workspaceState: WorkspaceState | null
}

function fmtUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

export function Header({ connected, workspaceState }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const running = workspaceState?.running ?? false
  const paperLedger = workspaceState?.portfolio.ledgers.find((ledger) => ledger.mode === 'paper')
  const liveLedger = workspaceState?.portfolio.ledgers.find((ledger) => ledger.mode === 'live')

  async function handleStart() {
    setLoading(true)
    setError(null)
    try {
      await api.startWorkspace()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  async function handleStop() {
    setLoading(true)
    setError(null)
    try {
      await api.stopWorkspace()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <header className="flex items-center justify-between px-4 py-3 border-b border-gray-800 bg-gray-950">
      {/* Left: branding */}
      <div className="flex items-center gap-4">
        <span className="text-green-400 font-bold text-lg tracking-widest font-mono">
          SOL MEME BOT
        </span>

        {/* WS connection dot */}
        <span className="flex items-center gap-1.5 text-xs text-gray-500">
          <span
            className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-green-400' : 'bg-gray-600'}`}
          />
          {connected ? 'connected' : 'connecting…'}
        </span>
      </div>

      {/* Center: status indicators */}
      <div className="flex items-center gap-6 font-mono text-sm">
        {/* Running status */}
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full ${running ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`}
          />
          <span className={running ? 'text-green-400' : 'text-gray-500'}>
            {running ? 'RUNNING' : 'STOPPED'}
          </span>
        </div>

        {/* Mode badge */}
        <div className="text-gray-300">
          <span className="text-gray-500 text-xs mr-1">PAPER</span>
          <span>{paperLedger?.balance_sol.toFixed(4) ?? '0.0000'} SOL</span>
        </div>

        <div className="text-gray-300">
          <span className="text-gray-500 text-xs mr-1">LIVE</span>
          <span>{liveLedger?.balance_sol.toFixed(4) ?? '0.0000'} SOL</span>
        </div>

        {/* Uptime */}
        {running && (
          <div className="text-gray-500 text-xs">
            up {fmtUptime(workspaceState?.uptime_seconds ?? 0)}
          </div>
        )}
      </div>

      {/* Right: controls */}
      <div className="flex items-center gap-3">
        {error && <span className="text-red-400 text-xs">{error}</span>}
        {!running ? (
          <button
            onClick={handleStart}
            disabled={loading}
            className="px-4 py-1.5 bg-green-500 hover:bg-green-400 disabled:opacity-50
                       text-black font-bold text-sm rounded font-mono transition-colors"
          >
            {loading ? '…' : 'START'}
          </button>
        ) : (
          <button
            onClick={handleStop}
            disabled={loading}
            className="px-4 py-1.5 bg-red-600 hover:bg-red-500 disabled:opacity-50
                       text-white font-bold text-sm rounded font-mono transition-colors"
          >
            {loading ? '…' : 'STOP'}
          </button>
        )}
      </div>
    </header>
  )
}
