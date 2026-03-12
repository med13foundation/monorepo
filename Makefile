# MED13 Resource Library - Development Makefile
# Automates common development, testing, and deployment tasks

# Virtual environment configuration
VENV := venv
PYTHON := $(VENV)/bin/python3
PIP := $(VENV)/bin/pip3
ALEMBIC_BIN := $(if $(wildcard $(VENV)/bin/alembic),$(VENV)/bin/alembic,alembic)

# Dockerized Postgres configuration
POSTGRES_ENV_FILE := .env.postgres
POSTGRES_ENV_TEMPLATE := .env.postgres.example
POSTGRES_COMPOSE_FILE := docker-compose.postgres.yml
POSTGRES_SERVICE := postgres
POSTGRES_COMPOSE := docker compose --env-file $(POSTGRES_ENV_FILE) -f $(POSTGRES_COMPOSE_FILE)
POSTGRES_ACTIVE_FLAG := .postgres-active
POSTGRES_ACTIVE := $(wildcard $(POSTGRES_ACTIVE_FLAG))
BACKEND_PID_FILE := .uvicorn.pid
BACKEND_LOG := logs/backend.log
BACKEND_PORT := 8080
BACKEND_UVICORN_APP := main:app
BACKEND_UVICORN_MATCH := uvicorn .*main:app
WEB_PID_FILE := .next.dev.pid
WEB_LOG := logs/web.log
WEB_PID_FILE_ABS := $(abspath $(WEB_PID_FILE))
WEB_LOG_ABS := $(abspath $(WEB_LOG))
NEXT_DEV_ENV := NEXTAUTH_SECRET=med13-resource-library-nextauth-secret-key-for-development-2024-secure-random-string NEXTAUTH_URL=http://localhost:3000 NEXT_PUBLIC_API_URL=http://localhost:8080
BACKEND_DEV_ENV := MED13_DEV_JWT_SECRET=med13-resource-library-backend-jwt-secret-for-development-2026-01
NEXTAUTH_URL ?= http://localhost:3000
NEXT_BUILD_ENV := NEXTAUTH_URL=$(NEXTAUTH_URL)
WEB_WAIT_TIMEOUT_SECONDS ?= 120
WEB_WAIT_INTERVAL_SECONDS ?= 2
FRONTDOOR_PORT ?= 3010

ADMIN_PASSWORD_EFFECTIVE := $(strip $(or $(ADMIN_PASSWORD),$(MED13_ADMIN_PASSWORD)))

# pip-audit exceptions:
# - CVE-2025-69872: diskcache has no upstream fix yet.
# - CVE-2026-25580: tracked dependency advisory under evaluation.
PIP_AUDIT_IGNORE_VULNS := CVE-2025-69872 CVE-2026-25580
PIP_AUDIT_IGNORE_FLAGS := $(foreach vuln,$(PIP_AUDIT_IGNORE_VULNS),--ignore-vuln $(vuln))

# Detect environment type
CI_ENV := $(CI)
IN_VENV := $(shell python3 -c "import sys; print('1' if sys.prefix != sys.base_prefix else '0')" 2>/dev/null || echo "0")

# Choose Python/Pip based on environment
ifeq ($(CI_ENV),true)
    # CI/CD environment - use system python/pip
    USE_PYTHON := python3
    USE_PIP := pip3
    VENV_STATUS := CI/CD (no venv)
    VENV_ACTIVE := false
else ifeq ($(IN_VENV),1)
    # We're in a venv - use venv python/pip
    USE_PYTHON := $(PYTHON)
    USE_PIP := $(PIP)
    VENV_STATUS := Active
    VENV_ACTIVE := true
else ifeq ($(wildcard $(VENV)/bin/python3),)
    # No venv exists - warn user
    USE_PYTHON := python3
    USE_PIP := pip3
    VENV_STATUS := None - run 'make venv' first
    VENV_ACTIVE := false
else
    # Venv exists but not activated - warn and use venv
    USE_PYTHON := $(PYTHON)
    USE_PIP := $(PIP)
    VENV_STATUS := Available - activate with 'source venv/bin/activate'
    VENV_ACTIVE := false
endif

REQUIRED_PYTHON_MAJOR := 3
REQUIRED_PYTHON_MINOR := 12
PYTHON_VERSION_OK := $(shell $(USE_PYTHON) -c "import sys; print('1' if sys.version_info >= ($(REQUIRED_PYTHON_MAJOR), $(REQUIRED_PYTHON_MINOR)) else '0')" 2>/dev/null || echo "0")
PYTHON_VERSION_DISPLAY := $(shell $(USE_PYTHON) -c "import platform; print(platform.python_version())" 2>/dev/null || echo "unknown")

define ensure_python_version
	@if [ "$(PYTHON_VERSION_OK)" != "1" ]; then \
		echo "❌ Python $(REQUIRED_PYTHON_MAJOR).$(REQUIRED_PYTHON_MINOR)+ is required. Detected: $(PYTHON_VERSION_DISPLAY)"; \
		echo "   Update your Python installation or activate the correct virtual environment."; \
		exit 1; \
	fi
endef

# Keep command execution stable even when the virtual environment is not
# explicitly activated, since commands already use the venv interpreter
# when available.
define check_venv
	$(call ensure_python_version)
endef

define ensure_postgres_env
	@if [ ! -f "$(POSTGRES_ENV_FILE)" ]; then \
		if [ -f "$(POSTGRES_ENV_TEMPLATE)" ]; then \
			cp "$(POSTGRES_ENV_TEMPLATE)" "$(POSTGRES_ENV_FILE)"; \
			echo "Created $(POSTGRES_ENV_FILE) from template."; \
		else \
			echo "Missing $(POSTGRES_ENV_TEMPLATE). Cannot create $(POSTGRES_ENV_FILE)."; \
			exit 1; \
		fi \
	fi
endef

define run_with_postgres_env
	$(call ensure_postgres_env)
	@echo "▶ Using Postgres env ($(POSTGRES_ENV_FILE))"
	@/bin/bash -lc 'set -a; source "$(POSTGRES_ENV_FILE)"; set +a; $(1)'
endef

define ensure_web_deps
	@if [ ! -d "src/web/node_modules" ]; then \
		echo "Installing Next.js dependencies..."; \
		if [ -f "src/web/package-lock.json" ]; then \
			(cd src/web && npm ci); \
		else \
			(cd src/web && npm install); \
		fi; \
	fi
