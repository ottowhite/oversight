# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is this?

Oversight is an academic paper search engine with vector similarity search. It indexes papers from ArXiv and CS conferences (ICML, NeurIPS, ICLR, OSDI, SOSP, ASPLOS, ATC, NSDI, MLSys, EuroSys, VLDB) into PostgreSQL with pgvector, and provides a chat-style search UI.

## Development Commands

```bash
# Start dev environment (Docker with hot-reload, auto-finds free ports)
make dev            # or ./dev.sh

# Stop dev environment
make dev/down

# Production build & run
make build          # builds both containers
make compose/up     # runs production docker-compose

# Backend linting/formatting (Python - uses uv + ruff)
make format         # auto-format
make format/check   # check formatting (runs in pre-commit hook)
make lint           # ruff linter
make lint/fix       # auto-fix lint issues
make typecheck      # ty type checker (runs in pre-commit hook)

# Frontend (from frontend/ directory)
npm run dev         # next.js dev server on port 3000
npm run build       # production build
npm run lint        # eslint

# Data sync
make oversight/sync # sync papers from ArXiv
```

## Architecture

**Two-service app: Python backend + Next.js frontend, connected via Docker networking.**

### Backend (`src/`)
- **Flask REST API** (`flask_app.py`) — routes: `/api/search`, `/api/health`, `/api/inventory`, `/api/sync`, `/api/digest`
- **Layered data access**: `flask_app.py` → `PaperRepository.py` (business logic + embeddings) → `PaperDatabase.py` (PostgreSQL/pgvector queries)
- **Embeddings**: Google Generative AI (Gemini) via `EmbeddingModel.py`
- **LLM**: OpenRouter API (Gemini-2.5-Flash) via `ResearchLLM.py` with LangChain/LangGraph
- **Data ingestion**: `ArXivRepository.py` (ArXiv sync), `OpenReviewHarvester.py` (conference scraping)

### Frontend (`frontend/`)
- **Next.js 12 + React 17 + TypeScript** — essentially a single-page app
- **Styling**: Tailwind CSS + DaisyUI with a custom Vercel-inspired dark theme (black bg, white text, blue accents)
- **Main UI**: `pages/index.tsx` — contains the entire search interface (search input, filters sidebar, results display)
- **API proxy**: `next.config.js` rewrites `/api/*` to backend URL from `NEXT_PUBLIC_BACKEND_URL`

### Infrastructure
- **Docker Compose** for both dev (`docker-compose.dev.yml` with volume mounts) and prod (`docker-compose.yml`)
- **`dev.sh`** dynamically finds free ports to avoid conflicts across git worktrees
- **Nix** (`shell.nix`) provides uv, nodejs, npm

## Commit Style

Use atomic commits — each commit should contain a single logical change. Prefix commit messages with a tag: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`, `style:`.

## Pre-commit Hooks

The `.githooks/pre-commit` hook runs `ruff format --check src/` and `ty check src/`. Format code before committing.

## Key Environment Variables

See `.env.example`. Required: `GOOGLE_API_KEY` (embeddings), `OPENROUTER_API_KEY` (LLM), `DATABASE_URL` / `POSTGRES_*` (database), `NEXT_PUBLIC_BACKEND_URL` (frontend→backend proxy).
