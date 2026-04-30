APP_HOME ?= $(HOME)/.gmgn-twitter-intel

GMGN := uv run gmgn-twitter-intel
COMPOSE_ENV := GMGN_TWITTER_HOME=$(APP_HOME)

.PHONY: help sync test lint compile check config serve status recent search-pepe embed docker-up docker-status docker-logs docker-down docker-shell clean

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

status: ## print health and readiness for the running API
	@curl -fsS http://127.0.0.1:8765/healthz
	@curl -fsS http://127.0.0.1:8765/readyz

recent: ## print recent matched events
	@$(GMGN) recent --limit 20

embed: ## process pending embeddings
	@$(GMGN) embed --limit 100

docker-up: ## build and start container service
	@$(COMPOSE_ENV) docker compose up -d --build app

docker-status: ## show container and readiness
	@$(COMPOSE_ENV) docker compose ps
	@curl -fsS http://127.0.0.1:8765/readyz || true

docker-logs: ## tail container logs
	@$(COMPOSE_ENV) docker compose logs -f --tail=100 app

docker-down: ## stop container service
	@$(COMPOSE_ENV) docker compose down

docker-shell: ## open shell in container
	@$(COMPOSE_ENV) docker compose exec app /bin/sh

clean: ## remove local test/cache artifacts
	@rm -rf .pytest_cache .ruff_cache __pycache__
	@find src tests -type d -name __pycache__ -prune -exec rm -rf {} +