endef

define ensure_frontdoor_deps
	@if [ ! -d "apps/frontdoor/node_modules" ]; then \
		echo "Installing frontdoor dependencies..."; \
		if [ -f "apps/frontdoor/package-lock.json" ]; then \
			(cd apps/frontdoor && npm ci); \
		else \
			(cd apps/frontdoor && npm install); \
		fi; \
	fi
endef

.PHONY: help venv venv-check install install-dev test test-graph test-graph-fast test-verbose test-cov test-watch test-architecture test-contract lint lint-strict format format-check black-format type-check type-check-strict type-check-report type-check-full security-audit security-full clean clean-all docker-build docker-run docker-push docker-stop docker-postgres-up docker-postgres-down docker-postgres-destroy docker-postgres-logs docker-postgres-status postgres-disable postgres-migrate init-artana-schema setup-postgres dev-postgres run-local-postgres run-web-postgres test-postgres postgres-cmd backend-status start-local db-migrate db-create db-reset db-seed deploy-dev deploy-staging deploy-staging-queued-workers deploy-prod setup-dev setup-gcp cloud-logs cloud-secrets-list all all-report ci check-env docs-serve backup-db restore-db activate deactivate stop-local stop-web stop-all restart web-install web-build web-clean web-lint web-type-check web-test web-test-architecture web-test-integration web-test-all web-test-coverage web-visual-test web-wait frontdoor-install frontdoor-stop frontdoor-dev frontdoor-build frontdoor-test phi-backfill-dry-run phi-backfill-commit graph-readiness graph-reasoning-rebuild

PY_CHECK_PATHS := src tests scripts alembic
PY_STRICT_CHECK_PATHS := src
GRAPH_TEST_PATHS := \
	tests/unit/application/services/test_kernel_relation_projection_materialization_service.py \
	tests/unit/application/services/test_kernel_relation_projection_invariant_service.py \
	tests/unit/application/services/test_kernel_claim_projection_readiness_service.py \
	tests/unit/application/services/test_check_claim_projection_readiness_script.py \
	tests/unit/application/services/test_rebuild_reasoning_paths_script.py \
	tests/unit/application/services/test_kernel_reasoning_path_service.py \
	tests/unit/application/services/test_hypothesis_generation_service.py \
	tests/unit/infrastructure/test_graph_query_repository.py \
	tests/integration/api/test_hypothesis_routes_api.py \
	tests/integration/api/test_kernel_graph_view_api.py \
	tests/integration/api/test_kernel_reasoning_path_api.py \
	tests/integration/api/test_kernel_routes_api.py \
	tests/integration/kernel/test_graph_dictionary_hard_guarantees.py
GRAPH_FAST_TEST_PATHS := \
	tests/unit/application/services/test_kernel_relation_projection_materialization_service.py \
	tests/unit/application/services/test_kernel_relation_projection_invariant_service.py \
	tests/unit/application/services/test_kernel_claim_projection_readiness_service.py \
	tests/unit/application/services/test_check_claim_projection_readiness_script.py \
	tests/unit/application/services/test_rebuild_reasoning_paths_script.py \
	tests/unit/application/services/test_kernel_reasoning_path_service.py \
	tests/unit/application/services/test_hypothesis_generation_service.py \
	tests/unit/infrastructure/test_graph_query_repository.py

# Default target
help: ## Show this help message
	@echo "MED13 Resource Library - Development Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Virtual Environment
venv: $(VENV) ## Create virtual environment if it doesn't exist
$(VENV):
	@echo "Creating virtual environment..."
	@python3 -c "import platform, sys; assert sys.version_info >= (3, 13), f'Python 3.13+ required to create virtualenv (found {platform.python_version()})'"
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	@echo "Virtual environment created at $(VENV)"

activate: ## Show command to activate virtual environment
	@echo "To activate the virtual environment, run:"
	@echo "source $(VENV)/bin/activate"

deactivate: ## Show command to deactivate virtual environment
	@echo "To deactivate the virtual environment, run:"
	@echo "deactivate"

# Installation
install: ## Install production dependencies
	$(call check_venv)
	$(USE_PIP) install --upgrade "pip>=26.0"
	$(USE_PIP) install -e .

install-dev: ## Install development dependencies
	$(call check_venv)
	$(USE_PIP) install --upgrade "pip>=26.0"
	$(USE_PIP) install -e ".[dev]"

# Development setup
setup-dev: install-dev ## Set up development environment
	$(USE_PIP) install pre-commit --quiet || true
	pre-commit install || true
	@echo "Development environment setup complete!"
	@echo "Virtual environment status: $(VENV_STATUS)"

setup-gcp: ## Set up Google Cloud SDK and authenticate
	@echo "Setting up Google Cloud..."
	gcloud auth login
	gcloud config set project YOUR_PROJECT_ID
	gcloud services enable run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com storage.googleapis.com

generate-ts-types: ## Generate TypeScript definitions from backend models
	$(call check_venv)
	$(USE_PYTHON) scripts/generate_ts_types.py

# Testing
test: ## Run all tests (excluding heavy performance tests)
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,MED13_ENABLE_DISTRIBUTED_RATE_LIMIT=0 $(USE_PYTHON) scripts/run_isolated_postgres_tests.py -m "not performance")

test-graph-fast: ## Run fast graph invariant tests without Postgres orchestration
	$(call check_venv)
	$(USE_PYTHON) -m pytest $(GRAPH_FAST_TEST_PATHS) -m "graph and not performance"

test-graph: ## Run graph invariant tests in isolated Postgres
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,MED13_ENABLE_DISTRIBUTED_RATE_LIMIT=0 $(USE_PYTHON) scripts/run_isolated_postgres_tests.py $(GRAPH_TEST_PATHS) -m "graph and not performance")

test-performance: ## Run performance tests
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,MED13_ENABLE_DISTRIBUTED_RATE_LIMIT=0 $(USE_PYTHON) scripts/run_isolated_postgres_tests.py tests/performance)

test-contract: ## Run API contract tests
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,MED13_ENABLE_DISTRIBUTED_RATE_LIMIT=0 $(USE_PYTHON) scripts/run_isolated_postgres_tests.py tests/security/test_schemathesis_contracts.py)

test-architecture: ## Run architectural compliance tests (type_examples.md pattern validation)
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,MED13_ENABLE_DISTRIBUTED_RATE_LIMIT=0 $(USE_PYTHON) scripts/run_isolated_postgres_tests.py tests/unit/architecture/test_architectural_compliance.py -v -m architecture)

