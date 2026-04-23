import type { OpenPosition } from '../types'

function truncateMint(mint: string) {
  return `${mint.slice(0, 6)}…${mint.slice(-4)}`
}

function fmtHold(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

interface Props {
  position: OpenPosition
}

export function PositionCard({ position: p }: Props) {
  const isProfit = p.pnl_sol >= 0
  const pnlColor = isProfit ? 'text-green-400' : 'text-red-400'
  const pnlBg = isProfit ? 'bg-green-400/10 border-green-400/30' : 'bg-red-400/10 border-red-400/30'
  const pnlSign = p.pnl_sol >= 0 ? '+' : ''

  return (
    <div className={`border rounded-lg p-3 font-mono text-xs ${pnlBg}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
          <span className="text-gray-200 font-bold">{truncateMint(p.mint)}</span>
          {p.tp1_triggered && (
            <span className="text-[10px] text-cyan-400 border border-cyan-400/50 rounded px-1">
              TP1 ✓
            </span>
          )}
        </div>
        <span className={`font-bold text-sm ${pnlColor}`}>
          {pnlSign}{p.pnl_pct.toFixed(1)}%
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2 text-gray-400">
        <div>
          <div className="text-gray-600 text-[10px]">ENTRY</div>
          <div className="text-gray-300">{p.entry_price.toExponential(3)}</div>
        </div>
        <div>
          <div className="text-gray-600 text-[10px]">CURRENT</div>
          <div className="text-gray-300">{p.current_price.toExponential(3)}</div>
        </div>
        <div>
          <div className="text-gray-600 text-[10px]">PNL</div>
          <div className={pnlColor}>{pnlSign}{p.pnl_sol.toFixed(4)} SOL</div>
        </div>
      </div>

      <div className="mt-2 flex items-center justify-between text-gray-600 text-[10px]">
        <span>hold: {fmtHold(p.hold_seconds)}</span>
        <span>{p.status}</span>
      </div>
    </div>
  )
}

interface ListProps {
  positions: OpenPosition[]
}

export function PositionList({ positions }: ListProps) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-3">
      <div className="text-xs text-gray-500 uppercase tracking-widest mb-3 font-mono">
        Open Positions
      </div>
      {positions.length === 0 ? (
        <div className="text-gray-600 text-xs font-mono text-center py-2">
          no open positions
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {positions.map((p) => (
            <PositionCard key={p.position_id} position={p} />
          ))}
        </div>
      )}
    </div>
  )
}
