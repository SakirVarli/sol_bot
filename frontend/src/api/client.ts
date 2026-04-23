const BASE = import.meta.env.VITE_API_URL ?? ''

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  health: () => apiFetch<{ status: string }>('/api/health'),

  startWorkspace: () => apiFetch('/api/workspace/start', { method: 'POST' }),

  stopWorkspace: () => apiFetch('/api/workspace/stop', { method: 'POST' }),

  getStatus: () => apiFetch('/api/workspace/status'),

  getHistory: (limit = 100) => apiFetch(`/api/workspace/trades/history?limit=${limit}`),

  getConfig: () => apiFetch('/api/workspace/config'),

  getStrategies: () => apiFetch('/api/strategies'),

  saveDefinition: (payload: unknown) =>
    apiFetch('/api/strategies/definitions', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  saveInstance: (payload: unknown) =>
    apiFetch('/api/strategies/instances', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  deleteInstance: (strategyId: string) =>
    apiFetch(`/api/strategies/instances/${strategyId}`, { method: 'DELETE' }),

  deleteDefinition: (definitionId: string) =>
    apiFetch(`/api/strategies/definitions/${definitionId}`, { method: 'DELETE' }),

  validateDefinition: (payload: unknown) =>
    apiFetch('/api/strategies/validate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  previewDefinition: (payload: unknown) =>
    apiFetch('/api/strategies/preview', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  startStrategy: (strategyId: string) =>
    apiFetch(`/api/strategies/${strategyId}/start`, { method: 'POST' }),

  stopStrategy: (strategyId: string) =>
    apiFetch(`/api/strategies/${strategyId}/stop`, { method: 'POST' }),
}

export function createWebSocket(): WebSocket {
  const wsBase = import.meta.env.VITE_WS_URL ?? ''
  const url = wsBase
    ? `${wsBase}/ws/workspace`
    : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/workspace`
  return new WebSocket(url)
}
