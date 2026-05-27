GMGN := uv run gmgn-twitter-intel

.PHONY: help sync install uninstall tool-path test lint compile check init config db-migrate db-health serve status recent asset-flow account-alerts token-radar-cex-recover docker-up docker-status docker-logs docker-down docker-shell clean test-unit test-integration test-e2e test-golden test-architecture test-contract check-all coverage contract-check regen-contract install-hooks

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

check: ## gates 1+2: lint + format + typecheck + unit + arch + contract (no external deps; ~10s)
	@uv run ruff check .
	@uv run ruff format --check .
	@uv run mypy src
	@cd web && npm run typecheck && npm run lint && npm run format:check
	@uv run python -m pytest tests/unit tests/architecture tests/contract -m "unit or architecture or contract"; ec=$$?; [ $$ec -eq 5 ] && exit 0 || exit $$ec
	@uv run python -m compileall src tests

test-unit: ## run only tests/unit/
	@uv run python -m pytest tests/unit -m unit; ec=$$?; [ $$ec -eq 5 ] && exit 0 || exit $$ec

test-integration: ## run only tests/integration/ (real Postgres required; auto testcontainers in P5)
	@uv run python -m pytest tests/integration -m integration; ec=$$?; [ $$ec -eq 5 ] && exit 0 || exit $$ec

test-e2e: ## run only tests/e2e/ (testcontainers + uvicorn subprocess; populated in P5)
	@uv run python -m pytest tests/e2e -m e2e; ec=$$?; [ $$ec -eq 5 ] && exit 0 || exit $$ec

test-golden: ## run only tests/golden/ (real Postgres golden corpus)
	@uv run python -m pytest tests/golden -m e2e; ec=$$?; [ $$ec -eq 5 ] && exit 0 || exit $$ec

test-architecture: ## run only tests/architecture/ (AST/grep checks)
	@uv run python -m pytest tests/architecture -m architecture; ec=$$?; [ $$ec -eq 5 ] && exit 0 || exit $$ec

test-contract: ## run only tests/contract/ (OpenAPI drift; populated in P4)
	@uv run python -m pytest tests/contract -m contract; ec=$$?; [ $$ec -eq 5 ] && exit 0 || exit $$ec

check-all: ## the only command that may produce verification-artefact evidence (gates 1+2+3)
	@$(MAKE) check
	@$(MAKE) test-integration
	@$(MAKE) test-e2e
	@$(MAKE) test-golden
	@$(MAKE) coverage

coverage: ## run coverage report (gates fail_under from pyproject.toml [tool.coverage])
	@uv run python -m pytest --cov --cov-report=term-missing --cov-config=pyproject.toml -q

contract-check: ## verify OpenAPI types are in sync (gate 2)
	@uv run python -m pytest tests/contract -m contract

regen-contract: ## regenerate openapi.json + web/src/lib/types/openapi.ts
	@uv run python scripts/regen_openapi.py
	@cd web && npm run generate:types && cd ..

install-hooks: ## install pre-commit hooks
	@uv run pre-commit install

init: ## create ~/.gmgn-twitter-intel/config.yaml + workers.yaml
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

asset-flow: ## print 5m token activity
	@$(GMGN) asset-flow --window 5m --limit 20

account-alerts: ## print watched-account token alerts
	@$(GMGN) account-alerts --window 24h --limit 50

token-radar-cex-recover: ## recover Token Radar CEX recognition
	@$(GMGN) ops sync-binance-usdt-perp-universe --execute
	@$(GMGN) ops sync-binance-cex-profiles
	@$(GMGN) ops cex-binance-hard-cut-cleanup --dry-run --min-binance-feeds 400
	@$(GMGN) ops cex-binance-hard-cut-cleanup --execute --min-binance-feeds 400
	@$(GMGN) ops rebuild-token-intents --window 24h --limit 5000 --projection-limit 5000
	@$(GMGN) ops audit-token-radar --window 1h --scope all --limit 20

docker-up: init ## build and start container service
	@if [ -n "$${GITHUB_TOKEN:-}" ]; then \
		docker compose up -d --build app; \
	elif command -v gh >/dev/null 2>&1 && GITHUB_TOKEN=$$(gh auth token 2>/dev/null); then \
		GITHUB_TOKEN="$$GITHUB_TOKEN" docker compose up -d --build app; \
	else \
		docker compose up -d --build app; \
	fi

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

.PHONY: docs-generated docs-db-schema docs-cli-help docs-score-versions docs-ws-protocol docs-pulse-agent-desk-decisions

docs-generated: docs-db-schema docs-cli-help docs-score-versions docs-ws-protocol docs-pulse-agent-desk-decisions ## regenerate docs/generated/*

docs-db-schema: ## regenerate docs/generated/db-schema.md (requires Postgres)
	@uv run python scripts/regen_db_schema.py

docs-cli-help: ## regenerate docs/generated/cli-help.md
	@uv run python scripts/regen_cli_help.py

docs-score-versions: ## regenerate docs/generated/score-versions.md
	@uv run python scripts/regen_score_versions.py

docs-ws-protocol: ## regenerate docs/generated/ws-protocol.md
	@uv run python scripts/regen_ws_protocol.py

docs-pulse-agent-desk-decisions: ## regenerate docs/generated/pulse-agent-desk-decisions.md
	@uv run python scripts/regen_pulse_agent_desk_decisions.py
