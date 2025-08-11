.PHONY: build run run-compose stop clean test help

help:
	@echo "Available commands:"
	@echo "  build        - Build the Docker image"
	@echo "  run          - Build and run the container with port mapping"
	@echo "  run-compose  - Run with Docker Compose"
	@echo "  stop         - Stop running containers"
	@echo "  clean        - Remove containers and images"
	@echo "  test         - Run tests"
	@echo "  help         - Show this help message"

build:
	docker build -t stocks-api .

run: build
	docker run -p 8000:8000 stocks-api

run-compose:
	docker compose up --build

stop:
	docker stop $$(docker ps -q --filter ancestor=stocks-api) 2>/dev/null || true
	docker compose down 2>/dev/null || true

clean: stop
	docker rmi stocks-api 2>/dev/null || true
	docker system prune -f

test:
	python -m pytest
