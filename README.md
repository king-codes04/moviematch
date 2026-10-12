# MovieMatch

MovieMatch helps a group independently browse the same movie pool and discover
movies that at least two room members like. The app uses FastAPI, Redis, TMDB,
React, and Vite.

## Requirements

- Python 3.10 or newer
- Node.js 20.19+ or 22.12+
- Redis 6.2 or newer
- A TMDB API Read Access Token

## Local setup

1. Create a root `.env` file from `.env.example` and set
   `TMDB_BEARER_TOKEN` to your TMDB token. Keep the real token private.
2. Start Redis and set `REDIS_URL` to its connection URL.
3. Install the backend dependencies and start the API:

   ```sh
   python -m venv .venv
   . .venv/bin/activate
   pip install -r requirements-dev.txt
   uvicorn app.main:app --reload
   ```

4. Install and start the frontend in a second terminal:

   ```sh
   cd frontend
   npm ci
   npm run dev
   ```

The frontend is available at <http://localhost:5173>; Vite proxies API and
WebSocket requests to the backend at <http://localhost:8000>. For a frontend
served from a different origin, set `VITE_API_URL` to the backend origin when
building the frontend and set `CORS_ORIGINS` to a JSON array of allowed browser
origins (for example, `["https://movies.example.com"]`). A production reverse
proxy must support both `/rooms` HTTP requests and `/ws` WebSocket upgrades.

## Docker Compose

1. Create a root `.env` file from `.env.example` and set
   `TMDB_BEARER_TOKEN` to your TMDB token.
2. Build and start the frontend, API, and Redis:

   ```sh
   docker compose up --build
   ```

Open <http://localhost:8080>. The frontend container serves the production
Vite build and proxies `/api/` requests and `/ws/` WebSocket connections to
the API. Redis data is persisted in the `redis-data` named volume. Stop the
services with `docker compose down`; to also delete persisted Redis data, run
`docker compose down --volumes`.

## Validation

The backend tests use the configured Redis service and stub TMDB responses:

```sh
pytest
```

Run the frontend checks from `frontend/`:

```sh
npm test
npm run lint
npm run build
```

The API readiness endpoint is `GET /health`; it returns HTTP 503 when Redis is
unavailable. The root `.env` file is ignored by Git; use `.env.example` as the
template and never commit credentials.

## Current operational notes

- Redis stores room membership, the shared movie pool, decisions, and matches.
  This MVP does not expire room data automatically; plan Redis persistence and
  room cleanup before a public deployment.
- Room nicknames are not authenticated identities. Do not treat them as
  account-level identity or authorization for a public deployment.
- The WebSocket endpoint does not yet enforce an allowed-origin list or
  authenticate members. Restrict public access at the reverse proxy until
  identity and WebSocket-origin validation are added.
- The browser stores its room code and nickname locally to recover its state.
- Docker Compose runs the frontend, API, and Redis locally. For public
  deployment, add a trusted TLS-terminating reverse proxy and configure
  production secrets and WebSocket-origin validation.

See [frontend/README.md](frontend/README.md) for API, decision, and WebSocket
contracts.
