DATA_DIR ?= $(HOME)/.local/state/gmgn-twitter-cli
WINDOW ?= 1h

GMGN := uv run gmgn-twitter-cli
COMPOSE_ENV := GMGN_TWITTER_DATA_DIR=$(DATA_DIR)

.PHONY: help sync test lint compile check config serve status logs service-install service-restart service-stop service-status recent search-pepe embed docker-up docker-status docker-logs docker-down docker-shell clean

help: ## show available targets
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z0-9_-]+:.*##/ {printf "%-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## install dependencies
	@uv sync

test: ## run tests
	@uv run pytest

lint: ## run ruff
	@uv run ruff check .

compile: ## compile Python files
	@uv run python -m compileall src tests

check: test lint compile ## run all local checks

config: ## print effective runtime config
	@$(GMGN) config

serve: ## run collector and API in foreground
	@$(GMGN) serve

status: ## print health and readiness
	@curl -fsS http://127.0.0.1:8765/healthz
	@curl -fsS http://127.0.0.1:8765/readyz

logs: ## tail macOS service logs
	@$(GMGN) service logs --lines 120

service-install: ## install and start macOS LaunchAgent
	@$(GMGN) service install --start

service-restart: ## restart macOS LaunchAgent
	@$(GMGN) service restart

service-stop: ## stop macOS LaunchAgent
	@$(GMGN) service stop

service-status: ## print macOS LaunchAgent status
	@$(GMGN) service status

recent: ## print recent matched events
	@$(GMGN) recent --limit 20

search-pepe: ## search all stored PEPE events without shell cashtag escaping
	@$(GMGN) search --symbol PEPE --limit 20

embed: ## process pending embeddings
	@$(GMGN) embed --limit 100

docker-up: ## build and start container service
	@$(COMPOSE_ENV) docker compose up -d --build gmgn-twitter-cli

docker-status: ## show container and readiness
	@$(COMPOSE_ENV) docker compose ps
	@curl -fsS http://127.0.0.1:8765/readyz || true

docker-logs: ## tail container logs
	@$(COMPOSE_ENV) docker compose logs -f --tail=100 gmgn-twitter-cli

docker-down: ## stop container service
	@$(COMPOSE_ENV) docker compose down

docker-shell: ## open shell in container
	@$(COMPOSE_ENV) docker compose exec gmgn-twitter-cli /bin/sh

clean: ## remove local test/cache artifacts
	@rm -rf .pytest_cache .ruff_cache __pycache__
