.PHONY: build up stop logs restart status clean run-local init-env dry-run test help up_and_logs clear-db

# Default variables
ENV_FILE ?= .env

# Commands
build:
	docker compose build

up:
	docker compose up -d --build

up_and_logs:
	docker compose up --build

stop:
	docker compose down

logs:
	docker compose logs -f

restart: stop up

status:
	docker compose ps

clean: stop
	docker compose rm -f

clear-db: check-env
	@echo "Clearing database..."
	docker compose run --rm --build app python -c "from pymongo import MongoClient; from src.config import settings; client = MongoClient(settings.db.uri); client.dca_bot.trades.drop(); print('Trades collection cleared successfully.')"

check-env:
	@if [ ! -f $(ENV_FILE) ]; then \
		echo "$(ENV_FILE) file does not exist. Please create it based on .env.example"; \
		exit 1; \
	fi

run-local: check-env
	python -m src.main

init-env:
	cp .env.example .env
	@echo "Created .env file from .env.example. Please edit it with your credentials."

dry-run:
	DRY_RUN=true python -m src.main

# Test command
test: check-env
	@echo "Running production tests..."
	docker compose run --rm --build app python -m pytest -xvs --log-cli-level=INFO tests/test_prod.py

help:
	@echo "Available commands:"
	@echo "  make build      - Build Docker image"
	@echo "  make up         - Start container in detached mode"
	@echo "  make up_and_logs - Start container and show logs"
	@echo "  make stop       - Stop container"
	@echo "  make logs       - View container logs"
	@echo "  make restart    - Restart container"
	@echo "  make status     - Check container status"
	@echo "  make clean      - Stop and remove container"
	@echo "  make clear-db   - Clear the database by dropping trades collection"
	@echo "  make run-local  - Run application locally"
	@echo "  make init-env   - Create .env file from .env.example"
	@echo "  make dry-run    - Run application in dry run mode (no actual trades)"
	@echo "  make test       - Run production tests in Docker container"
	@echo "  make help       - Show this help message"
