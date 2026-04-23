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
  strategy_id: string
  strategy_name: string
  ledger_type: string
  entry_price: number
  current_price: number
  pnl_pct: number
  pnl_sol: number
  status: string
  hold_seconds: number
  tp1_triggered: boolean
  cost_sol: number
  entry_reason: string
}

export interface Stats {
  trades: number
  win_rate: number
  net_pnl_sol: number
  winners: number
  losers: number
}

export interface StrategyStat {
  strategy_id: string
  strategy_name: string
  mode: 'paper' | 'live'
  trades: number
  winners: number
  losers: number
  win_rate: number
  realized_pnl_sol: number
  unrealized_pnl_sol: number
  open_positions: number
  used_budget_sol: number
  reserved_budget_sol: number
  free_budget_sol: number
}

export interface LedgerSnapshot {
  mode: 'paper' | 'live'
  initial_balance_sol: number
  balance_sol: number
  reserved_sol: number
  used_sol: number
  free_sol: number
}

export interface WorkspaceState {
  running: boolean
  uptime_seconds: number
  stop_reason: string | null
  portfolio: {
    ledgers: LedgerSnapshot[]
    strategies: Record<
      string,
      {
        mode: 'paper' | 'live'
        reserved_sol: number
        used_sol: number
        free_sol: number
        realized_pnl_sol: number
      }
    >
  }
  positions: OpenPosition[]
  pipeline: {
    filtering: PipelineToken[]
    watching: PipelineToken[]
  }
  stats: Stats
  strategies: StrategyStat[]
}

export interface ClosedTrade {
  position_id: string
  mint: string
  mode: string
  strategy_id: string
  strategy_name: string
  ledger_type: string
  entry_ts: number
  close_ts: number
  cost_sol: number
  realized_pnl_sol: number
  pnl_pct: number
  exit_reason: string
  exit_reason_detail: string
  hold_seconds: number
}

export interface RuleBlockPayload {
  type: string
  params: Record<string, string | number | boolean>
}

export interface RuleGroupPayload {
  logic: 'AND' | 'OR'
  blocks: Array<RuleBlockPayload | RuleGroupPayload>
}

export interface StrategyDefinition {
  definition_id: string
  name: string
  description: string
  version: number
  candle_seconds: number
  entry: RuleGroupPayload
  exits: RuleGroupPayload
  sizing: Record<string, unknown>
  risk: Record<string, unknown>
  reentry: Record<string, unknown>
}

export interface StrategyInstance {
  strategy_id: string
  definition_id: string
  name: string
  mode: 'paper' | 'live'
  status: 'enabled' | 'paused' | 'stopped'
  reserved_budget_sol: number
  allocation_pct?: number | null
  overrides: Record<string, unknown>
}

export interface StrategyCatalog {
  definitions: StrategyDefinition[]
  instances: StrategyInstance[]
  validation: Record<string, { errors: string[]; entry_summary: string; exit_summary: string }>
}

export type WSMessage =
  | { type: 'log'; data: LogEntry }
  | { type: 'state'; data: WorkspaceState }
  | { type: 'history'; data: ClosedTrade[] }
