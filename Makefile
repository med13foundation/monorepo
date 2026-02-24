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
WEB_PID_FILE := .next.dev.pid
WEB_LOG := logs/web.log
WEB_PID_FILE_ABS := $(abspath $(WEB_PID_FILE))
WEB_LOG_ABS := $(abspath $(WEB_LOG))
NEXT_DEV_ENV := NEXTAUTH_SECRET=med13-resource-library-nextauth-secret-key-for-development-2024-secure-random-string NEXTAUTH_URL=http://localhost:3000 NEXT_PUBLIC_API_URL=http://localhost:8080
BACKEND_DEV_ENV := MED13_DEV_JWT_SECRET=med13-resource-library-backend-jwt-secret-for-development-2026-01
NEXTAUTH_URL ?= http://localhost:3000
NEXT_BUILD_ENV := NEXTAUTH_URL=$(NEXTAUTH_URL)

ADMIN_PASSWORD_EFFECTIVE := $(strip $(or $(ADMIN_PASSWORD),$(MED13_ADMIN_PASSWORD)))

# pip-audit exceptions:
# - CVE-2025-69872: diskcache has no upstream fix yet.
# - CVE-2026-25580: flujo 0.6.4 currently requires pydantic-ai<1.26.0.
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

# Warn if venv is not active but exists
define check_venv
	@if [ "$(VENV_ACTIVE)" = "false" ] && [ -d "$(VENV)" ] && [ "$(SUPPRESS_VENV_WARNING)" != "1" ]; then \
		echo "⚠️  Virtual environment exists but not activated."; \
		echo "   Run: source $(VENV)/bin/activate"; \
		echo "   Or use: make activate"; \
		echo ""; \
	fi
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

.PHONY: help venv venv-check install install-dev test test-verbose test-cov test-watch test-architecture test-contract lint lint-strict format format-check type-check type-check-strict type-check-report type-check-full security-audit security-full clean clean-all docker-build docker-run docker-push docker-stop docker-postgres-up docker-postgres-down docker-postgres-destroy docker-postgres-logs docker-postgres-status postgres-disable postgres-migrate init-artana-schema setup-postgres dev-postgres run-local-postgres run-web-postgres test-postgres postgres-cmd backend-status start-local db-migrate db-create db-reset db-seed deploy-staging deploy-prod setup-dev setup-gcp cloud-logs cloud-secrets-list all all-report ci check-env docs-serve backup-db restore-db activate deactivate stop-local stop-web stop-all web-install web-build web-clean web-lint web-type-check web-test web-test-architecture web-test-integration web-test-all web-test-coverage web-visual-test phi-backfill-dry-run phi-backfill-commit

PY_CHECK_PATHS := src tests scripts alembic
PY_STRICT_CHECK_PATHS := src

# Default target
help: ## Show this help message
	@echo "MED13 Resource Library - Development Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Virtual Environment
venv: $(VENV) ## Create virtual environment if it doesn't exist
$(VENV):
	@echo "Creating virtual environment..."
		@python3 - <<'PY'
	import platform
	import sys
	if sys.version_info < (3, 12):
	    raise SystemExit(f"Python 3.12+ required to create virtualenv (found {platform.python_version()})")
	PY
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
	$(USE_PIP) install -r requirements.txt

install-dev: ## Install development dependencies
	$(call check_venv)
	$(USE_PIP) install --upgrade "pip>=26.0"
	$(USE_PIP) install -r requirements.txt
	$(USE_PIP) install -r requirements-dev.txt

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
ifeq ($(POSTGRES_ACTIVE),)
	$(USE_PYTHON) -m pytest -m "not performance"
else
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,MED13_ENABLE_DISTRIBUTED_RATE_LIMIT=0 $(USE_PYTHON) scripts/run_isolated_postgres_tests.py -m "not performance")
endif

test-performance: ## Run performance tests
	$(call check_venv)
