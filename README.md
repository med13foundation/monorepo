# MED13 Resource Library 🏥

A comprehensive biomedical data platform for MED13 genetic variants, phenotypes, and evidence. Features a **three-service architecture** with a FastAPI backend, a Next.js admin interface, and a public front door website. Built for Google Cloud Run deployment with enterprise-grade quality assurance.

## 📋 Overview

A **three-service architecture** biomedical data platform featuring Clean Architecture principles, type safety, and modern Next.js interfaces. The Dash curation client has been retired in favor of the unified Next.js experience.

### 🏗️ Architecture

```
MED13 Resource Library
├── FastAPI Backend (med13-api)         # REST API & business logic
├── Next.js Admin (med13-admin)         # Authenticated admin dashboard
└── Next.js Front Door (med13-frontdoor) # Public website and onboarding
```

### 🎯 Key Features
- **Three-Service Architecture**: Independent scaling of public site, admin UI, and API services
- **Clean Architecture**: Domain-driven design with clear separation of concerns
- **Type Safety**: 100% MyPy compliance with shared TypeScript types
- **Modern Admin UI**: Next.js 14 with Tailwind CSS and shadcn/ui components
- **Template Catalog**: Fully typed `/admin/templates` endpoints for managing reusable data source templates
- **Comprehensive APIs**: REST endpoints with OpenAPI documentation
- **FAIR Compliance**: Findable, Accessible, Interoperable, Reusable data
- **Cloud-Native**: Multi-service Google Cloud Run deployment
- **Quality Assurance**: Enterprise-grade linting, testing, and security scanning

### Documentation and roadmap
- The current graph implementation path is Postgres-backed with NetworkX traversal. TypeDB is an optional future migration.
- Start with `docs/README.md` for the canonical documentation order and status.
- Front door product requirements and implementation scope: `docs/frontend/frontdoor_website_prd.md`.

## 🚀 How To Work (Local, Dev, Prod)

This project has three working environments:

- **Local**: your laptop with Dockerized Postgres + Redis.
- **Dev**: shared cloud staging environment on Google Cloud Run.
- **Prod**: production Google Cloud Run services.

### 1) Local (daily development)

Use Local for coding, debugging, and running tests quickly.

**Prerequisites**
- Python 3.13+
- Node.js 18+
- Docker Desktop (or Docker Engine + Compose)

**One-time setup**
```bash
git clone <repository-url>
cd med13-resource-library
make setup-dev
make web-install
cp .env.postgres.example .env.postgres
```

Set a local admin password in `.env.postgres`:
```bash
MED13_ADMIN_PASSWORD=<your-strong-local-password>
```

**Start local stack**
```bash
make dev-postgres
```

This starts/reuses Docker Postgres + Redis, runs migrations, initializes Artana schema, seeds admin, then starts backend + Next.js.

**Local URLs**
- API docs: http://localhost:8080/docs
- Admin UI: http://localhost:3000/dashboard

**Stop / reset local**
```bash
make stop-all           # stop backend + web + Docker services
make run-all-postgres   # full reset (wipes Postgres volume, then rebuilds)
```

**Run tests locally**
```bash
make test
make web-test-all
```

### 2) Dev (shared staging in GCP)

Use Dev to validate integration before production.

**Before deploy**
```bash
make all
```

**Deploy to staging**
```bash
make deploy-staging
```

**Check runtime health**
```bash
make cloud-logs
```

### 3) Prod (live environment)

Use Prod only after staging is healthy.

**Pre-checks**
- Latest code merged to the release branch.
- `make all` passed.
- Staging deploy and smoke checks passed.
- Required secrets exist in GCP Secret Manager.

**Deploy to production**
```bash
make deploy-prod
```

**Post-deploy checks**
- Open API health/docs URL and key admin pages.
- Verify Cloud Run logs for errors.

### Security-sensitive environment variables

Set these in staging/prod (prefer Secret Manager):

