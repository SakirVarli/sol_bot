import type { WorkspaceState } from '../types'

interface Props {
  workspaceState: WorkspaceState | null
}

function Stat({
  label,
  value,
  color = 'text-gray-100',
}: {
  label: string
  value: string
  color?: string
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-gray-500 text-xs uppercase tracking-wider">{label}</span>
      <span className={`font-mono font-bold text-sm ${color}`}>{value}</span>
    </div>
  )
}

export function StatsPanel({ workspaceState }: Props) {
  const stats = workspaceState?.stats ?? {
    trades: 0,
    win_rate: 0,
    net_pnl_sol: 0,
    winners: 0,
    losers: 0,
  }

  const pnlColor =
    stats.net_pnl_sol > 0
      ? 'text-green-400'
      : stats.net_pnl_sol < 0
        ? 'text-red-400'
        : 'text-gray-400'

  const pnlSign = stats.net_pnl_sol >= 0 ? '+' : ''

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-3">
      <div className="text-xs text-gray-500 uppercase tracking-widest mb-3 font-mono">
        Performance
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Stat label="Trades" value={String(stats.trades)} />
        <Stat
          label="Win Rate"
          value={`${(stats.win_rate * 100).toFixed(0)}%`}
          color={stats.win_rate > 0.5 ? 'text-green-400' : stats.win_rate > 0 ? 'text-yellow-400' : 'text-gray-400'}
        />
        <Stat
          label="Net PnL"
          value={`${pnlSign}${stats.net_pnl_sol.toFixed(4)} SOL`}
          color={pnlColor}
        />
        <Stat
          label="W / L"
          value={`${stats.winners} / ${stats.losers}`}
          color="text-gray-300"
        />
      </div>
    </div>
  )
}