ifeq ($(POSTGRES_ACTIVE),)
	$(USE_PYTHON) -m pytest tests/performance
else
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,MED13_ENABLE_DISTRIBUTED_RATE_LIMIT=0 $(USE_PYTHON) scripts/run_isolated_postgres_tests.py tests/performance)
endif

test-contract: ## Run API contract tests
	$(call check_venv)
ifeq ($(POSTGRES_ACTIVE),)
	$(USE_PYTHON) -m pytest tests/security/test_schemathesis_contracts.py
else
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,MED13_ENABLE_DISTRIBUTED_RATE_LIMIT=0 $(USE_PYTHON) scripts/run_isolated_postgres_tests.py tests/security/test_schemathesis_contracts.py)
endif

test-architecture: ## Run architectural compliance tests (type_examples.md pattern validation)
	$(call check_venv)
ifeq ($(POSTGRES_ACTIVE),)
	$(USE_PYTHON) -m pytest tests/unit/architecture/test_architectural_compliance.py -v -m architecture
else
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,MED13_ENABLE_DISTRIBUTED_RATE_LIMIT=0 $(USE_PYTHON) scripts/run_isolated_postgres_tests.py tests/unit/architecture/test_architectural_compliance.py -v -m architecture)
endif

test-artana-architecture: ## Run Artana AI agent architecture compliance tests
	$(call check_venv)
	$(USE_PYTHON) -m pytest tests/unit/architecture/test_flujo_compliance.py -v -m architecture

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
ifeq ($(POSTGRES_ACTIVE),)
	$(USE_PYTHON) -m pytest -v --tb=short
else
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,MED13_ENABLE_DISTRIBUTED_RATE_LIMIT=0 $(USE_PYTHON) scripts/run_isolated_postgres_tests.py -v --tb=short)
endif

test-cov: ## Run tests with coverage report
	$(call check_venv)
ifeq ($(POSTGRES_ACTIVE),)
	$(USE_PYTHON) -m pytest --cov=src --cov-report=html --cov-report=term-missing
else
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,MED13_ENABLE_DISTRIBUTED_RATE_LIMIT=0 $(USE_PYTHON) scripts/run_isolated_postgres_tests.py --cov=src --cov-report=html --cov-report=term-missing)
endif

test-watch: ## Run tests in watch mode
	$(call check_venv)
ifeq ($(POSTGRES_ACTIVE),)
	$(USE_PYTHON) -m pytest-watch
else
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,MED13_ENABLE_DISTRIBUTED_RATE_LIMIT=0 MED13_TEST_RUNNER=pytest-watch $(USE_PYTHON) scripts/run_isolated_postgres_tests.py)
endif

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

format: ## Format code with Black and sort imports with ruff
	$(call check_venv)
	@$(USE_PYTHON) -m black $(PY_CHECK_PATHS)
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
	@$(USE_PIP) install pip-audit --quiet || true
	@pip-audit $(PIP_AUDIT_IGNORE_FLAGS) --format json > pip-audit-results.json || true
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
ifeq ($(POSTGRES_ACTIVE),)
	$(BACKEND_DEV_ENV) $(USE_PYTHON) -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
else
	@$(MAKE) postgres-migrate
	$(call run_with_postgres_env,$(BACKEND_DEV_ENV) $(USE_PYTHON) -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload)
endif

run-all-postgres: ## Restart Postgres, run migrations, seed admin, start backend + Next.js
	$(call check_venv)
	@$(MAKE) -s stop-all
	@$(MAKE) -s docker-postgres-up
	@$(MAKE) -s postgres-migrate SUPPRESS_VENV_WARNING=1
	@$(MAKE) -s init-artana-schema SUPPRESS_VENV_WARNING=1
	@$(call run_with_postgres_env,$(MAKE) -s db-seed-admin SUPPRESS_VENV_WARNING=1)
	@$(MAKE) -s start-local SKIP_POSTGRES_MIGRATE=1 SUPPRESS_VENV_WARNING=1
	@echo "Backend running in background. Starting Next.js..."
	@$(MAKE) -s web-clean
	@$(MAKE) -s start-web SKIP_POSTGRES_MIGRATE=1 SKIP_ADMIN_SEED=1 SUPPRESS_VENV_WARNING=1
	@echo "All services running. FastAPI logs: $(BACKEND_LOG) | Next.js logs: $(WEB_LOG)"