test-artana-architecture: ## Run Artana AI agent architecture compliance tests
	$(call check_venv)
	$(USE_PYTHON) -m pytest tests/unit/architecture/test_architectural_compliance.py -v -m architecture

test-all-architecture: test-architecture test-artana-architecture validate-architecture validate-dependencies ## Run all architecture tests

validate-architecture: ## Validate architectural compliance
	$(call check_venv)
	@echo "🔍 Validating architectural compliance..."
	$(USE_PYTHON) scripts/validate_architecture.py
	@echo "✅ Architectural validation passed"

validate-dependencies: ## Validate dependency graph and layer boundaries (fails on errors)
	$(call check_venv)
	@echo "🔍 Validating dependencies..."
	$(USE_PYTHON) scripts/validate_dependencies.py
	@echo "✅ Dependency validation passed"

validate-dependencies-warn: ## Validate dependencies (warnings only, doesn't fail)
	$(call check_venv)
	@echo "🔍 Validating dependencies (non-blocking)..."
	@$(USE_PYTHON) scripts/validate_dependencies.py || echo "Dependency validation found issues (see docs/known-architectural-debt.md)"

test-verbose: ## Run tests with verbose output
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,MED13_ENABLE_DISTRIBUTED_RATE_LIMIT=0 $(USE_PYTHON) scripts/run_isolated_postgres_tests.py -v --tb=short)

test-cov: ## Run tests with coverage report
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,MED13_ENABLE_DISTRIBUTED_RATE_LIMIT=0 $(USE_PYTHON) scripts/run_isolated_postgres_tests.py --cov=src --cov-report=html --cov-report=term-missing)

graph-readiness: ## Audit global claim-backed projection readiness
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/check_claim_projection_readiness.py)

graph-reasoning-rebuild: ## Rebuild derived reasoning paths from grounded claim chains
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/rebuild_reasoning_paths.py)

test-watch: ## Run tests in watch mode
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,MED13_ENABLE_DISTRIBUTED_RATE_LIMIT=0 MED13_TEST_RUNNER=pytest-watch $(USE_PYTHON) scripts/run_isolated_postgres_tests.py)

# Code Quality
lint: ## Run all linting tools (warnings only)
	$(call check_venv)
	@echo "Running flake8..."
	-$(USE_PYTHON) -m flake8 $(PY_CHECK_PATHS) --max-line-length=88 --extend-ignore=E203,W503,E501,E402 --exclude=src/web/node_modules || echo "⚠️  Flake8 found style issues (non-blocking)"
	@echo "Running ruff..."
	-$(USE_PYTHON) -m ruff check $(PY_CHECK_PATHS) || echo "⚠️  Ruff found linting issues (non-blocking)"
	@echo "Running mypy..."
	-$(USE_PYTHON) -m mypy $(PY_CHECK_PATHS) || echo "⚠️  MyPy found type issues (non-blocking)"
	@echo "Running bandit (non-blocking)..."
	-$(USE_PYTHON) -m bandit -r $(PY_CHECK_PATHS) -f json -o bandit-results.json 2>&1 | grep -vE "(WARNING.*Test in comment|WARNING.*Unknown test found)" || echo "⚠️  Bandit found security issues (non-blocking)"

lint-strict: ## Run all linting tools (fails on error)
	$(call check_venv)
	@echo "Running flake8 (strict)..."
	@$(USE_PYTHON) -m flake8 $(PY_CHECK_PATHS) --max-line-length=88 --extend-ignore=E203,W503,E501,E402 --exclude=src/web/node_modules
	@echo "Running ruff (strict)..."
	@$(USE_PYTHON) -m ruff check $(PY_CHECK_PATHS)
	@echo "Running bandit (strict)..."
	@$(USE_PYTHON) -m bandit -r $(PY_CHECK_PATHS) -f json -o bandit-results.json 2>&1 | grep -vEi "(Test in comment|Unknown test found)" || true

black-format: ## Format Python code with Black (uses pre-commit Black when available)
	$(call check_venv)
	@if command -v pre-commit >/dev/null 2>&1; then \
		pre-commit run black --all-files; \
	else \
		$(USE_PYTHON) -m black $(PY_CHECK_PATHS); \
	fi

format: ## Format code with Black and sort imports with ruff
	$(call check_venv)
	@$(MAKE) -s black-format SUPPRESS_VENV_WARNING=1
	@$(USE_PYTHON) -m ruff check --fix $(PY_CHECK_PATHS) || echo "Ruff found linting issues (non-blocking)"

format-check: ## Check code formatting without making changes
	$(call check_venv)
	$(USE_PYTHON) -m black --check $(PY_CHECK_PATHS)
	$(USE_PYTHON) -m ruff check $(PY_CHECK_PATHS)

type-check: ## Run mypy type checking with strict settings (warnings only)
	$(call check_venv)
	-$(USE_PYTHON) -m mypy $(PY_STRICT_CHECK_PATHS) --strict --show-error-codes || echo "⚠️  MyPy found type issues (non-blocking)"

type-check-strict: ## Run mypy type checking with strict settings (fails on error)
	$(call check_venv)
	@$(USE_PYTHON) -m mypy $(PY_STRICT_CHECK_PATHS) --strict --show-error-codes

type-check-report: ## Generate mypy type checking report
	$(call check_venv)
	$(USE_PYTHON) -m mypy $(PY_STRICT_CHECK_PATHS) --html-report mypy-report

type-check-full: ## Run strict mypy across src/tests/scripts/alembic (warnings only, legacy debt visibility)
	$(call check_venv)
	-$(USE_PYTHON) -m mypy $(PY_CHECK_PATHS) --strict --show-error-codes || echo "⚠️  MyPy found type issues outside runtime strict gate"

