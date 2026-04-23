import { useState } from 'react'
import { Header } from './components/Header'
import { LogFeed } from './components/LogFeed'
import { PipelineView } from './components/PipelineView'
import { PositionList } from './components/PositionCard'
import { StatsPanel } from './components/StatsPanel'
import { TradeHistory } from './components/TradeHistory'
import { useWebSocket } from './hooks/useWebSocket'

type Tab = 'logs' | 'history'

export default function App() {
  const { connected, botState, logs, history } = useWebSocket()
  const [activeTab, setActiveTab] = useState<Tab>('logs')

  return (
    <div className="h-screen bg-gray-950 text-gray-100 font-mono flex flex-col overflow-hidden">
      {/* Top bar */}
      <Header connected={connected} botState={botState} />

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden" style={{ height: 'calc(100vh - 57px)' }}>
        {/* Left sidebar */}
        <aside className="w-72 shrink-0 flex flex-col gap-3 p-3 overflow-y-auto border-r border-gray-800">
          <StatsPanel botState={botState} />
          <PipelineView botState={botState} />
          <PositionList positions={botState?.positions ?? []} />
        </aside>

        {/* Right content */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Tab bar */}
          <div className="flex items-center gap-0 border-b border-gray-800 bg-gray-950 shrink-0">
            {(['logs', 'history'] as Tab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-5 py-2.5 text-xs uppercase tracking-widest transition-colors border-b-2 ${
                  activeTab === tab
                    ? 'text-green-400 border-green-400'
                    : 'text-gray-600 border-transparent hover:text-gray-400'
                }`}
              >
                {tab === 'logs' ? `Live Log (${logs.length})` : `History (${history.length})`}
              </button>
            ))}
          </div>

          {/* Tab content — min-h-0 lets flex-1 shrink below content size */}
          <div className="flex-1 min-h-0 p-3 flex flex-col">
            {activeTab === 'logs' && <LogFeed logs={logs} />}
            {activeTab === 'history' && (
              <div className="flex-1 min-h-0 overflow-y-auto">
                <TradeHistory trades={history} />
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
