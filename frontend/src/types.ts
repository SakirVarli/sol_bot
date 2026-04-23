export interface LogEntry {
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'
  message: string
  ts: number
  module: string
}

export interface PipelineToken {
  mint: string
  source: string
  liquidity_usd: number
  swap_count: number
  watch_elapsed_seconds: number
  price_change_pct: number
  retrace_pct: number
  state: string
}

export interface OpenPosition {
  position_id: string
  mint: string
  entry_price: number
  current_price: number
  pnl_pct: number
  pnl_sol: number
  status: string
  hold_seconds: number
  tp1_triggered: boolean
  cost_sol: number
}

export interface Stats {
  trades: number
  win_rate: number
  net_pnl_sol: number
  winners: number
  losers: number
}

export interface BotState {
  running: boolean
  mode: 'paper' | 'live'
  uptime_seconds: number
  stop_reason: string | null
  balance_sol: number
  initial_balance_sol: number
  positions: OpenPosition[]
  pipeline: {
    filtering: PipelineToken[]
    watching: PipelineToken[]
  }
  stats: Stats
}

export interface ClosedTrade {
  position_id: string
  mint: string
  mode: string
  entry_ts: number
  close_ts: number
  cost_sol: number
  realized_pnl_sol: number
  pnl_pct: number
  exit_reason: string
  hold_seconds: number
}

export type WSMessage =
  | { type: 'log'; data: LogEntry }
  | { type: 'state'; data: BotState }
  | { type: 'history'; data: ClosedTrade[] }