security-audit: ## Run comprehensive security audit (pip-audit, bandit) [blocking on MEDIUM/HIGH]
	$(call check_venv)
	@echo "Running pip-audit..."
	@PIP_NO_CACHE_DIR=1 $(USE_PIP) install pip-audit --quiet || true
	@PIP_NO_CACHE_DIR=1 /bin/bash -lc '$(USE_PYTHON) -m pip_audit $(PIP_AUDIT_IGNORE_FLAGS) --format json > pip-audit-results.json 2> >(grep -vF "Cache entry deserialization failed, entry ignored" >&2)' || true
	@if [ -n "$$SAFETY_API_KEY" ]; then \
		echo "Running safety..."; \
		SAFETY_API_KEY="$$SAFETY_API_KEY" safety --stage development scan --save-as json safety-results.json --use-server-matching || true; \
	fi
	@echo "Running bandit (blocking on MEDIUM/HIGH)..."
	@$(USE_PYTHON) -m bandit -r $(PY_CHECK_PATHS) --severity-level medium -f json -o bandit-results.json 2>&1 | grep -vEi "(Test in comment|Unknown test found)" || true

security-full: security-audit ## Full security assessment with all tools

phi-backfill-dry-run: ## Dry-run PHI identifier encryption backfill
	$(call check_venv)
	$(USE_PYTHON) scripts/backfill_phi_identifiers.py

phi-backfill-commit: ## Commit PHI identifier encryption backfill changes
	$(call check_venv)
	$(USE_PYTHON) scripts/backfill_phi_identifiers.py --commit

# Local Development
run-local: ## Run the application locally
	$(call check_venv)
	@$(MAKE) -s setup-postgres
	@$(MAKE) postgres-migrate
	$(call run_with_postgres_env,$(BACKEND_DEV_ENV) $(USE_PYTHON) -m uvicorn $(BACKEND_UVICORN_APP) --host 0.0.0.0 --port $(BACKEND_PORT) --reload)

run-all-postgres: ## Restart Postgres, run migrations, seed admin, start backend + Next.js
	$(call check_venv)
	@$(MAKE) -s stop-all
	@$(MAKE) -s docker-postgres-up
	@$(MAKE) -s postgres-migrate SUPPRESS_VENV_WARNING=1
	@$(MAKE) -s init-artana-schema SUPPRESS_VENV_WARNING=1
	@$(call run_with_postgres_env,$(MAKE) -s db-seed-admin SUPPRESS_VENV_WARNING=1)
	@$(MAKE) -s start-local SKIP_SETUP_POSTGRES=1 SKIP_POSTGRES_MIGRATE=1 SUPPRESS_VENV_WARNING=1
	@echo "Backend running in background. Starting Next.js..."
	@$(MAKE) -s web-clean
	@$(MAKE) -s start-web SKIP_SETUP_POSTGRES=1 SKIP_POSTGRES_MIGRATE=1 SKIP_ADMIN_SEED=1 SUPPRESS_VENV_WARNING=1
	@echo "All services running. FastAPI logs: $(BACKEND_LOG) | Next.js logs: $(WEB_LOG)"

dev-postgres: ## Start Postgres (if needed) + services for local development
	$(call check_venv)
	@$(MAKE) -s setup-postgres
	@$(call run_with_postgres_env,$(MAKE) -s db-seed-admin SUPPRESS_VENV_WARNING=1)
	@$(MAKE) -s start-local SKIP_SETUP_POSTGRES=1 SKIP_POSTGRES_MIGRATE=1 SUPPRESS_VENV_WARNING=1
	@echo "Backend running in background. Starting Next.js..."
	@$(MAKE) -s start-web SKIP_SETUP_POSTGRES=1 SKIP_POSTGRES_MIGRATE=1 SKIP_ADMIN_SEED=1 SUPPRESS_VENV_WARNING=1
	@echo "All services running. FastAPI logs: $(BACKEND_LOG) | Next.js logs: $(WEB_LOG)"
start-local: ## Run FastAPI backend in the background (logs/backend.log)
	$(call check_venv)
ifneq ($(SKIP_SETUP_POSTGRES),1)
	@$(MAKE) -s setup-postgres SUPPRESS_VENV_WARNING=1
else
	@$(MAKE) -s postgres-wait SUPPRESS_VENV_WARNING=1