- `ADMIN_API_KEY`, `WRITE_API_KEY`, `READ_API_KEY`
- `MED13_RATE_LIMIT_REDIS_URL`
- `MED13_ENV=staging` or `MED13_ENV=production`
- `DATABASE_URL` and `ASYNC_DATABASE_URL` (Postgres with TLS)
- `MED13_ENABLE_ENTITY_EMBEDDINGS=0|1` (keep `0` until embeddings are refreshed)
- `MED13_ENABLE_RELATION_SUGGESTIONS=0|1` (keep `0` until similarity is validated)

For local only, `MED13_ALLOW_MISSING_API_KEYS=1` may be used during development.

## 📁 Project Structure

```
med13-resource-library/
├── src/                          # Backend source code
│   ├── main.py                  # FastAPI application entry point
│   ├── database/                # Database configuration
│   ├── models/                  # SQLAlchemy database models
│   ├── routes/                  # API endpoints (including /admin/*)
│   ├── domain/                  # Business logic & entities
│   ├── application/             # Use cases & services
│   ├── infrastructure/          # External adapters & repositories
│   ├── presentation/            # Reserved for future UI adapters
│   └── shared/                 # Shared types between services
│       └── types/              # TypeScript type definitions
├── src/web/                     # Next.js admin interface
│   ├── app/                    # Next.js app router pages
│   ├── components/             # React components & UI
│   ├── lib/                    # Utilities and configurations
│   ├── types/                  # Frontend type definitions
│   ├── package.json            # Node.js dependencies
│   └── tailwind.config.ts      # Tailwind CSS configuration
├── apps/frontdoor/              # Next.js public front door website
│   ├── app/                    # Public routes and API handlers
│   ├── components/             # Marketing/onboarding components
│   ├── lib/                    # SEO, analytics, validation helpers
│   ├── tests/                  # Front door unit tests
│   └── Dockerfile              # Independent container build
├── tests/                      # Backend test suite
├── docs/                       # Documentation
├── .github/workflows/          # CI/CD pipelines
├── pyproject.toml              # Python dependencies and tool configuration
├── Makefile                   # Development automation
├── Procfile                   # Cloud Run configuration
└── pytest.ini                 # Test configuration
```

## 🛠️ Development Workflow

### Available Commands

```bash
# Quality Assurance (Multi-Service)
make all               # Complete quality suite: Python + Next.js (recommended)

# Environment Management
make venv              # Create Python virtual environment
make activate          # Show activation command
make check-env         # Check environment status

# Setup & Installation
make install           # Install Python production dependencies
make install-dev       # Install Python development dependencies
make setup-dev         # Complete Python development setup
make web-install       # Install Next.js dependencies
make frontdoor-install # Install front door dependencies

# Development Servers
make run-local         # Start FastAPI backend (port 8080)
make run-web           # Start Next.js admin interface (port 3000)
make frontdoor-dev     # Start public front door (default: port 3010)

# Code Quality
make lint              # Python linting (flake8, ruff, mypy, bandit)
make format            # Python auto-format (Black + Ruff)
make type-check        # Python type checking with mypy
make web-lint          # Next.js linting
make web-type-check    # Next.js type checking

# Testing
make test              # Python tests
make test-cov          # Python tests with coverage
make test-verbose      # Python tests with verbose output
make web-test          # Next.js tests
make frontdoor-test    # Front door tests

# Building
make web-build         # Build Next.js for production
make frontdoor-build   # Build front door for production

# Database
make db-migrate        # Run database migrations
make db-create         # Create new migration
make db-reset          # Reset database (WARNING!)
make db-seed           # Seed with test data
make backup-db         # Backup Postgres database via pg_dump
make restore-db        # Restore from backup

# Security
make security-audit    # Run security scans

# CI/CD
make ci                # Run full Python CI pipeline locally

# Cloud Operations
make cloud-logs        # View Cloud Run logs
make cloud-secrets-list # List GCP secrets

# Documentation
make docs-serve        # Serve docs locally
```

## 🗄️ Database

### Local Development
- **Database**: Dockerized PostgreSQL (`pgvector/pg16`)
- **Cache/Rate Limit**: Dockerized Redis (`redis:7-alpine`)
- **ORM**: SQLAlchemy 2.0 with Alembic migrations
- **Setup**: `make dev-postgres`

### Production
- **Database**: PostgreSQL
- **Backup**: `pg_dump`/managed backups
- **Migration**: Alembic schema versioning