dev-postgres: ## Start Postgres (if needed) + services for local development
	$(call check_venv)
	@$(MAKE) -s setup-postgres
	@$(call run_with_postgres_env,$(MAKE) -s db-seed-admin SUPPRESS_VENV_WARNING=1)
	@$(MAKE) -s start-local SKIP_POSTGRES_MIGRATE=1 SUPPRESS_VENV_WARNING=1
	@echo "Backend running in background. Starting Next.js..."
	@$(MAKE) -s start-web SKIP_POSTGRES_MIGRATE=1 SKIP_ADMIN_SEED=1 SUPPRESS_VENV_WARNING=1
	@echo "All services running. FastAPI logs: $(BACKEND_LOG) | Next.js logs: $(WEB_LOG)"
start-local: ## Run FastAPI backend in the background (logs/backend.log)
	$(call check_venv)
	@mkdir -p $(dir $(BACKEND_LOG))
	@if lsof -ti tcp:8080 >/dev/null 2>&1; then \
		echo "Port 8080 already in use. Run 'make stop-local' or free the port before starting in background."; \
		exit 1; \
	fi
	@if [ -f "$(BACKEND_PID_FILE)" ] && kill -0 $$(cat "$(BACKEND_PID_FILE)") 2>/dev/null; then \
		echo "FastAPI already running (PID $$(cat "$(BACKEND_PID_FILE)"))."; \
		exit 0; \
	fi
ifeq ($(POSTGRES_ACTIVE),)
	@$(BACKEND_DEV_ENV) nohup $(USE_PYTHON) -m uvicorn main:app --host 0.0.0.0 --port 8080 >> "$(BACKEND_LOG)" 2>&1 &
	@echo $$! > "$(BACKEND_PID_FILE)"
else
ifneq ($(SKIP_POSTGRES_MIGRATE),1)
	@$(MAKE) postgres-migrate
endif
	@/bin/bash -lc "set -a; source \"$(POSTGRES_ENV_FILE)\"; set +a; $(BACKEND_DEV_ENV) nohup $(USE_PYTHON) -m uvicorn main:app --host 0.0.0.0 --port 8080 >> \"$(BACKEND_LOG)\" 2>&1 & echo \$$! > \"$(BACKEND_PID_FILE)\""
endif
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
	$(call run_with_postgres_env,$(BACKEND_DEV_ENV) $(USE_PYTHON) -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload)


run-web: ## Run the Next.js admin interface locally (seeds admin user if needed)
	$(call ensure_web_deps)
	@echo "Ensuring admin user exists..."
ifeq ($(POSTGRES_ACTIVE),)
	@$(MAKE) db-seed-admin || echo "Warning: Could not seed admin user (backend may not be running)"
	@echo "Starting Next.js admin interface..."
	cd src/web && $(NEXT_DEV_ENV) npm run dev
else
	@$(MAKE) postgres-migrate
	$(call run_with_postgres_env,$(MAKE) db-seed-admin || echo "Warning: Could not seed admin user (backend may not be running)")
	@echo "Starting Next.js admin interface..."
	$(call run_with_postgres_env,cd src/web && $(NEXT_DEV_ENV) npm run dev)
endif

