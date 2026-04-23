# SOL Trading

A Dockerized Solana meme-token paper trading bot with a FastAPI backend and a React dashboard.

## What This Project Does

The backend listens for early Solana token launch activity, filters candidates, evaluates a trading strategy, and records paper trades. The frontend shows bot status, live logs, pipeline activity, open positions, and trade history.

## Main Parts

- `backend/`: FastAPI app, bot runner, strategy/filter logic, storage, and API/WebSocket routes
- `frontend/`: React + Vite dashboard
- `data/`: runtime logs and local paper-trading database files
- `docker-compose.yml`: production-style local stack
- `docker-compose.dev.yml`: hot-reload development override

## Current Strategy

The default configuration uses paper mode and a `first_pullback` strategy. The bot watches for new pools, applies liquidity and risk filters, and enters simulated positions when the configured setup appears.

## Requirements

- Docker Desktop with Docker Compose

Optional for non-Docker development:

- Python 3.12
- Node.js 20+

## Run With Docker

Start the app:

```powershell
docker compose up --build
```

Run in the background:

```powershell
docker compose up --build -d
```

Open:

- Frontend: `http://localhost`
- Backend health: `http://localhost:8000/api/health`

Stop the stack:

```powershell
docker compose down
```

## Development Mode

Use the dev override for hot reload:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

That exposes:

- Frontend dev server: `http://localhost:3000`
- Backend API: `http://localhost:8000`

## Environment Notes

The project reads configuration from YAML files in `backend/config/` and supports `.env` overrides for:

- `SOLANA_RPC_HTTP`
- `SOLANA_RPC_WS`
- `BOT_MODE`

The `.env` file is intentionally ignored and should not be committed.

## Useful Commands

```powershell
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
```

## Repository Notes

- Runtime trade databases and logs under `data/` are not meant to be committed.
- The bot currently starts in an idle state until you press `START` in the dashboard.
- This repository is suitable for paper trading and local experimentation before any live-trading work.