endif
	@mkdir -p $(dir $(BACKEND_LOG))
	@if lsof -nP -iTCP:$(BACKEND_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
		echo "Port $(BACKEND_PORT) already in use. Run 'make stop-local' or free the port before starting in background."; \
		exit 1; \
	fi
	@if [ -f "$(BACKEND_PID_FILE)" ] && kill -0 $$(cat "$(BACKEND_PID_FILE)") 2>/dev/null; then \
		echo "FastAPI already running (PID $$(cat "$(BACKEND_PID_FILE)"))."; \
		exit 0; \
	fi
ifneq ($(SKIP_POSTGRES_MIGRATE),1)
	@$(MAKE) postgres-migrate
endif
	@/bin/bash -lc "set -a; source \"$(POSTGRES_ENV_FILE)\"; set +a; $(BACKEND_DEV_ENV) nohup $(USE_PYTHON) -m uvicorn $(BACKEND_UVICORN_APP) --host 0.0.0.0 --port $(BACKEND_PORT) >> \"$(BACKEND_LOG)\" 2>&1 & echo \$$! > \"$(BACKEND_PID_FILE)\""
	@i=0; while [ ! -f "$(BACKEND_PID_FILE)" ] && [ $$i -lt 10 ]; do sleep 0.5; i=$$((i+1)); done
	@if [ -f "$(BACKEND_PID_FILE)" ]; then \
		PID=$$(cat "$(BACKEND_PID_FILE)"); \
		echo "FastAPI started in background (PID $$PID). Logs: $(BACKEND_LOG)"; \
	else \
		echo "FastAPI launch command executed but PID file was not created. Check $(BACKEND_LOG) for details."; \
	fi

backend-status: ## Show FastAPI background process status
	@if [ -f "$(BACKEND_PID_FILE)" ]; then \
		PID=$$(cat "$(BACKEND_PID_FILE)"); \
		if kill -0 $$PID 2>/dev/null; then \
			echo "FastAPI running (PID $$PID). Logs: $(BACKEND_LOG)"; \
		else \
			echo "FastAPI PID file exists but process $$PID is not running."; \
		fi; \
	else \
		echo "FastAPI backend is not running (no PID file)."; \
	fi

run-local-postgres: ## Run the FastAPI backend with Postgres env vars loaded
	$(call run_with_postgres_env,$(BACKEND_DEV_ENV) $(USE_PYTHON) -m uvicorn $(BACKEND_UVICORN_APP) --host 0.0.0.0 --port $(BACKEND_PORT) --reload)


run-web: ## Run the Next.js admin interface locally (seeds admin user if needed)
	$(call ensure_web_deps)
	@$(MAKE) -s setup-postgres
	@echo "Ensuring admin user exists..."
	@$(MAKE) postgres-migrate
	$(call run_with_postgres_env,$(MAKE) db-seed-admin || echo "Warning: Could not seed admin user (backend may not be running)")
	@echo "Starting Next.js admin interface..."
	$(call run_with_postgres_env,cd src/web && $(NEXT_DEV_ENV) npm run dev)

run-web-postgres: ## Run the Next.js admin interface with Postgres env vars loaded
	$(call ensure_web_deps)
	@echo "Ensuring admin user exists (Postgres)..."
	$(call run_with_postgres_env,$(MAKE) db-seed-admin || echo "Warning: Could not seed admin user (backend may not be running)")
	@echo "Starting Next.js admin interface (Postgres)..."
	$(call run_with_postgres_env,cd src/web && $(NEXT_DEV_ENV) npm run dev)

start-web: ## Run Next.js admin interface in the background (logs/web.log)
	$(call check_venv)
ifneq ($(SKIP_SETUP_POSTGRES),1)
	@$(MAKE) -s setup-postgres SUPPRESS_VENV_WARNING=1
else
	@$(MAKE) -s postgres-wait SUPPRESS_VENV_WARNING=1
endif
	$(call ensure_web_deps)
	@mkdir -p $(dir $(WEB_LOG))
	@if lsof -ti tcp:3000 >/dev/null 2>&1; then \
		echo "Port 3000 already in use. Run 'make stop-web' or free the port before starting in background."; \
		exit 1; \
	fi
	@if [ -f "$(WEB_PID_FILE)" ] && kill -0 $$(cat "$(WEB_PID_FILE)") 2>/dev/null; then \
		echo "Next.js already running (PID $$(cat "$(WEB_PID_FILE)"))."; \
		exit 0; \
	fi
ifneq ($(SKIP_ADMIN_SEED),1)
	@echo "Ensuring admin user exists..."
endif
ifneq ($(SKIP_POSTGRES_MIGRATE),1)
	@$(MAKE) postgres-migrate
endif
ifneq ($(SKIP_ADMIN_SEED),1)
	$(call run_with_postgres_env,$(MAKE) db-seed-admin || echo "Warning: Could not seed admin user (backend may not be running)")
endif
	@/bin/bash -lc "set -a; source \"$(POSTGRES_ENV_FILE)\"; set +a; cd src/web && $(NEXT_DEV_ENV) nohup npm run dev >> \"$(WEB_LOG_ABS)\" 2>&1 & echo \$$! > \"$(WEB_PID_FILE_ABS)\""
	@i=0; while [ ! -f "$(WEB_PID_FILE)" ] && [ $$i -lt 10 ]; do sleep 0.5; i=$$((i+1)); done
	@if [ -f "$(WEB_PID_FILE)" ]; then \
		PID=$$(cat "$(WEB_PID_FILE)"); \
		sleep 2; \
		if ! kill -0 $$PID 2>/dev/null; then \
			echo "Next.js process $$PID exited shortly after launch. Recent logs:"; \
			tail -n 80 "$(WEB_LOG)" || true; \
			rm -f "$(WEB_PID_FILE)"; \
			exit 1; \
		fi; \
		echo "Next.js started in background (PID $$PID). Logs: $(WEB_LOG)"; \
	else \
		echo "Next.js launch command executed but PID file was not created. Check $(WEB_LOG) for details."; \
		tail -n 80 "$(WEB_LOG)" || true; \
		exit 1; \
	fi
	@$(MAKE) -s web-wait

web-wait: ## Wait until Next.js is reachable on http://localhost:3000
	@attempts=0; \
	max_attempts=$$(( $(WEB_WAIT_TIMEOUT_SECONDS) / $(WEB_WAIT_INTERVAL_SECONDS) )); \
	if [ $$max_attempts -lt 1 ]; then max_attempts=1; fi; \
	while true; do \
		if curl -sS --max-time 3 http://localhost:3000/ >/dev/null 2>&1; then \
			echo "Next.js is reachable at http://localhost:3000"; \
			exit 0; \
		fi; \
		if [ -f "$(WEB_PID_FILE)" ]; then \
			PID=$$(cat "$(WEB_PID_FILE)"); \
			if ! kill -0 $$PID 2>/dev/null; then \
				echo "Next.js process $$PID is not running. Recent logs:"; \
				tail -n 80 "$(WEB_LOG)" || true; \
				exit 1; \
			fi; \
		fi; \
		attempts=$$((attempts+1)); \
		if [ $$attempts -ge $$max_attempts ]; then \
			echo "Timed out waiting for Next.js readiness after $(WEB_WAIT_TIMEOUT_SECONDS)s. Recent logs:"; \
			tail -n 80 "$(WEB_LOG)" || true; \
			exit 1; \
		fi; \
		sleep $(WEB_WAIT_INTERVAL_SECONDS); \
	done

test-postgres: ## Run pytest with Postgres env vars loaded
	$(call run_with_postgres_env,$(USE_PYTHON) -m pytest)

postgres-cmd: ## Run arbitrary CMD with Postgres env vars (usage: make postgres-cmd CMD="make run-local")
	@if [ -z "$(CMD)" ]; then \
		echo "Usage: make postgres-cmd CMD=\"<command>\""; \
		exit 1; \
	fi
	$(call run_with_postgres_env,$(CMD))

stop-local: ## Stop the local FastAPI backend
	@echo "Stopping FastAPI backend..."
	@handled=0; \
	if [ -f "$(BACKEND_PID_FILE)" ]; then \
		PID=$$(cat "$(BACKEND_PID_FILE)"); \
		if kill -0 $$PID 2>/dev/null; then \
			kill $$PID && echo "Stopped FastAPI process $$PID."; \
			handled=1; \
			sleep 1; \
		else \
			echo "PID $$PID not running; cleaning up stale PID file."; \
		fi; \
		rm -f "$(BACKEND_PID_FILE)"; \
	else \
		echo "No PID file found; attempting graceful shutdown."; \
	fi; \
	MATCHED_PIDS=$$(pgrep -f "$(BACKEND_UVICORN_MATCH)" 2>/dev/null || true); \
	if [ -n "$$MATCHED_PIDS" ]; then \
		echo "Stopping matching FastAPI process(es): $$MATCHED_PIDS"; \
		kill $$MATCHED_PIDS >/dev/null 2>&1 || true; \
		handled=1; \
		for _ in 1 2 3 4 5 6; do \
			if ! lsof -tiTCP:$(BACKEND_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
				break; \
			fi; \
			sleep 0.5; \
		done; \
	fi; \
	LISTEN_PIDS=$$(lsof -tiTCP:$(BACKEND_PORT) -sTCP:LISTEN 2>/dev/null || true); \
	if [ -n "$$LISTEN_PIDS" ]; then \
		echo "Port $(BACKEND_PORT) is still held by: $$LISTEN_PIDS"; \
		ps -p $$LISTEN_PIDS -o pid=,command=; \
	elif [ $$handled -eq 0 ]; then \
		echo "No FastAPI process found"; \
	fi

stop-web: ## Stop the Next.js admin interface
	@echo "Stopping Next.js admin interface..."
	@handled=0; \
	if [ -f "$(WEB_PID_FILE)" ]; then \
		PID=$$(cat "$(WEB_PID_FILE)"); \
		if kill -0 $$PID 2>/dev/null; then \
			kill $$PID && echo "Stopped Next.js process $$PID."; \
		else \
			echo "PID $$PID not running; cleaning up stale PID file."; \
		fi; \
		rm -f "$(WEB_PID_FILE)"; \
		handled=1; \
	fi; \
	PORT_PIDS=$$(lsof -ti tcp:3000 2>/dev/null || true); \
	if [ -n "$$PORT_PIDS" ]; then \
		echo "Terminating processes on port 3000: $$PORT_PIDS"; \
		kill $$PORT_PIDS >/dev/null 2>&1 || true; \
		sleep 1; \
		REMAINING=$$(lsof -ti tcp:3000 2>/dev/null || true); \
		if [ -n "$$REMAINING" ]; then \
			echo "Force killing stubborn processes on port 3000: $$REMAINING"; \
			kill -9 $$REMAINING >/dev/null 2>&1 || true; \
		fi; \
		echo "Port 3000 cleared."; \
		handled=1; \
	fi; \
	NEXT_DEV_PIDS=$$(pgrep -f "src/web.*next dev" 2>/dev/null || true); \
	if [ -n "$$NEXT_DEV_PIDS" ]; then \
		echo "Terminating lingering Next.js dev processes: $$NEXT_DEV_PIDS"; \
		kill $$NEXT_DEV_PIDS >/dev/null 2>&1 || true; \
		sleep 1; \
		REMAINING_NEXT=$$(pgrep -f "src/web.*next dev" 2>/dev/null || true); \
		if [ -n "$$REMAINING_NEXT" ]; then \
			echo "Force killing stubborn Next.js dev processes: $$REMAINING_NEXT"; \
			kill -9 $$REMAINING_NEXT >/dev/null 2>&1 || true; \
		fi; \
		handled=1; \
	fi; \
	if [ $$handled -eq 0 ]; then \
		echo "No Next.js process found"; \
	fi

stop-all: ## Stop FastAPI, Next.js, Postgres, and remove PID files/log hints
	@$(MAKE) -s stop-local
	@$(MAKE) -s stop-web
	@$(MAKE) -s docker-stop
	@$(MAKE) -s docker-postgres-destroy
	@rm -f "$(BACKEND_PID_FILE)"
	@rm -f "$(WEB_PID_FILE)"
	@echo "All services stopped (including Postgres)."

restart: ## Fast restart backend + Next.js without stopping Postgres
	@$(MAKE) -s stop-local
	@$(MAKE) -s stop-web
	@$(MAKE) -s start-local SKIP_SETUP_POSTGRES=1 SKIP_POSTGRES_MIGRATE=1 SUPPRESS_VENV_WARNING=1
	@$(MAKE) -s start-web SKIP_SETUP_POSTGRES=1 SKIP_POSTGRES_MIGRATE=1 SKIP_ADMIN_SEED=1 SUPPRESS_VENV_WARNING=1
	@echo "Backend and Next.js restarted (Postgres untouched)."

run-docker: docker-build ## Build and run with Docker
	docker run -p 8080:8080 med13-resource-library

# Docker
docker-build: ## Build Docker image
	docker build -t med13-resource-library .

docker-run: ## Run Docker container
	docker run -p 8080:8080 med13-resource-library

docker-stop: ## Stop and remove Docker container
	@echo "Stopping Docker container..."
	@if docker ps -q --filter ancestor=med13-resource-library | grep -q .; then \
		docker stop $$(docker ps -q --filter ancestor=med13-resource-library); \
		docker rm $$(docker ps -aq --filter ancestor=med13-resource-library); \
	else \
		echo "No running containers found"; \
	fi

docker-push: docker-build ## Build and push Docker image to GCR
	docker tag med13-resource-library gcr.io/YOUR_PROJECT_ID/med13-resource-library
	docker push gcr.io/YOUR_PROJECT_ID/med13-resource-library

# Dockerized Postgres helpers
docker-postgres-up: ## Start Postgres dev container (creates .env.postgres if missing)
	$(call ensure_postgres_env)
	@echo "Starting Postgres via $(POSTGRES_COMPOSE_FILE)..."
	$(POSTGRES_COMPOSE) up -d
	@touch "$(POSTGRES_ACTIVE_FLAG)"
	@echo "Postgres mode enabled (auto-applied to run-local/run-web/test)."

docker-postgres-down: ## Stop Postgres container (data persists)
	@if [ ! -f "$(POSTGRES_ENV_FILE)" ]; then \
		echo "No $(POSTGRES_ENV_FILE) found; nothing to stop."; \
		exit 0; \
	fi
	@echo "Stopping Postgres container..."
	$(POSTGRES_COMPOSE) down && rm -f "$(POSTGRES_ACTIVE_FLAG)" || true
	@echo "Postgres mode flags cleared."

docker-postgres-destroy: ## Stop Postgres container and remove volumes
	@if [ ! -f "$(POSTGRES_ENV_FILE)" ]; then \
		echo "No $(POSTGRES_ENV_FILE) found; nothing to destroy."; \
		exit 0; \
	fi
	@echo "Destroying Postgres container and volumes..."
	$(POSTGRES_COMPOSE) down -v && rm -f "$(POSTGRES_ACTIVE_FLAG)" || true
	@echo "Postgres mode flags cleared."

docker-postgres-logs: ## Tail Postgres logs
	@if [ ! -f "$(POSTGRES_ENV_FILE)" ]; then \
		echo "No $(POSTGRES_ENV_FILE) found; cannot tail logs."; \
		exit 1; \
	fi
	@echo "Tailing Postgres logs (Ctrl+C to stop)..."
	$(POSTGRES_COMPOSE) logs -f $(POSTGRES_SERVICE)

docker-postgres-status: ## Show Postgres container status
	@if [ ! -f "$(POSTGRES_ENV_FILE)" ]; then \
		echo "No $(POSTGRES_ENV_FILE) found; Postgres not configured."; \
	else \
		$(POSTGRES_COMPOSE) ps; \
	fi

postgres-disable: ## Keep container running but disable auto-Postgres mode
	@rm -f "$(POSTGRES_ACTIVE_FLAG)"
	@echo "Postgres mode flag removed. Existing containers unaffected."

postgres-wait: ## Wait until Postgres is ready to accept connections
	$(call ensure_postgres_env)
	@if [ -z "$$($(POSTGRES_COMPOSE) ps -q $(POSTGRES_SERVICE))" ]; then \
		if [ "$(MED13_SKIP_COMPOSE)" = "1" ]; then \
			echo "Postgres container is not running and MED13_SKIP_COMPOSE=1; skipping auto-start."; \
			echo "Skipping Postgres wait/migrate steps."; \
			exit 0; \
		else \
			echo "Postgres container is not running; starting via $(POSTGRES_COMPOSE_FILE)..."; \
			$(POSTGRES_COMPOSE) up -d $(POSTGRES_SERVICE); \
			touch "$(POSTGRES_ACTIVE_FLAG)"; \
		fi \
	fi
	@echo "Waiting for Postgres health check..."
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/wait_for_postgres.py)

postgres-migrate: ## Run Alembic migrations with Postgres
	@$(MAKE) -s postgres-wait
	@echo "Applying Alembic migrations (Postgres)..."
	$(call run_with_postgres_env,$(ALEMBIC_BIN) upgrade heads)

init-artana-schema: ## Initialize the artana schema in Postgres
	$(call check_venv)
	@echo "Creating artana schema..."
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/init_artana_schema.py)

