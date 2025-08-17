api/build:
	docker build -f Dockerfile.api -t oversight-backend .

api/up:
	docker compose up -d

api/down:
	docker compose down