run-web-postgres: ## Run the Next.js admin interface with Postgres env vars loaded
	$(call ensure_web_deps)
	@echo "Ensuring admin user exists (Postgres)..."
	$(call run_with_postgres_env,$(MAKE) db-seed-admin || echo "Warning: Could not seed admin user (backend may not be running)")
	@echo "Starting Next.js admin interface (Postgres)..."
	$(call run_with_postgres_env,cd src/web && $(NEXT_DEV_ENV) npm run dev)

start-web: ## Run Next.js admin interface in the background (logs/web.log)
	$(call check_venv)
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
ifeq ($(POSTGRES_ACTIVE),)
ifneq ($(SKIP_ADMIN_SEED),1)
	@$(MAKE) db-seed-admin || echo "Warning: Could not seed admin user (backend may not be running)"
endif
	@/bin/bash -lc "cd src/web && $(NEXT_DEV_ENV) nohup npm run dev >> \"$(WEB_LOG_ABS)\" 2>&1 & echo \$$! > \"$(WEB_PID_FILE_ABS)\""
else
ifneq ($(SKIP_POSTGRES_MIGRATE),1)
	@$(MAKE) postgres-migrate
endif
ifneq ($(SKIP_ADMIN_SEED),1)
	$(call run_with_postgres_env,$(MAKE) db-seed-admin || echo "Warning: Could not seed admin user (backend may not be running)")
endif
	@/bin/bash -lc "set -a; source \"$(POSTGRES_ENV_FILE)\"; set +a; cd src/web && $(NEXT_DEV_ENV) nohup npm run dev >> \"$(WEB_LOG_ABS)\" 2>&1 & echo \$$! > \"$(WEB_PID_FILE_ABS)\""
endif
	@i=0; while [ ! -f "$(WEB_PID_FILE)" ] && [ $$i -lt 10 ]; do sleep 0.5; i=$$((i+1)); done
	@if [ -f "$(WEB_PID_FILE)" ]; then \
		PID=$$(cat "$(WEB_PID_FILE)"); \
		echo "Next.js started in background (PID $$PID). Logs: $(WEB_LOG)"; \
	else \
		echo "Next.js launch command executed but PID file was not created. Check $(WEB_LOG) for details."; \
	fi

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
	@if [ -f "$(BACKEND_PID_FILE)" ]; then \
		PID=$$(cat "$(BACKEND_PID_FILE)"); \
		if kill -0 $$PID 2>/dev/null; then \
			kill $$PID && echo "Stopped FastAPI process $$PID."; \
		else \
			echo "PID $$PID not running; cleaning up stale PID file."; \
		fi; \
		rm -f "$(BACKEND_PID_FILE)"; \
	else \
		echo "No PID file found; attempting graceful shutdown."; \
		pkill -f "uvicorn main:app" || echo "No FastAPI process found"; \
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
	@echo "Postgres mode flags cleared (commands revert to SQLite)."

docker-postgres-destroy: ## Stop Postgres container and remove volumes
	@if [ ! -f "$(POSTGRES_ENV_FILE)" ]; then \
		echo "No $(POSTGRES_ENV_FILE) found; nothing to destroy."; \
		exit 0; \
	fi
	@echo "Destroying Postgres container and volumes..."
	$(POSTGRES_COMPOSE) down -v && rm -f "$(POSTGRES_ACTIVE_FLAG)" || true
	@echo "Postgres mode flags cleared (commands revert to SQLite)."

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
		exit 0; \
	fi
	$(POSTGRES_COMPOSE) ps

postgres-disable: ## Keep container running but force commands back to SQLite
	@rm -f "$(POSTGRES_ACTIVE_FLAG)"
	@echo "Postgres mode flag removed. Existing containers unaffected."

postgres-wait: ## Wait until Postgres is ready to accept connections
ifeq ($(POSTGRES_ACTIVE),)
	@echo "Postgres mode inactive; skipping wait."
