# SOL Trading

A Dockerized Solana trading workspace with a FastAPI backend and a React dashboard for running multiple strategy instances side by side.

## What This Project Does

The app listens for Solana launch and swap activity, builds shared candle/market state, and lets you run many strategies at the same time from one workspace.

Current workspace capabilities:

- shared discovery and market-data pipeline
- multiple concurrent strategy instances
- `paper` and `live` modes shown in one dashboard
- per-strategy reserved budget slices from the main ledger
- separate positions and stats per strategy
- candle-based strategy designer with entry/exit rule summaries
- validation and preview flows for strategy definitions
- strategy instance and definition deletion with safety checks

## Architecture

### Backend

The backend now uses a workspace-oriented runtime instead of a single bot loop.

Main pieces:

- `backend/core/engine/supervisor.py`: shared runtime supervisor
- `backend/core/engine/rule_engine.py`: compiles and evaluates strategy rule graphs
- `backend/core/engine/candle_service.py`: builds candles from shared ticks
- `backend/core/engine/portfolio_allocator.py`: enforces reserved per-strategy budgets
- `backend/core/engine/strategy_store.py`: persists definitions and instances
- `backend/core/portfolio/multi_position_manager.py`: strategy-owned positions and exits
- `backend/api/routes/workspace*.py`: workspace status, trade history, websocket streams
- `backend/api/routes/strategies.py`: strategy CRUD, validation, preview, start/stop, delete

### Frontend

The frontend is now a workspace dashboard rather than a single bot control page.

Main pieces:

- `frontend/src/AppWorkspace.tsx`: main workspace UI
- `frontend/src/api/client.ts`: workspace/strategy API client
- `frontend/src/hooks/useWebSocket.ts`: live workspace and history updates
- `frontend/src/components/*`: dashboard panels for stats, pipeline, header, logs, and history

## Strategy Model

The strategy designer is aimed at candle-driven workflows such as:

- buy after the first red candle
- buy on the first green candle after 5 red candles
- exit at `+5%` profit
- exit at `-3%` loss
- exit after `5 consecutive red candles`

Each saved strategy has:

- a reusable `StrategyDefinition`
- one or more runnable `StrategyInstance`s
- a mode: `paper` or `live`
- a reserved budget amount
- separate runtime stats and positions

Important behavior:

- multiple strategies can run at the same time
- strategies can share one workspace while keeping positions separate
- a definition cannot be deleted while instances still depend on it
- an instance cannot be deleted while it still has open positions

## API Overview

Useful endpoints:

- `GET /api/health`
- `POST /api/workspace/start`
- `POST /api/workspace/stop`
- `GET /api/workspace/status`
- `GET /api/workspace/trades/history`
- `GET /api/strategies`
- `POST /api/strategies/definitions`
- `POST /api/strategies/instances`
- `POST /api/strategies/validate`
- `POST /api/strategies/preview`
- `POST /api/strategies/{strategy_id}/start`
- `POST /api/strategies/{strategy_id}/stop`
- `DELETE /api/strategies/instances/{strategy_id}`
- `DELETE /api/strategies/definitions/{definition_id}`

WebSocket:

- `ws://localhost/ws/workspace`

## Run With Docker

Requirements:

- Docker Desktop with Docker Compose

Start the stack:

```powershell
docker compose up --build
```

Run in the background:

```powershell
docker compose up --build -d
```

Open:

- Frontend: [http://localhost](http://localhost)
- Backend health: [http://localhost:8000/api/health](http://localhost:8000/api/health)
- Workspace status: [http://localhost:8000/api/workspace/status](http://localhost:8000/api/workspace/status)

Useful commands:

```powershell
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose down
```

Notes:

- runtime data is persisted under `./data`
- the workspace starts idle until you start it from the dashboard
- the current `live` mode is wired through the shared workspace model, but execution is still simulator-backed until a real live adapter is added

## Development

Optional local development requirements:

- Python 3.12
- Node.js 20+

Hot-reload mode:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

That exposes:

- Frontend dev server: `http://localhost:3000`
- Backend API: `http://localhost:8000`

## Configuration

The app reads configuration from YAML files in `backend/config/` and supports `.env` overrides for values such as:

- `SOLANA_RPC_HTTP`
- `SOLANA_RPC_WS`
- `BOT_MODE`

The `.env` file is ignored and should not be committed.

## Repository Notes

- `data/` contains local logs and database files and should stay uncommitted
- this repository is currently best suited for paper trading, strategy design, and local experimentation
- if you are extending live execution, treat the current `live` mode as a runtime shell that still needs a real broker/wallet adapter
