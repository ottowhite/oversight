api/build:
	docker build -f Dockerfile.api -t oversight-backend .

frontend/build:
	docker build -f frontend/Dockerfile -t oversight-frontend ./frontend

build: api/build frontend/build

compose/up: build
	docker compose up --remove-orphans

api/down:
	docker compose down

compose/down:
	docker compose down