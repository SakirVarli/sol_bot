import { useEffect, useMemo, useState } from 'react'
import { api } from './api/client'
import { Header } from './components/Header'
import { LogFeed } from './components/LogFeed'
import { PipelineView } from './components/PipelineView'
import { PositionList } from './components/PositionCard'
import { StatsPanel } from './components/StatsPanel'
import { TradeHistory } from './components/TradeHistory'
import { useWebSocket } from './hooks/useWebSocket'
import type { RuleBlockPayload, RuleGroupPayload, StrategyCatalog, StrategyDefinition, StrategyInstance } from './types'

type Tab = 'overview' | 'logs' | 'history' | 'designer'

type DefinitionDraft = {
  name: string
  description: string
  version: number
  candle_seconds: number
  entry: RuleGroupPayload
  exits: RuleGroupPayload
  sizing: Record<string, string | number | boolean>
  risk: Record<string, string | number | boolean>
  reentry: Record<string, string | number | boolean>
}

const defaultDefinitionDraft: DefinitionDraft = {
  name: 'First Green After 5 Red',
  description: 'Buy the first green candle after five consecutive red candles, then exit on target, stop, or weakness.',
  version: 1,
  candle_seconds: 60,
  entry: {
    logic: 'AND',
    blocks: [{ type: 'first_candle_after_sequence', params: { count: 5, after_color: 'red', then_color: 'green' } }],
  } satisfies RuleGroupPayload,
  exits: {
    logic: 'OR',
    blocks: [
      { type: 'profit_pct_gte', params: { value: 5 } },
      { type: 'loss_pct_lte', params: { value: 3 } },
      { type: 'consecutive_candles', params: { count: 5, color: 'red' } },
    ],
  } satisfies RuleGroupPayload,
  sizing: { kind: 'fixed_sol', value: 0.1, max_size_sol: 0.1 },
  risk: { max_concurrent_positions: 1 },
  reentry: { allow_repeat_entries: true, cooldown_seconds: 0 },
}

