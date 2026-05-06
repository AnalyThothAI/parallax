GMGN := uv run gmgn-twitter-intel

.PHONY: help sync install uninstall tool-path test lint compile check init config db-migrate db-health serve status recent token-flow account-alerts docker-up docker-status docker-logs docker-down docker-shell clean

help: ## show available targets
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z0-9_-]+:.*##/ {printf "%-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## install dependencies
	@uv sync

install: ## install or update the global CLI with uv tool
	@uv tool install --force --reinstall .

uninstall: ## uninstall the global CLI installed by uv tool
	@uv tool uninstall gmgn-twitter-intel

tool-path: ## ensure uv tool executables are on PATH
	@uv tool update-shell

test: ## run tests
	@uv run python -m pytest

lint: ## run ruff
	@uv run python -m ruff check .

compile: ## compile Python files
	@uv run python -m compileall src tests

check: test lint compile ## run all local Python checks

init: ## create ~/.gmgn-twitter-intel/config.yaml
	@$(GMGN) init

config: ## print effective runtime config
	@$(GMGN) config

db-migrate: ## apply PostgreSQL migrations
	@$(GMGN) db migrate

db-health: ## check PostgreSQL liveness and migration version
	@$(GMGN) db health

serve: ## run collector and API in foreground
	@$(GMGN) serve

status: ## print health and readiness for the running API
	@curl -fsS http://127.0.0.1:8765/healthz
	@curl -fsS http://127.0.0.1:8765/readyz

recent: ## print recent matched events
	@$(GMGN) recent --limit 20

token-flow: ## print 5m token activity
	@$(GMGN) token-flow --window 5m --limit 20

account-alerts: ## print watched-account token alerts
	@$(GMGN) account-alerts --window 24h --limit 50

docker-up: init ## build and start container service
	@docker compose up -d --build app

docker-status: ## show container and readiness
	@docker compose ps
	@curl -fsS http://127.0.0.1:8765/readyz || true

docker-logs: ## tail container logs
	@docker compose logs -f --tail=100 app

docker-down: ## stop container service
	@docker compose down

docker-shell: ## open shell in container
	@docker compose exec app /bin/sh

clean: ## remove local test/cache artifacts
	@rm -rf .pytest_cache .ruff_cache __pycache__
	@find src tests -type d -name __pycache__ -prune -exec rm -rf {} +