### Data Sources
- **ClinVar/ClinGen**: Variant interpretations and curation status
- **HPO**: Human Phenotype Ontology terms and hierarchies
- **PubMed/LitVar**: Literature references and variant links
- **OMIM/Orphanet**: Gene-disease associations
- **UniProt/GTEx**: Functional and expression metadata

## 🧪 Testing

### Backend Testing (Python)
```bash
# Run all Python tests
make test

# Run with coverage
make test-cov

# Run specific tests
pytest tests/test_health.py -v

# Watch mode for development
make test-watch

# Verbose output
make test-verbose
```

### Frontend Testing (Next.js)
```bash
# Run Next.js tests
make web-test

# Run with coverage
cd src/web && npm run test:coverage

# Watch mode for development
cd src/web && npm run test:watch
```

### Integration Testing
```bash
# Test API endpoints
curl -X GET "http://localhost:8080/admin/data-sources"
curl -X GET "http://localhost:8080/admin/stats"

# Test frontend connectivity
# Open http://localhost:3000/dashboard
# Verify data loads from API
```

### Quality Assurance Pipeline
```bash
# Run complete multi-service quality suite
make all

# This includes:
# - Python: format, lint, type-check, test, security
# - Next.js: build, lint, type-check, test
# - Integration: cross-service compatibility
```

## 🚀 Deployment

Deployments target Google Cloud Run with two services:

- `med13-api` (FastAPI backend)
- `med13-admin` (Next.js admin)

### Dev (staging) deployment
```bash
make all
make deploy-staging
make cloud-logs
```

### Prod deployment
```bash
make all
make deploy-prod
make cloud-logs
```

Note: always deploy to staging first, run smoke checks, then deploy to production.

### CI Runtime Config Sync
The deploy workflow now applies runtime Cloud Run configuration after source deploy
using `scripts/deploy/sync_cloud_run_runtime_config.sh`.

Configure GitHub **Environment Variables** per environment suffix
(`DEV`, `STAGING`, `PROD`) as needed:

- `CLOUDSQL_CONNECTION_NAME_<ENV>`
- `DATABASE_URL_SECRET_NAME_<ENV>`
- `MED13_DEV_JWT_SECRET_NAME_<ENV>`
- `ADMIN_API_KEY_SECRET_NAME_<ENV>`
- `WRITE_API_KEY_SECRET_NAME_<ENV>`
- `READ_API_KEY_SECRET_NAME_<ENV>`
- `NEXTAUTH_SECRET_SECRET_NAME_<ENV>`
- `MED13_ALLOWED_ORIGINS_<ENV>`
- `API_MIN_INSTANCES_<ENV>`
- `ADMIN_MIN_INSTANCES_<ENV>`
- `API_PUBLIC_<ENV>` (`true`/`false`)
- `ADMIN_PUBLIC_<ENV>` (`true`/`false`)
- `MIGRATION_JOB_NAME_<ENV>`
- `SYNC_ADMIN_URLS_<ENV>` (`true`/`false`, defaults to disabled)

Secrets referenced above must exist in Google Secret Manager in the target GCP
project, and the deploying service account must have access.

## 🔒 Security & Quality

### Multi-Service Quality Gates
- **Python Backend**:
  - Linting: Flake8, Ruff (import sorting, formatting)
  - Type Checking: MyPy with strict settings
  - Formatting: Black code formatter
  - Security: Bandit security linter
- **Next.js Frontend**:
  - Linting: ESLint with Next.js config
  - Type Checking: TypeScript strict mode
  - Formatting: Prettier
  - Testing: Jest + React Testing Library

### Dependency Security
- **Python**: Safety and pip-audit automated scanning
- **Node.js**: npm audit and dependency checks
- **Vulnerability Checks**: CI/CD pipeline for both ecosystems
- **License Compliance**: All biomedical data sources verified
- **Container Scanning**: Every CI run builds the FastAPI image and scans it with Trivy before deployments
- **Schema Fuzzing**: Schemathesis-based smoke tests (`pytest tests/security/test_schemathesis_contracts.py`) ensure OpenAPI endpoints stay within contract without leaking 5xx responses