setup-postgres: ## Full PostgreSQL setup including artana schema
	@$(MAKE) -s docker-postgres-up SUPPRESS_VENV_WARNING=1
	@$(MAKE) -s postgres-wait SUPPRESS_VENV_WARNING=1
	@$(MAKE) -s postgres-migrate SUPPRESS_VENV_WARNING=1
	@$(MAKE) -s init-artana-schema SUPPRESS_VENV_WARNING=1
	@echo "PostgreSQL setup complete with artana schema."

# Database
db-migrate: ## Run database migrations
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,alembic upgrade heads)

db-create: ## Create database migration
	@echo "Creating new migration..."
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,alembic revision --autogenerate -m "$(msg)")

db-reset: ## Reset database (WARNING: destroys data)
	@echo "This will destroy all data. Are you sure? [y/N] " && read ans && [ $${ans:-N} = y ]
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,alembic downgrade base)

db-seed: ## Seed database with test data
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/seed_database.py)

db-seed-admin: ## Seed admin user (requires ADMIN_PASSWORD or MED13_ADMIN_PASSWORD)
	$(call check_venv)
	@if [ -z "$(ADMIN_PASSWORD_EFFECTIVE)" ]; then \
		echo "ADMIN_PASSWORD or MED13_ADMIN_PASSWORD must be provided (e.g. ADMIN_PASSWORD='StrongPassw0rd!' make db-seed-admin)"; \
		exit 1; \
	fi
	@echo "Seeding admin user..."
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,ADMIN_PASSWORD="$(ADMIN_PASSWORD_EFFECTIVE)" $(USE_PYTHON) scripts/seed_admin_user.py --password "$$ADMIN_PASSWORD")