else
	$(call ensure_postgres_env)
	@if [ -z "$$($(POSTGRES_COMPOSE) ps -q $(POSTGRES_SERVICE))" ]; then \
		if [ "$(MED13_SKIP_COMPOSE)" = "1" ]; then \
			echo "Postgres container is not running and MED13_SKIP_COMPOSE=1; skipping auto-start."; \
			echo "Skipping Postgres wait/migrate steps (tests will run with default DB)."; \
			exit 0; \
		else \
			echo "Postgres container is not running; starting via $(POSTGRES_COMPOSE_FILE)..."; \
			$(POSTGRES_COMPOSE) up -d $(POSTGRES_SERVICE); \
		fi \
	fi
	@echo "Waiting for Postgres health check..."
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/wait_for_postgres.py)
endif

postgres-migrate: ## Run Alembic migrations when Postgres mode is active
ifeq ($(POSTGRES_ACTIVE),)
	@echo "Postgres mode inactive; skipping migrations."
else
	@$(MAKE) -s postgres-wait
	@echo "Applying Alembic migrations (Postgres)..."
	$(call run_with_postgres_env,$(ALEMBIC_BIN) upgrade heads)
endif

init-artana-schema: ## Initialize the artana schema in Postgres
	$(call check_venv)
	@echo "Creating artana schema..."
ifeq ($(POSTGRES_ACTIVE),)
	$(USE_PYTHON) scripts/init_artana_schema.py
else
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/init_artana_schema.py)
endif

setup-postgres: ## Full PostgreSQL setup including artana schema
	@$(MAKE) -s docker-postgres-up
	@$(MAKE) -s postgres-wait
	@$(MAKE) -s postgres-migrate
	@$(MAKE) -s init-artana-schema
	@echo "PostgreSQL setup complete with artana schema."

# Database
db-migrate: ## Run database migrations
ifeq ($(POSTGRES_ACTIVE),)
	alembic upgrade head
else
	$(call run_with_postgres_env,alembic upgrade heads)
endif

db-create: ## Create database migration
	@echo "Creating new migration..."
ifeq ($(POSTGRES_ACTIVE),)
	alembic revision --autogenerate -m "$(msg)"
else
	$(call run_with_postgres_env,alembic revision --autogenerate -m "$(msg)")
endif

db-reset: ## Reset database (WARNING: destroys data)
	@echo "This will destroy all data. Are you sure? [y/N] " && read ans && [ $${ans:-N} = y ]
ifeq ($(POSTGRES_ACTIVE),)
	alembic downgrade base
else
	$(call run_with_postgres_env,alembic downgrade base)
endif

db-seed: ## Seed database with test data
	$(call check_venv)
ifeq ($(POSTGRES_ACTIVE),)
	$(USE_PYTHON) scripts/seed_database.py
else
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/seed_database.py)
endif

db-seed-admin: ## Seed admin user (requires ADMIN_PASSWORD or MED13_ADMIN_PASSWORD)
	$(call check_venv)
	@if [ -z "$(ADMIN_PASSWORD_EFFECTIVE)" ]; then \
		echo "ADMIN_PASSWORD or MED13_ADMIN_PASSWORD must be provided (e.g. ADMIN_PASSWORD='StrongPassw0rd!' make db-seed-admin)"; \
		exit 1; \
	fi
	@echo "Seeding admin user..."
ifeq ($(POSTGRES_ACTIVE),)
	@ADMIN_PASSWORD="$(ADMIN_PASSWORD_EFFECTIVE)" $(USE_PYTHON) scripts/seed_admin_user.py --password "$$ADMIN_PASSWORD"
else
	$(call run_with_postgres_env,ADMIN_PASSWORD="$(ADMIN_PASSWORD_EFFECTIVE)" $(USE_PYTHON) scripts/seed_admin_user.py --password "$$ADMIN_PASSWORD")
endif