### Type Safety
- **100% MyPy Compliance**: Strict typing across Python codebase
- **Shared Type Definitions**: TypeScript types synced between services
- **Runtime Validation**: Pydantic models ensure data integrity

### Audit Logging & Access Controls
- **JWT-first curation pipeline**: Curation routes reject API-key-only requests and require JWT-authenticated users with explicit permissions.
- **Per-user Data Discovery isolation**: Repository filters ensure sessions can only be read or mutated by their owners (admins may opt-in to override).
- **Append-only audit trail**: High-risk curation and data-discovery actions emit structured entries into `audit_logs`, providing tamper-resistant traceability.

## 📚 Documentation

### Core Documentation
- **`docs/goal.md`**: Project objectives and biomedical data model
- **`docs/infra.md`**: Multi-service infrastructure and deployment guide
- **`docs/node_js_migration_prd.md`**: Next.js admin interface migration plan
- **`docs/admin_area.md`**: Research Spaces Management System PRD
- **`AGENTS.md`**: AI agent development guidelines and architecture
- **`docs/EngineeringArchitecture.md`**: Current state and growth strategy

### API Documentation
- **OpenAPI/Swagger**: http://localhost:8080/docs (when running)
- **Alternative Docs**: http://localhost:8080/redoc
- **Admin API**: `/admin/*` endpoints for data source management
- **Research Spaces API**: `docs/research-spaces-api.md` - Complete API reference for research spaces endpoints
- **Research Spaces Components**: `docs/research-spaces-components.md` - React component documentation

### Development Guides
- **`docs/type_examples.md`**: Type safety patterns and examples
- **`docs/curator.md`**: Researcher curation workflows
- **Makefile**: Comprehensive development automation reference

## 🤝 Contributing

### Development Workflow
1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/your-feature`)
3. **Set up** multi-service environment:
   ```bash
   make setup-dev      # Python environment
   make web-install    # Next.js dependencies
   ```
4. **Develop** following established patterns
5. **Test** all services: `make all` (Python + Next.js quality gates)
6. **Submit** a pull request

### Development Standards

#### Python Backend
- **Code Style**: Black formatting, Ruff linting
- **Type Safety**: 100% MyPy compliance with strict settings
- **Testing**: Comprehensive pytest suite
- **Architecture**: Clean Architecture with domain-driven design

#### Next.js Frontend
- **Code Style**: ESLint, Prettier formatting
- **Type Safety**: TypeScript strict mode
- **Testing**: Jest + React Testing Library
- **UI/UX**: shadcn/ui components, Tailwind CSS

#### Multi-Service Requirements
- **Shared Types**: Consistent TypeScript types across services
- **API Contracts**: OpenAPI specification compliance
- **Integration Tests**: Cross-service compatibility verification
- **Documentation**: Clear docstrings, type hints, and API docs

## 📄 License

This project uses data from multiple biomedical sources. Refer to `docs/goal.md` for detailed licensing information and attribution requirements.

## 🆘 Support

- **Issues**: GitHub Issues for bugs and feature requests
- **Documentation**: See `docs/` directory for detailed guides
- **CI/CD**: Automated pipelines provide immediate feedback

---

## 🧱 Template Catalog

### API

Manage reusable data source templates directly from the admin interface:

```
GET    /admin/templates            # List templates (available/public/mine)
GET    /admin/templates/{id}       # Fetch template details
POST   /admin/templates            # Create a template
PUT    /admin/templates/{id}       # Update template metadata/schema
DELETE /admin/templates/{id}       # Delete a template
```

All endpoints return strongly typed payloads backed by the shared `TemplateResponse` model, with matching helpers in `src/web/lib/api/templates.ts` and `src/web/hooks/use-templates.ts`.

### UI

The Next.js admin dashboard now includes a dedicated `/templates` workspace featuring:

- Scope tabs (`available`, `public`, `mine`) with paginated cards
- In-place create/edit dialogs for schema updates and metadata
- Detail views (`/templates/{id}`) with schema inspection and destructive-action confirmations

These components reuse the same typed hooks, so backend/API updates stay in sync with the UI.
