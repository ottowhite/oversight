api/build:
	docker build -f Dockerfile.api -t oversight-backend .

frontend/build:
	docker build -f frontend/Dockerfile -t oversight-frontend ./frontend

build: api/build frontend/build

compose/up: build
	docker compose up

api/down:
	docker compose down

compose/down:
	docker compose down

dev:
	./dev.sh

dev/down:
	docker compose -f docker-compose.dev.yml down

db/up:
	docker compose -f docker-compose.db.yml up -d

db/down:
	docker compose -f docker-compose.db.yml down

db/enable:
	sudo systemctl enable --now docker
	docker compose -f docker-compose.db.yml up -d

db/logs:
	docker logs -f oversight-db

db/stats:
	@set -a; . ./.env; set +a; \
	PGPASSWORD="$$OVERSIGHT_DB_PASSWORD" psql -h localhost -U oversight -d oversight -c "SELECT datname, xact_commit, tup_returned, tup_fetched, blks_hit FROM pg_stat_database WHERE datname='oversight'"

lint:
	uv run ruff check src/

lint/fix:
	uv run ruff check --fix src/

format:
	uv run ruff format src/

format/check:
	uv run ruff format --check src/

typecheck:
	uv run ty check src/

oversight/sync:
	uv run python -m oversight.ArXivRepository --sync