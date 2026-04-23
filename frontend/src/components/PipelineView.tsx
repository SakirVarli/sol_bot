import type { PipelineToken, WorkspaceState } from '../types'

function truncateMint(mint: string) {
  return `${mint.slice(0, 6)}…${mint.slice(-4)}`
}

function TokenRow({ token }: { token: PipelineToken }) {
  const changeColor =
    token.price_change_pct > 0 ? 'text-green-400' : token.price_change_pct < 0 ? 'text-red-400' : 'text-gray-400'

  return (
    <div className="flex items-center justify-between py-1.5 border-b border-gray-800 last:border-0 text-xs font-mono">
      <div className="flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
        <span className="text-gray-300">{truncateMint(token.mint)}</span>
        <span className="text-gray-600 text-[10px]">{token.source}</span>
      </div>
      <div className="flex items-center gap-3 text-right">
        <span className="text-gray-500">${token.liquidity_usd.toLocaleString()}</span>
        <span className={changeColor}>
          {token.price_change_pct >= 0 ? '+' : ''}
          {token.price_change_pct.toFixed(1)}%
        </span>
        <span className="text-gray-600">{Math.floor(token.watch_elapsed_seconds)}s</span>
      </div>
    </div>
  )
}

interface Props {
  workspaceState: WorkspaceState | null
}

export function PipelineView({ workspaceState }: Props) {
  const pipeline = workspaceState?.pipeline ?? { filtering: [], watching: [] }
  const watching = pipeline.watching ?? []
  const filtering = pipeline.filtering ?? []
  const total = watching.length + filtering.length

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-3">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-gray-500 uppercase tracking-widest font-mono">
          Pipeline
        </span>
        <div className="flex gap-3 text-xs font-mono">
          {filtering.length > 0 && (
            <span className="text-yellow-400">{filtering.length} filtering</span>
          )}
          <span className={watching.length > 0 ? 'text-cyan-400' : 'text-gray-600'}>
            {watching.length} watching
          </span>
        </div>
      </div>

      {total === 0 ? (
        <div className="text-gray-600 text-xs font-mono text-center py-2">
          no candidates
        </div>
      ) : (
        <div>
          {watching.map((t) => (
            <TokenRow key={t.mint} token={t} />
          ))}
        </div>
      )}
    </div>
  )
}
