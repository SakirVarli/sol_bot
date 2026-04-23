import { useState } from 'react'
import { api } from '../api/client'
import type { BotState } from '../types'

interface Props {
  connected: boolean
  botState: BotState | null
}

function fmtUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

export function Header({ connected, botState }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const running = botState?.running ?? false
  const mode = botState?.mode ?? 'paper'
  const balance = botState?.balance_sol ?? 0

  async function handleStart() {
    setLoading(true)
    setError(null)
    try {
      await api.startBot('paper')
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
      await api.stopBot()
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
        <span
          className={`px-2 py-0.5 rounded text-xs font-bold border ${
            mode === 'live'
              ? 'border-red-500 text-red-400'
              : 'border-purple-600 text-purple-400'
          }`}
        >
          {mode.toUpperCase()}
        </span>

        {/* Balance */}
        <div className="text-gray-300">
          <span className="text-gray-500 text-xs mr-1">BAL</span>
          <span className={balance > (botState?.initial_balance_sol ?? 10) ? 'text-green-400' : 'text-gray-300'}>
            {balance.toFixed(4)} SOL
          </span>
        </div>

        {/* Uptime */}
        {running && (
          <div className="text-gray-500 text-xs">
            up {fmtUptime(botState?.uptime_seconds ?? 0)}
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
