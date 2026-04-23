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

  startBot: (mode: 'paper' | 'live') =>
    apiFetch('/api/bot/start', {
      method: 'POST',
      body: JSON.stringify({ mode }),
    }),

  stopBot: () => apiFetch('/api/bot/stop', { method: 'POST' }),

  getStatus: () => apiFetch('/api/bot/status'),

  getHistory: (limit = 100) => apiFetch(`/api/trades/history?limit=${limit}`),

  getConfig: () => apiFetch('/api/bot/config'),
}

export function createWebSocket(): WebSocket {
  const wsBase = import.meta.env.VITE_WS_URL ?? ''
  const url = wsBase
    ? `${wsBase}/ws/stream`
    : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/stream`
  return new WebSocket(url)
}