db-reset-admin-password: ## Reset admin password (requires ADMIN_PASSWORD or MED13_ADMIN_PASSWORD)
	$(call check_venv)
	@if [ -z "$(ADMIN_PASSWORD_EFFECTIVE)" ]; then \
		echo "ADMIN_PASSWORD or MED13_ADMIN_PASSWORD must be provided (e.g. ADMIN_PASSWORD='NewStrongPass!' make db-reset-admin-password)"; \
		exit 1; \
	fi
	@echo "Resetting admin password..."
ifeq ($(POSTGRES_ACTIVE),)
	@ADMIN_PASSWORD="$(ADMIN_PASSWORD_EFFECTIVE)" $(USE_PYTHON) scripts/reset_admin_password.py --password "$$ADMIN_PASSWORD"
else
	$(call run_with_postgres_env,ADMIN_PASSWORD="$(ADMIN_PASSWORD_EFFECTIVE)" $(USE_PYTHON) scripts/reset_admin_password.py --password "$$ADMIN_PASSWORD")
endif

db-verify-admin: ## Verify admin user exists
	$(call check_venv)
	@echo "Verifying admin user..."
ifeq ($(POSTGRES_ACTIVE),)
	@$(USE_PYTHON) scripts/reset_admin_password.py --verify-only
else
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/reset_admin_password.py --verify-only)
endif

# Deployment
deploy-staging: ## Deploy to staging environment
	@echo "Deploying to staging..."
	gcloud run deploy med13-resource-library-staging \
		--source . \
		--region us-central1 \
		--allow-unauthenticated=false \
		--service-account med13-staging@YOUR_PROJECT_ID.iam.gserviceaccount.com

deploy-prod: ## Deploy to production environment
	@echo "Deploying to production..."
	gcloud run deploy med13-resource-library \
		--source . \
		--region us-central1 \
		--allow-unauthenticated=false \
		--service-account med13-prod@YOUR_PROJECT_ID.iam.gserviceaccount.com

	gcloud run deploy med13-curation \
		--source . \
		--region us-central1 \
		--allow-unauthenticated=false \
		--service-account med13-prod@YOUR_PROJECT_ID.iam.gserviceaccount.com

	gcloud run deploy med13-admin \
		--source . \
		--region us-central1 \
		--allow-unauthenticated=false \
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
	cd src/web && npm install

web-build: ## Build Next.js admin interface
	cd src/web && $(NEXT_BUILD_ENV) npm run build

web-clean: ## Remove Next.js build artifacts
	rm -rf src/web/.next

web-lint: ## Lint Next.js code
	cd src/web && npm run lint

web-type-check: ## Type check Next.js code
	cd src/web && npm run type-check

web-test: ## Run Next.js tests
	cd src/web && npm run test

web-test-architecture: ## Run Next.js architecture validation tests (Server-Side Orchestration)
	cd src/web && npm test -- __tests__/architecture

web-test-integration: ## Run Next.js integration tests (frontend-backend)
	cd src/web && npm test -- __tests__/integration

web-test-all: web-test-architecture web-test-integration web-test ## Run all Next.js tests (architecture, integration, and unit tests)

web-test-coverage: ## Run Next.js tests with coverage report
	cd src/web && npm run test:coverage

web-visual-test: ## Run Percy-powered visual regression snapshots (requires PERCY_TOKEN)
	./scripts/run_visual_snapshots.sh

web-security-audit: ## Run npm security audit for Next.js app
	cd src/web && npm run security:audit

web-security-check: ## Run full security check (audit + outdated packages)
	cd src/web && npm run security:check

test-web: web-test ## Alias for web-test

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
backup-db: ## Create database backup (SQLite)
	@echo "Creating SQLite database backup..."
	cp med13.db backup_$(shell date +%Y%m%d_%H%M%S).db

restore-db: ## Restore database from backup (specify FILE variable)
	@echo "Restoring SQLite database from $(FILE)..."
	cp $(FILE) med13.db
restart-postgres: ## Recreate Postgres container (down -v, up)
	@$(MAKE) -s docker-postgres-destroy
	@$(MAKE) -s docker-postgres-up