function StrategyCard({
  instance,
  definitionName,
  validation,
  onToggle,
  onDelete,
}: {
  instance: StrategyInstance
  definitionName?: string
  validation?: { errors: string[]; entry_summary: string; exit_summary: string }
  onToggle: (instance: StrategyInstance) => Promise<void>
  onDelete: (instance: StrategyInstance) => Promise<void>
}) {
  const isEnabled = instance.status === 'enabled'
  return (
    <div className="rounded-2xl border border-stone-800 bg-stone-950/80 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold tracking-wide text-stone-100">{instance.name}</div>
          <div className="mt-1 text-[11px] uppercase tracking-[0.28em] text-stone-500">{instance.mode} / {instance.status}</div>
        </div>
        <div className="flex gap-2">
          <button onClick={() => void onToggle(instance)} className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] ${isEnabled ? 'bg-red-500/20 text-red-300' : 'bg-emerald-500/20 text-emerald-300'}`}>{isEnabled ? 'Stop' : 'Start'}</button>
          <button onClick={() => void onDelete(instance)} className="rounded-full border border-red-500/30 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-red-300">Delete</button>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-stone-300">
        <div className="rounded-xl border border-stone-800 bg-stone-900/80 p-3">
          <div className="text-[10px] uppercase tracking-[0.2em] text-stone-500">Reserved</div>
          <div className="mt-1 text-sm font-semibold text-stone-100">{instance.reserved_budget_sol.toFixed(4)} SOL</div>
        </div>
        <div className="rounded-xl border border-stone-800 bg-stone-900/80 p-3">
          <div className="text-[10px] uppercase tracking-[0.2em] text-stone-500">Definition</div>
          <div className="mt-1 text-sm font-semibold text-stone-100">{definitionName ?? instance.definition_id.slice(0, 12)}</div>
        </div>
      </div>
      {validation && (
        <div className="mt-4 space-y-2 text-xs text-stone-400">
          <div><span className="text-stone-500">Entry:</span> {validation.entry_summary}</div>
          <div><span className="text-stone-500">Exit:</span> {validation.exit_summary}</div>
          {validation.errors.length > 0 && <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-2 text-red-300">{validation.errors.join(' ')}</div>}
        </div>
      )}
    </div>
  )
}

function DefinitionCard({
  definition,
  linkedInstances,
  validation,
  onDelete,
}: {
  definition: StrategyDefinition
  linkedInstances: number
  validation?: { errors: string[]; entry_summary: string; exit_summary: string }
  onDelete: (definition: StrategyDefinition) => Promise<void>
}) {
  return (
    <div className="rounded-2xl border border-stone-800 bg-stone-950/80 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold tracking-wide text-stone-100">{definition.name}</div>
          <div className="mt-1 text-[11px] uppercase tracking-[0.28em] text-stone-500">v{definition.version} / {definition.candle_seconds}s candles</div>
        </div>
        <button onClick={() => void onDelete(definition)} className="rounded-full border border-red-500/30 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-red-300">Delete</button>
      </div>
      <p className="mt-3 text-sm leading-6 text-stone-400">{definition.description || 'No description yet.'}</p>
      <div className="mt-4 rounded-xl border border-stone-800 bg-stone-900/80 p-3 text-xs text-stone-300">
        <div className="text-[10px] uppercase tracking-[0.2em] text-stone-500">Linked Instances</div>
        <div className="mt-1 text-sm font-semibold text-stone-100">{linkedInstances}</div>
      </div>
      {validation && (
        <div className="mt-4 space-y-2 text-xs text-stone-400">
          <div><span className="text-stone-500">Entry:</span> {validation.entry_summary}</div>
          <div><span className="text-stone-500">Exit:</span> {validation.exit_summary}</div>
          {validation.errors.length > 0 && <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-2 text-red-300">{validation.errors.join(' ')}</div>}
        </div>
      )}
    </div>
  )
}

function DesignerPanel({ catalog, onRefresh }: { catalog: StrategyCatalog | null; onRefresh: () => Promise<void> }) {
  const [definitionDraft, setDefinitionDraft] = useState<DefinitionDraft>(defaultDefinitionDraft)
  const [instanceName, setInstanceName] = useState('Momentum Paper Runner')
  const [instanceMode, setInstanceMode] = useState<'paper' | 'live'>('paper')
  const [reservedBudget, setReservedBudget] = useState('2')
  const [validationResult, setValidationResult] = useState<{ errors: string[]; entry_summary: string; exit_summary: string } | null>(null)
  const [previewRows, setPreviewRows] = useState<Array<{ mint: string; entry_match: boolean; reason: string; candles: number }>>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const payload = useMemo(() => ({
    ...definitionDraft,
    candle_seconds: Number(definitionDraft.candle_seconds),
    sizing: {
      ...definitionDraft.sizing,
      value: Number((definitionDraft.sizing.value as number) ?? 0.1),
      max_size_sol: Number((definitionDraft.sizing.max_size_sol as number) ?? 0.1),
    },
    reentry: {
      ...definitionDraft.reentry,
      cooldown_seconds: Number((definitionDraft.reentry.cooldown_seconds as number) ?? 0),
    },
  }), [definitionDraft])

  async function validate() {
    try {
      setError(null)
      setSuccess(null)
      setValidationResult(await api.validateDefinition(payload) as { errors: string[]; entry_summary: string; exit_summary: string })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function preview() {
    try {
      setError(null)
      setSuccess(null)
      const result = await api.previewDefinition(payload) as {
        validation: { errors: string[]; entry_summary: string; exit_summary: string }
        preview: Array<{ mint: string; entry_match: boolean; reason: string; candles: number }>
      }
      setValidationResult(result.validation)
      setPreviewRows(result.preview)
      if (result.preview.length === 0) {
        setSuccess('Preview ran successfully. Start the workspace to test against live watched tokens.')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function saveAll() {
    setSaving(true)
    try {
      setError(null)
      setSuccess(null)
      const saved = await api.saveDefinition(payload) as { definition: StrategyDefinition; validation: { errors: string[]; entry_summary: string; exit_summary: string } }
      setValidationResult(saved.validation)
      await api.saveInstance({ definition_id: saved.definition.definition_id, name: instanceName, mode: instanceMode, status: 'stopped', reserved_budget_sol: Number(reservedBudget) })
      await onRefresh()
      setSuccess('Strategy definition and runnable instance saved successfully.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  function updateEntryBlock(block: RuleBlockPayload, index: number) {
    setDefinitionDraft((prev) => {
      const nextBlocks = [...prev.entry.blocks] as RuleBlockPayload[]
      nextBlocks[index] = block
      return { ...prev, entry: { ...prev.entry, blocks: nextBlocks } } as DefinitionDraft
    })
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
      <section className="rounded-3xl border border-stone-800 bg-stone-950/90 p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-stone-100">Strategy Designer</h2>
            <p className="mt-1 text-sm text-stone-400">Build candle-driven entries and exits with sequence logic, counters, and risk controls.</p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => void validate()} className="rounded-full border border-stone-700 px-4 py-2 text-xs uppercase tracking-[0.2em] text-stone-200">Validate</button>
            <button onClick={() => void preview()} className="rounded-full border border-amber-500/40 px-4 py-2 text-xs uppercase tracking-[0.2em] text-amber-200">Preview</button>
            <button onClick={() => void saveAll()} disabled={saving} className="rounded-full bg-emerald-500 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-black disabled:opacity-60">{saving ? 'Saving' : 'Save'}</button>
          </div>
        </div>
        {(error || success) && (
          <div className={`mt-4 rounded-2xl border p-3 text-sm ${error ? 'border-red-500/30 bg-red-500/10 text-red-300' : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'}`}>
            {error ?? success}
          </div>
        )}
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="mb-2 block text-xs uppercase tracking-[0.2em] text-stone-500">Definition Name</span>
            <input value={definitionDraft.name} onChange={(e) => setDefinitionDraft((prev) => ({ ...prev, name: e.target.value }))} className="w-full rounded-2xl border border-stone-800 bg-stone-900 px-4 py-3 text-sm text-stone-100" />
          </label>
          <label className="block">
            <span className="mb-2 block text-xs uppercase tracking-[0.2em] text-stone-500">Candle Seconds</span>
            <input type="number" value={definitionDraft.candle_seconds} onChange={(e) => setDefinitionDraft((prev) => ({ ...prev, candle_seconds: Number(e.target.value) }))} className="w-full rounded-2xl border border-stone-800 bg-stone-900 px-4 py-3 text-sm text-stone-100" />
          </label>
        </div>
        <label className="mt-4 block">
          <span className="mb-2 block text-xs uppercase tracking-[0.2em] text-stone-500">Description</span>
          <textarea value={definitionDraft.description} onChange={(e) => setDefinitionDraft((prev) => ({ ...prev, description: e.target.value }))} className="min-h-24 w-full rounded-2xl border border-stone-800 bg-stone-900 px-4 py-3 text-sm text-stone-100" />
        </label>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-stone-800 bg-stone-900/70 p-4">
            <div className="mb-3 text-xs uppercase tracking-[0.2em] text-stone-500">Entry Sequence</div>
            <p className="mb-4 text-xs leading-5 text-stone-400">
              Define what must happen before a buy is triggered. Use these blocks for patterns like
              "first red candle", "5 consecutive red candles", or "first green candle after 5 red candles".
            </p>
            {definitionDraft.entry.blocks.map((block, index) => {
              const rule = block as unknown as RuleBlockPayload
              return (
                <div key={index} className="space-y-3">
                  <select value={rule.type} onChange={(e) => updateEntryBlock({ ...rule, type: e.target.value }, index)} className="w-full rounded-xl border border-stone-800 bg-stone-950 px-3 py-2 text-sm text-stone-100">
                    <option value="first_candle_after_sequence">First color after sequence</option>
                    <option value="first_candle_color">First candle color</option>
                    <option value="consecutive_candles">Consecutive candles</option>
                  </select>
                  <div className="grid grid-cols-3 gap-2">
                    <input type="number" value={String((rule.params.count as number) ?? 1)} onChange={(e) => updateEntryBlock({ ...rule, params: { ...rule.params, count: Number(e.target.value) } }, index)} className="rounded-xl border border-stone-800 bg-stone-950 px-3 py-2 text-sm text-stone-100" placeholder="count" />
                    <input value={String((rule.params.after_color as string) ?? 'red')} onChange={(e) => updateEntryBlock({ ...rule, params: { ...rule.params, after_color: e.target.value } }, index)} className="rounded-xl border border-stone-800 bg-stone-950 px-3 py-2 text-sm text-stone-100" placeholder="after color" />
                    <input value={String((rule.params.then_color as string) ?? 'green')} onChange={(e) => updateEntryBlock({ ...rule, params: { ...rule.params, then_color: e.target.value } }, index)} className="rounded-xl border border-stone-800 bg-stone-950 px-3 py-2 text-sm text-stone-100" placeholder="then color" />
                  </div>
                </div>
              )
            })}
          </div>
          <div className="rounded-2xl border border-stone-800 bg-stone-900/70 p-4">
            <div className="mb-3 text-xs uppercase tracking-[0.2em] text-stone-500">Exit Controls</div>
            <p className="mb-4 text-xs leading-5 text-stone-400">
              Define how positions close. Combine profit targets, stop losses, and candle-pattern exits with OR logic,
              for example "take profit at 5%" or "exit after 5 consecutive red candles".
            </p>
            <div className="grid gap-3">
              {definitionDraft.exits.blocks.map((block, index) => {
                const rule = block as unknown as RuleBlockPayload
                return (
                  <div key={index} className="rounded-xl border border-stone-800 bg-stone-950 p-3">
                    <div className="text-xs uppercase tracking-[0.2em] text-stone-500">{rule.type}</div>
                    <input type="number" value={String((rule.params.value as number) ?? (rule.params.count as number) ?? 0)} onChange={(e) => setDefinitionDraft((prev) => {
                      const nextBlocks = [...(prev.exits.blocks as RuleBlockPayload[])]
                      nextBlocks[index] = {
                        ...rule,
                        params: rule.type === 'consecutive_candles' ? { ...rule.params, count: Number(e.target.value) } : { ...rule.params, value: Number(e.target.value) },
                      }
                      return { ...prev, exits: { ...prev.exits, blocks: nextBlocks } }
                    })} className="mt-2 w-full rounded-xl border border-stone-800 bg-stone-900 px-3 py-2 text-sm text-stone-100" />
                  </div>
                )
              })}
            </div>
          </div>
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <label className="block">
            <span className="mb-2 block text-xs uppercase tracking-[0.2em] text-stone-500">Instance Name</span>
            <input value={instanceName} onChange={(e) => setInstanceName(e.target.value)} className="w-full rounded-2xl border border-stone-800 bg-stone-900 px-4 py-3 text-sm text-stone-100" />
          </label>
          <label className="block">
            <span className="mb-2 block text-xs uppercase tracking-[0.2em] text-stone-500">Mode</span>
            <select value={instanceMode} onChange={(e) => setInstanceMode(e.target.value as 'paper' | 'live')} className="w-full rounded-2xl border border-stone-800 bg-stone-900 px-4 py-3 text-sm text-stone-100"><option value="paper">Paper</option><option value="live">Live</option></select>
          </label>
          <label className="block">
            <span className="mb-2 block text-xs uppercase tracking-[0.2em] text-stone-500">Reserved Budget</span>
            <input value={reservedBudget} onChange={(e) => setReservedBudget(e.target.value)} className="w-full rounded-2xl border border-stone-800 bg-stone-900 px-4 py-3 text-sm text-stone-100" />
          </label>
        </div>
      </section>
      <section className="space-y-4">
        <div className="rounded-3xl border border-stone-800 bg-stone-950/90 p-5">
          <div className="text-xs uppercase tracking-[0.28em] text-stone-500">Human Readable</div>
          <div className="mt-3 space-y-3 text-sm text-stone-300">
            <div><span className="text-stone-500">Entry</span><div className="mt-1 text-stone-100">{validationResult?.entry_summary ?? 'Validate to generate summary.'}</div></div>
            <div><span className="text-stone-500">Exit</span><div className="mt-1 text-stone-100">{validationResult?.exit_summary ?? 'Validate to generate summary.'}</div></div>
            {validationResult?.errors.length ? <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-3 text-red-300">{validationResult.errors.join(' ')}</div> : <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-emerald-200">Rule graph is valid for compilation.</div>}
          </div>
        </div>
        <div className="rounded-3xl border border-stone-800 bg-stone-950/90 p-5">
          <div className="flex items-center justify-between"><div className="text-xs uppercase tracking-[0.28em] text-stone-500">Preview</div><div className="text-xs text-stone-500">{catalog?.instances.length ?? 0} saved strategies</div></div>
          <div className="mt-3 space-y-2">
            {previewRows.length === 0 ? <div className="rounded-2xl border border-stone-800 bg-stone-900/70 p-4 text-sm text-stone-500">Preview against live watched tokens after the workspace is running.</div> : previewRows.map((row) => (
              <div key={row.mint} className="rounded-2xl border border-stone-800 bg-stone-900/70 p-3 text-sm">
                <div className="flex items-center justify-between text-stone-100"><span>{row.mint.slice(0, 6)}...{row.mint.slice(-4)}</span><span className={row.entry_match ? 'text-emerald-300' : 'text-stone-500'}>{row.entry_match ? 'MATCH' : 'NO MATCH'}</span></div>
                <div className="mt-1 text-xs text-stone-400">{row.reason || `${row.candles} candles evaluated`}</div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}

export default function AppWorkspace() {
  const { connected, workspaceState, logs, history, catalog, setCatalog } = useWebSocket()
  const [activeTab, setActiveTab] = useState<Tab>('overview')
  const [overviewError, setOverviewError] = useState<string | null>(null)
  const [overviewSuccess, setOverviewSuccess] = useState<string | null>(null)

  async function refreshCatalog() {
    try {
      const result = await api.getStrategies()
      setCatalog(result as StrategyCatalog)
      setOverviewError(null)
    } catch (error) {
      setOverviewError(error instanceof Error ? error.message : String(error))
    }
  }

  useEffect(() => {
    void refreshCatalog()
  }, [workspaceState?.running])

  async function toggleStrategy(instance: StrategyInstance) {
    try {
      setOverviewError(null)
      setOverviewSuccess(null)
      if (instance.status === 'enabled') {
        await api.stopStrategy(instance.strategy_id)
        setOverviewSuccess(`Stopped ${instance.name}.`)
      } else {
        await api.startStrategy(instance.strategy_id)
        setOverviewSuccess(`Started ${instance.name}.`)
      }
      await refreshCatalog()
    } catch (error) {
      setOverviewError(error instanceof Error ? error.message : String(error))
    }
  }

  const strategyValidation = catalog?.validation ?? {}
  const definitionLookup = useMemo(
    () => Object.fromEntries((catalog?.definitions ?? []).map((definition) => [definition.definition_id, definition])),
    [catalog?.definitions],
  )
  const instanceCountByDefinition = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const instance of catalog?.instances ?? []) {
      counts[instance.definition_id] = (counts[instance.definition_id] ?? 0) + 1
    }
    return counts
  }, [catalog?.instances])

  async function deleteInstance(instance: StrategyInstance) {
    const confirmed = window.confirm(`Delete strategy instance "${instance.name}"? This removes the runnable strategy from the workspace.`)
    if (!confirmed) {
      return
    }
    try {
      setOverviewError(null)
      setOverviewSuccess(null)
      await api.deleteInstance(instance.strategy_id)
      await refreshCatalog()
      setOverviewSuccess(`Deleted instance ${instance.name}.`)
    } catch (error) {
      setOverviewError(error instanceof Error ? error.message : String(error))
    }
  }

  async function deleteDefinition(definition: StrategyDefinition) {
    const confirmed = window.confirm(`Delete strategy definition "${definition.name}"? Any linked instances must be removed first.`)
    if (!confirmed) {
      return
    }
    try {
      setOverviewError(null)
      setOverviewSuccess(null)
      await api.deleteDefinition(definition.definition_id)
      await refreshCatalog()
      setOverviewSuccess(`Deleted definition ${definition.name}.`)
    } catch (error) {
      setOverviewError(error instanceof Error ? error.message : String(error))
    }
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(245,158,11,0.14),_transparent_32%),linear-gradient(180deg,_#19140f_0%,_#0d0c0b_48%,_#080808_100%)] text-stone-100">
      <Header connected={connected} workspaceState={workspaceState} />
      <div className="grid gap-4 p-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="space-y-4 self-start xl:sticky xl:top-4">
          <StatsPanel workspaceState={workspaceState} />
          <PipelineView workspaceState={workspaceState} />
          <PositionList positions={workspaceState?.positions ?? []} />
          <div className="rounded-3xl border border-stone-800 bg-stone-950/90 p-4">
            <div className="text-xs uppercase tracking-[0.28em] text-stone-500">Ledgers</div>
            <div className="mt-3 space-y-3">
              {(workspaceState?.portfolio.ledgers ?? []).map((ledger) => (
                <div key={ledger.mode} className="rounded-2xl border border-stone-800 bg-stone-900/70 p-3 text-sm">
                  <div className="flex items-center justify-between text-stone-100"><span className="uppercase tracking-[0.2em] text-[11px]">{ledger.mode}</span><span>{ledger.balance_sol.toFixed(4)} SOL</span></div>
                  <div className="mt-2 grid grid-cols-3 gap-2 text-[11px] text-stone-400"><span>Reserved {ledger.reserved_sol.toFixed(3)}</span><span>Used {ledger.used_sol.toFixed(3)}</span><span>Free {ledger.free_sol.toFixed(3)}</span></div>
                </div>
              ))}
            </div>
          </div>
        </aside>
        <main className="min-w-0 overflow-x-hidden">
          <div className="mb-4 flex flex-wrap gap-2">
            {(['overview', 'logs', 'history', 'designer'] as Tab[]).map((tab) => (
              <button key={tab} onClick={() => setActiveTab(tab)} className={`rounded-full px-4 py-2 text-xs uppercase tracking-[0.22em] transition ${activeTab === tab ? 'bg-amber-400 text-black' : 'border border-stone-700 bg-stone-950/80 text-stone-300'}`}>{tab}</button>
            ))}
          </div>
          {activeTab === 'overview' && (
            <section className="rounded-3xl border border-stone-800 bg-stone-950/90 p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-stone-100">Strategy Workspace</h2>
                  <p className="mt-1 text-sm text-stone-400">Run paper and live strategies side by side with reserved budget slices and separate rule graphs.</p>
                </div>
                <button onClick={() => void refreshCatalog()} className="rounded-full border border-stone-700 px-4 py-2 text-xs uppercase tracking-[0.2em] text-stone-200">Refresh</button>
              </div>
              {(overviewError || overviewSuccess) && (
                <div className={`mt-4 rounded-2xl border p-3 text-sm ${overviewError ? 'border-red-500/30 bg-red-500/10 text-red-300' : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'}`}>
                  {overviewError ?? overviewSuccess}
                </div>
              )}
              <div className="mt-3 text-xs text-stone-500">
                Refresh reloads saved strategy definitions and instances from storage, even if the workspace is stopped.
              </div>
              <div className="mt-5">
                <div className="mb-3 text-xs uppercase tracking-[0.24em] text-stone-500">Runnable Instances</div>
                <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
                  {(catalog?.instances ?? []).map((instance) => (
                    <StrategyCard
                      key={instance.strategy_id}
                      instance={instance}
                      definitionName={definitionLookup[instance.definition_id]?.name}
                      validation={strategyValidation[instance.definition_id]}
                      onToggle={toggleStrategy}
                      onDelete={deleteInstance}
                    />
                  ))}
                  {!catalog?.instances.length && <div className="rounded-2xl border border-dashed border-stone-700 bg-stone-950/70 p-6 text-sm text-stone-500">Save a strategy in the designer to create a runnable instance here.</div>}
                </div>
              </div>
              <div className="mt-8">
                <div className="mb-3 text-xs uppercase tracking-[0.24em] text-stone-500">Saved Definitions</div>
                <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
                  {(catalog?.definitions ?? []).map((definition) => (
                    <DefinitionCard
                      key={definition.definition_id}
                      definition={definition}
                      linkedInstances={instanceCountByDefinition[definition.definition_id] ?? 0}
                      validation={strategyValidation[definition.definition_id]}
                      onDelete={deleteDefinition}
                    />
                  ))}
                  {!catalog?.definitions.length && <div className="rounded-2xl border border-dashed border-stone-700 bg-stone-950/70 p-6 text-sm text-stone-500">Saved strategy definitions will appear here after your first designer save.</div>}
                </div>
              </div>
            </section>
          )}
          {activeTab === 'logs' && <LogFeed logs={logs} />}
          {activeTab === 'history' && <TradeHistory trades={history} />}
          {activeTab === 'designer' && <DesignerPanel catalog={catalog} onRefresh={refreshCatalog} />}
        </main>
      </div>
    </div>
  )
}
