import type { ClosedTrade } from '../types'

function truncateMint(mint: string) {
  return `${mint.slice(0, 6)}…${mint.slice(-4)}`
}

function fmtHold(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

function fmtTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString()
}

const EXIT_COLOR: Record<string, string> = {
  TP1: 'text-cyan-400',
  TP2: 'text-green-400',
  TRAILING_STOP: 'text-yellow-400',
  HARD_STOP: 'text-red-400',
  TIME_STOP: 'text-orange-400',
  LIQUIDITY_COLLAPSE: 'text-red-500',
  EMERGENCY: 'text-red-500',
}

interface Props {
  trades: ClosedTrade[]
}

export function TradeHistory({ trades }: Props) {
  if (trades.length === 0) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <div className="text-xs text-gray-500 uppercase tracking-widest font-mono mb-3">
          Trade History
        </div>
        <div className="text-gray-700 text-xs font-mono text-center py-4">
          no closed trades yet
        </div>
      </div>
    )
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
      <div className="text-xs text-gray-500 uppercase tracking-widest font-mono px-3 py-3 border-b border-gray-800">
        Trade History ({trades.length})
      </div>
      <div className="overflow-x-auto">
        <table className="w-full font-mono text-xs">
          <thead>
            <tr className="text-gray-600 border-b border-gray-800">
              <th className="text-left px-3 py-2">Mint</th>
              <th className="text-left px-3 py-2">Entry</th>
              <th className="text-left px-3 py-2">Close</th>
              <th className="text-right px-3 py-2">PnL SOL</th>
              <th className="text-right px-3 py-2">PnL %</th>
              <th className="text-left px-3 py-2">Exit</th>
              <th className="text-right px-3 py-2">Hold</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => {
              const isWin = t.realized_pnl_sol > 0
              const pnlColor = isWin ? 'text-green-400' : 'text-red-400'
              const pnlSign = t.realized_pnl_sol >= 0 ? '+' : ''
              const exitColor = EXIT_COLOR[t.exit_reason] ?? 'text-gray-400'

              return (
                <tr
                  key={t.position_id}
                  className="border-b border-gray-800/50 hover:bg-gray-800/30"
                >
                  <td className="px-3 py-1.5 text-gray-300">{truncateMint(t.mint)}</td>
                  <td className="px-3 py-1.5 text-gray-500">
                    {t.entry_ts ? fmtTime(t.entry_ts) : '—'}
                  </td>
                  <td className="px-3 py-1.5 text-gray-500">
                    {t.close_ts ? fmtTime(t.close_ts) : '—'}
                  </td>
                  <td className={`px-3 py-1.5 text-right ${pnlColor}`}>
                    {pnlSign}{t.realized_pnl_sol.toFixed(4)}
                  </td>
                  <td className={`px-3 py-1.5 text-right ${pnlColor}`}>
                    {pnlSign}{t.pnl_pct.toFixed(1)}%
                  </td>
                  <td className={`px-3 py-1.5 ${exitColor}`}>
                    {t.exit_reason?.replace('_', ' ') ?? '—'}
                  </td>
                  <td className="px-3 py-1.5 text-right text-gray-500">
                    {fmtHold(t.hold_seconds)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