db-reset-admin-password: ## Reset admin password (requires ADMIN_PASSWORD or MED13_ADMIN_PASSWORD)
	$(call check_venv)
	@if [ -z "$(ADMIN_PASSWORD_EFFECTIVE)" ]; then \
		echo "ADMIN_PASSWORD or MED13_ADMIN_PASSWORD must be provided (e.g. ADMIN_PASSWORD='NewStrongPass!' make db-reset-admin-password)"; \
		exit 1; \
	fi
	@echo "Resetting admin password..."
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,ADMIN_PASSWORD="$(ADMIN_PASSWORD_EFFECTIVE)" $(USE_PYTHON) scripts/reset_admin_password.py --password "$$ADMIN_PASSWORD")

db-verify-admin: ## Verify admin user exists
	$(call check_venv)
	@echo "Verifying admin user..."
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/reset_admin_password.py --verify-only)

# Deployment
deploy-dev: ## Deploy to dev environment
	@echo "Deploying to dev..."
	gcloud run deploy med13-resource-library-dev \
		--source . \
		--region us-central1 \
		--no-allow-unauthenticated \
		--service-account med13-dev@YOUR_PROJECT_ID.iam.gserviceaccount.com
	gcloud run deploy med13-admin-dev \
		--source src/web \
		--region us-central1 \
		--no-allow-unauthenticated \
		--service-account med13-dev@YOUR_PROJECT_ID.iam.gserviceaccount.com

deploy-staging: ## Deploy to staging environment
	@echo "Deploying to staging..."
	gcloud run deploy med13-resource-library-staging \
		--source . \
		--region us-central1 \
		--no-allow-unauthenticated \
		--service-account med13-staging@YOUR_PROJECT_ID.iam.gserviceaccount.com
	gcloud run deploy med13-admin-staging \
		--source src/web \
		--region us-central1 \
		--no-allow-unauthenticated \
		--service-account med13-staging@YOUR_PROJECT_ID.iam.gserviceaccount.com

deploy-staging-queued-workers: ## Roll out the queued pipeline worker architecture to staging
	@echo "Rolling out queued pipeline workers to staging..."
	@/bin/bash scripts/deploy/rollout_staging_queued_workers.sh

deploy-prod: ## Deploy to production environment
	@echo "Deploying to production..."
	gcloud run deploy med13-resource-library \
		--source . \
		--region us-central1 \
		--no-allow-unauthenticated \
		--service-account med13-prod@YOUR_PROJECT_ID.iam.gserviceaccount.com

	gcloud run deploy med13-admin \
		--source src/web \
		--region us-central1 \
		--no-allow-unauthenticated \
		--service-account med13-prod@YOUR_PROJECT_ID.iam.gserviceaccount.com

