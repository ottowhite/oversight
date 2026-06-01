api/build:
	docker compose build oversight-backend

frontend/build:
	docker compose build oversight-frontend

build:
	docker compose build

compose/up: build
	docker compose up --remove-orphans -d

api/down:
	docker compose down

compose/down:
	docker compose down

compose/logs:
	docker compose logs -f

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

oversight/sync: oversight/sync/arxiv oversight/sync/pl

oversight/sync/arxiv:
	uv run python -m oversight.ArXivRepository --sync

oversight/sync/pl:
	uv run python -m oversight.PLConferenceHarvester --skip-existing-doi
	uv run oversight consume data/pl_conferences/ --format scraped

oversight/digest:
	uv run python -m oversight.ArXivRepository --digest

oversight/install-cron:
	sudo ./scripts/install_sync_cron.sh