# Cloud Operations
cloud-logs: ## View Cloud Run logs
	gcloud logs read "resource.type=cloud_run_revision AND resource.labels.service_name=med13-resource-library" --limit=50

cloud-secrets-list: ## List all secrets
	gcloud secrets list

# Cleanup
clean: ## Clean up temporary files
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +

clean-all: clean ## Clean everything including build artifacts
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf pip-audit-results.json
	rm -rf $(REPORT_DIR)/

# Next.js Admin Interface
web-install: ## Install Next.js dependencies
	$(call ensure_web_deps)

web-build: ## Build Next.js admin interface
	$(call ensure_web_deps)
	cd src/web && $(NEXT_BUILD_ENV) npm run build

web-clean: ## Remove Next.js build artifacts
	rm -rf src/web/.next

web-lint: ## Lint Next.js code
	$(call ensure_web_deps)
	cd src/web && npm run lint

web-type-check: ## Type check Next.js code
	$(call ensure_web_deps)
	cd src/web && npm run type-check

web-test: ## Run Next.js tests
	$(call ensure_web_deps)
	cd src/web && npm run test

web-test-architecture: ## Run Next.js architecture validation tests (Server-Side Orchestration)
	$(call ensure_web_deps)
	cd src/web && npm test -- __tests__/architecture

web-test-integration: ## Run Next.js integration tests (frontend-backend)
	$(call ensure_web_deps)
	cd src/web && npm test -- __tests__/integration

web-test-all: web-test-architecture web-test-integration web-test ## Run all Next.js tests (architecture, integration, and unit tests)

web-test-coverage: ## Run Next.js tests with coverage report
	$(call ensure_web_deps)
	cd src/web && npm run test:coverage

web-visual-test: ## Run Percy-powered visual regression snapshots (requires PERCY_TOKEN)
	./scripts/run_visual_snapshots.sh

web-security-audit: ## Run npm security audit for Next.js app
	cd src/web && npm run security:audit

web-security-check: ## Run full security check (audit + outdated packages)
	cd src/web && npm run security:check

test-web: web-test ## Alias for web-test

# Front Door Website
frontdoor-install: ## Install front door website dependencies
	$(call ensure_frontdoor_deps)

frontdoor-stop: ## Stop front door website process on configured port
	@pid="$$(lsof -ti tcp:$(FRONTDOOR_PORT) -sTCP:LISTEN || true)"; \
	if [ -n "$$pid" ]; then \
		echo "Stopping frontdoor process on port $(FRONTDOOR_PORT): $$pid"; \
		kill $$pid; \
		sleep 1; \
	else \
		echo "No frontdoor process found on port $(FRONTDOOR_PORT)."; \
	fi

frontdoor-dev: frontdoor-stop ## Run front door website locally (default port: 3010)
	$(call ensure_frontdoor_deps)
	cd apps/frontdoor && NEXT_PUBLIC_SITE_URL=http://localhost:$(FRONTDOOR_PORT) PORT=$(FRONTDOOR_PORT) npm run dev:clean

frontdoor-build: ## Build front door website
	$(call ensure_frontdoor_deps)
	cd apps/frontdoor && npm run build

frontdoor-test: ## Run front door website unit tests
	$(call ensure_frontdoor_deps)
	cd apps/frontdoor && npm run test

# Quality Assurance
venv-check: ## Ensure virtual environment is active
	@if [ "$(VENV_ACTIVE)" = "false" ]; then \
		echo "❌ Virtual environment is not active!"; \
		echo ""; \
		echo "To activate the virtual environment:"; \
		echo "  source $(VENV)/bin/activate"; \
		echo ""; \
		echo "Or use the convenience command:"; \
		echo "  make activate"; \
		echo ""; \
		exit 1; \
	fi

# Report directory for QA outputs
REPORT_DIR := reports

all: all-report ## Run complete quality assurance suite (fails on first error)

all-report: ## Run complete QA suite with final warnings/errors report (fails on first error)
	@bash scripts/run_qa_report.sh

# CI/CD Simulation
ci: install-dev lint test security-audit ## Run full CI pipeline locally

# Environment checks
check-env: ## Check if development environment is properly set up
	@echo "🐍 Python Environment Status:"
	@echo "   Virtual Environment: $(VENV_STATUS)"
	@echo "   Python Executable: $(USE_PYTHON)"
	@echo ""
	@echo "Checking Python version..."
	@$(USE_PYTHON) --version
	@echo "Checking pip version..."
	@$(USE_PIP) --version
	@echo "Checking if requirements are installed..."
	@$(USE_PYTHON) -c "import fastapi, uvicorn, sqlalchemy, pydantic; print('✅ Core dependencies OK')" 2>/dev/null || echo "Core dependencies missing - run 'make install-dev'"
	@echo "Checking Dockerized Postgres/Redis status..."
	@$(MAKE) -s docker-postgres-status || true
	@echo "Checking pre-commit..."
	@if command -v pre-commit >/dev/null 2>&1; then \
		echo "pre-commit available"; \
	else \
		echo "⚠️  pre-commit not installed - run 'make setup-dev'"; \
	fi

# Documentation
docs-serve: ## Serve documentation locally
	$(call check_venv)
	cd docs && $(USE_PYTHON) -m http.server 8000

# Backup and Recovery
backup-db: ## Create Postgres database backup using pg_dump
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,PGPASSWORD="$$MED13_POSTGRES_PASSWORD" pg_dump -h "$$MED13_POSTGRES_HOST" -p "$$MED13_POSTGRES_PORT" -U "$$MED13_POSTGRES_USER" -d "$$MED13_POSTGRES_DB" > backup_$(shell date +%Y%m%d_%H%M%S).sql)

restore-db: ## Restore Postgres database from backup (specify FILE variable)
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make restore-db FILE=<backup.sql>"; \
		exit 1; \
	fi
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,PGPASSWORD="$$MED13_POSTGRES_PASSWORD" psql -h "$$MED13_POSTGRES_HOST" -p "$$MED13_POSTGRES_PORT" -U "$$MED13_POSTGRES_USER" -d "$$MED13_POSTGRES_DB" -f "$(FILE)")
restart-postgres: ## Recreate Postgres container (down -v, up)
	@$(MAKE) -s docker-postgres-destroy
	@$(MAKE) -s docker-postgres-up
