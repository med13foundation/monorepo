# MED13 Resource Library - Infrastructure Guide

## Overview

This document outlines the infrastructure for the MED13 Resource Library, a sophisticated biomedical data platform implementing Clean Architecture with multiple microservices deployed on Google Cloud Platform. The system provides both REST APIs and modern web interfaces for managing MED13 genetic variants, phenotypes, evidence, and data sources.

## Architecture Decisions

### Multi-Service Microarchitecture
**Decision**: Independent Cloud Run services for each major component
**Rationale**:
- **Scalability**: Each service scales independently based on load patterns
- **Fault Isolation**: One service failure doesn't cascade to others
- **Technology Flexibility**: Different services can use different tech stacks
- **Deployment Independence**: Deploy services without affecting others
- **Resource Optimization**: Pay only for what each service actually uses

**Current Services**:
- `med13-api`: FastAPI backend (REST APIs, business logic)
- `med13-curation` (retired): Legacy Dash researcher interface
- `med13-admin`: Next.js admin interface (planned)

### Clean Architecture Implementation
**Decision**: Domain-Driven Design with strict layer separation
**Rationale**:
- **Testability**: Each layer can be tested in isolation
- **Maintainability**: Changes in one layer don't affect others
- **Flexibility**: Easy to swap implementations (database, UI frameworks)
- **Type Safety**: 100% MyPy compliance prevents runtime errors
- **Healthcare Critical**: Zero-defect tolerance for medical data

**Layer Structure**:
```
Presentation Layer: FastAPI routes + Next.js UI (Dash UI retired; references retained for history)
Application Layer: Use cases, service orchestration
Domain Layer: Business entities, rules, invariants
Infrastructure Layer: Database, external APIs, frameworks
```

### Database: PostgreSQL with Production Configuration
**Decision**: PostgreSQL for production with proper connection pooling and monitoring
**Rationale**:
- **Scalability**: Handles concurrent connections and complex queries
- **Data Integrity**: Advanced constraints and transaction support
- **Performance**: Indexing, query optimization, and caching capabilities
- **Monitoring**: Built-in performance metrics and health checks
- **Ecosystem**: Rich tooling and community support for biomedical data

**Migration Path**: Currently using SQLite for development, PostgreSQL ready for production

### CI/CD Pipeline: GitHub Actions with Quality Gates
**Decision**: Comprehensive automated pipeline with multiple quality checks
**Rationale**:
- **Quality Assurance**: Automated linting, type checking, testing, security scanning
- **Consistency**: Same checks run locally and in CI
- **Fast Feedback**: Failures caught before production deployment
- **Healthcare Standards**: Zero-defect pipeline for medical software

### Secrets Management: Google Cloud Secret Manager
**Decision**: Enterprise-grade secrets management with audit trails
**Rationale**:
- **Security**: Encrypted storage with access logging
- **Compliance**: HIPAA-ready with proper access controls
- **Auditability**: Complete audit trail for healthcare data access
- **Integration**: Native Cloud Run service account support
- **Cost-Effective**: $0.06/secret/month with versioning

## Infrastructure Components

### Multi-Service Application Stack

#### FastAPI Backend Service (`med13-api`)
- **Runtime**: Python 3.12+ with Clean Architecture
- **Framework**: FastAPI with automatic OpenAPI documentation
- **Architecture**: Domain-Driven Design with strict layer separation
- **Database**: PostgreSQL (production) / SQLite (development)
- **Deployment**: Cloud Run with independent scaling
- **Features**: REST APIs, business logic, data validation, authentication

#### Legacy Dash Researcher Interface (`med13-curation`) – Retired
- **Runtime**: (Retired) Python 3.12+ with Dash framework
- **UI Framework**: Plotly Dash with Bootstrap components
- **Purpose**: Researcher curation workflows and data visualization
- **Integration**: Consumes FastAPI backend APIs
- **Deployment**: Independent Cloud Run service
- **Scaling**: Optimized for research user patterns

#### Next.js Admin Interface (`med13-admin`) - Planned
- **Runtime**: Node.js 18+ with Next.js 14
- **Framework**: React 18 with TypeScript
- **UI Library**: Tailwind CSS + shadcn/ui components
- **Purpose**: Administrative data source management
- **Integration**: REST APIs + real-time WebSocket updates
- **Deployment**: Independent Cloud Run service

### Shared Infrastructure Services

#### Database Layer
- **Production**: PostgreSQL with connection pooling and monitoring
- **Development**: SQLite for simplified local development
- **Migration**: Alembic for schema versioning and deployments
- **Backup**: Automated PostgreSQL backups with point-in-time recovery
- **Monitoring**: Query performance, connection pooling metrics

#### Google Cloud Services
- **Cloud Run**: Multi-service serverless container platform
- **Secret Manager**: Enterprise secrets management with audit trails
- **Cloud Storage**: Data exports, backups, and long-term archives
- **Cloud SQL**: Managed PostgreSQL with high availability
- **Cloud Load Balancing**: Global load distribution across services
- **Cloud Monitoring**: Comprehensive observability and alerting

## Repository Structure

**Monorepo Architecture with Clean Architecture Organization**

```
med13-resource-library/
├── src/                          # Shared Python backend (Clean Architecture)
│   ├── domain/                  # Business logic layer
│   │   ├── entities/           # Pydantic domain models
│   │   ├── repositories/       # Repository interfaces
│   │   └── services/           # Domain services
│   ├── application/            # Use case orchestration
│   │   └── services/           # Application services
│   ├── infrastructure/         # External concerns
│   │   ├── repositories/       # SQLAlchemy implementations
│   │   ├── mappers/           # Data transformation
│   │   └── validation/        # External API validation
│   ├── presentation/           # UI implementations
│   │   ├── dash/              # Researcher interface
│   │   └── web/               # Next.js admin (planned)
│   ├── routes/                 # FastAPI route definitions
│   ├── main.py                 # FastAPI application entry point
│
├── docs/                        # Documentation
│   ├── infra.md                # Infrastructure guide (this file)
│   ├── type_examples.md        # Type safety patterns
│   └── EngineeringArchitecturePlan.md # Architecture roadmap
│
├── tests/                       # Comprehensive test suite
│   ├── unit/                   # Unit tests by layer
│   ├── integration/           # Service integration tests
│   ├── e2e/                   # End-to-end workflow tests
│   └── fixtures/              # Test data and utilities
│
├── .github/                     # CI/CD and automation
│   └── workflows/              # GitHub Actions pipelines
│
├── scripts/                     # Utility and maintenance scripts
├── alembic/                     # Database migrations
├── Dockerfile                   # Multi-service container definitions
├── Makefile                     # Development workflow automation
├── pyproject.toml              # Python project/dependency configuration
└── Procfile                     # Cloud Run deployment configurations
```

## Local Development Setup

### Dockerfile
Maintain a working Dockerfile for local development and future containerization:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY . .
RUN pip install .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### CORS Configuration
Configure CORS in FastAPI for frontend integration:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://med13foundation.org",
        "https://curate.med13foundation.org",
        "http://localhost:3000",  # For local development
        "http://localhost:8080"   # For local development
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    allow_credentials=True,
)

### Makefile Development Workflow

**Comprehensive automation for our multi-service architecture:**

```bash
# Environment setup
make setup-dev          # Python 3.12 venv + dependencies
make activate           # Activate virtual environment

# Multi-service development
make run-local          # FastAPI backend (port 8080)
# Future: make run-web  # Next.js admin UI (port 3000)

# Quality assurance (Clean Architecture focus)
make all                # Complete quality gate
make format            # Black + Ruff formatting
make lint              # Code quality checks
make type-check        # MyPy strict validation
make test              # Pytest with coverage
make test-cov          # Coverage reporting

# Database operations (PostgreSQL/SQLite)
make db-create         # Create development database
make db-migrate        # Run Alembic migrations
alembic revision --autogenerate -m "Add new feature"

# Deployment (multi-service)
make deploy-staging    # Deploy all services to staging
make deploy-prod       # Deploy all services to production

# Maintenance
make backup-db         # Database backup
make clean             # Remove temporary files
```

## Code Quality & Type Safety

### Robust Tooling Stack

The project implements a comprehensive quality assurance pipeline with multiple layers of validation:

#### **Type Safety & Validation**
- **Pydantic v2**: Data validation with strict typing and JSON schema generation
- **MyPy**: Static type checking with strict settings (--strict, --show-error-codes)
- **Type Hints**: Comprehensive type annotations throughout the codebase

#### **Code Quality Tools**
- **Black**: Code formatting with 88-character line length
- **Ruff**: Fast Python linter and import sorter (replaces flake8 + isort)
- **Flake8**: Additional style and error checking
- **Pre-commit Hooks**: Automated quality checks before commits

#### **Security Scanning**
- **Bandit**: Security vulnerability scanner for Python code
- **Safety**: Dependency vulnerability checker
- **Pip-audit**: Comprehensive package vulnerability assessment

#### **Testing & Coverage**
- **Pytest**: Comprehensive test framework with async support
- **Coverage.py**: Code coverage reporting (>90% target)
- **Pytest-xdist**: Parallel test execution
- **Pytest-watch**: Auto-run tests during development

### Type Safety Implementation

#### **Pydantic Models**
```python
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime

class Gene(BaseModel):
    gene_id: str = Field(..., min_length=1, max_length=50)
    symbol: str = Field(..., pattern=r'^[A-Z0-9]+$')
    name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @validator('symbol')
    def validate_symbol(cls, v):
        return v.upper()

class Variant(BaseModel):
    variant_id: str
    gene_id: str
    hgvs: str
    clinvar_id: Optional[str] = None
    phenotypes: List[Phenotype] = Field(default_factory=list)
```

#### **FastAPI with Type Hints**
```python
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Annotated

app = FastAPI(title="MED13 Resource Library", version="0.1.0")

@app.get("/api/variants/", response_model=List[VariantResponse])
async def get_variants(
    skip: int = 0,
    limit: int = 100,
    gene_symbol: Optional[str] = None,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[VariantResponse]:
    """Get variants with optional filtering."""
    # Implementation with full type safety
    pass

@app.post("/api/variants/", response_model=VariantResponse, status_code=201)
async def create_variant(
    variant: VariantCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
) -> VariantResponse:
    """Create a new variant with validation."""
    # Full type safety and validation
    pass
```

### Quality Assurance Pipeline

#### **Pre-commit Configuration**
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files

  - repo: https://github.com/psf/black
    rev: 23.12.1
    hooks:
      - id: black

  - repo: https://github.com/charliermarsh/ruff-pre-commit
    rev: v0.1.14
    hooks:
      - id: ruff
        args: [--fix]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.1
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
```

## CI/CD Pipeline

### Multi-Service Deployment Strategy

**Independent deployment of each service with shared quality gates:**

```yaml
# .github/workflows/deploy.yml
name: Deploy MED13 Services

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  REGION: us-central1
  PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}

jobs:
  # Shared quality gate for all services
  quality-gate:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'

    - name: Install dependencies
      run: |
        pip install -e ".[dev]"

    - name: Run quality checks
      run: make all

    - name: Upload test results
      uses: actions/upload-artifact@v4
      with:
        name: test-results
        path: test-results.xml

  # Deploy FastAPI backend
  deploy-api:
    needs: quality-gate
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
    - uses: actions/checkout@v4
    - name: Deploy to Cloud Run
      uses: google-github-actions/deploy-cloudrun@v2
      with:
        service: med13-api
        source: .
        env-vars-file: .env.production
        region: ${{ env.REGION }}

  # Future: Deploy Next.js admin UI
  # deploy-admin:
  #   needs: quality-gate
  #   runs-on: ubuntu-latest
  #   if: github.ref == 'refs/heads/main'
  #   steps:
  #   - uses: actions/checkout@v4
  #   - name: Set up Node.js
  #     uses: actions/setup-node@v4
  #     with:
  #       node-version: '18'
  #   - name: Build Next.js
  #     run: |
  #       cd src/web
  #       npm ci
  #       npm run build
  #   - name: Deploy Next.js Admin
  #     uses: google-github-actions/deploy-cloudrun@v2
  #     with:
  #       service: med13-admin
  #       source: src/web/.next
  #       region: ${{ env.REGION }}
```

### Multi-Service Deployment Configuration

#### Procfile Configurations (Per Service)

**FastAPI Backend (`Procfile.api`):**
```
web: uvicorn src.main:create_app --host 0.0.0.0 --port $PORT --factory
```

**Legacy Dash Researcher UI (`Procfile.dash`, retired):**
```
# (Removed) web: python src/dash_app.py
```

**Next.js Admin UI (`Procfile.admin`):**
```
web: npm start
```

#### Environment Configuration

**Development (`.env.development`):**
```bash
DATABASE_URL=sqlite:///med13.db
API_BASE_URL=http://localhost:8080
SECRET_KEY=dev-secret-key
DEBUG=True
```

**Production (`.env.production`):**
```bash
DATABASE_URL=postgresql://user:pass@cloudsql-instance/med13
API_BASE_URL=https://med13-api.com
SECRET_KEY=${SECRET_KEY}
DEBUG=False
CORS_ORIGINS=https://med13-admin.com
```

#### pyproject.toml (dependency excerpt)
```
[project]
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.30.0",
  "pydantic>=2.8.0",
  "sqlalchemy>=2.0.0",
  "alembic>=1.13.0",
  "httpx>=0.27.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0.0",
  "ruff>=0.11.10,<0.12.0",
  "mypy>=1.8.0",
]
```

## Database Configuration

### Multi-Environment Database Strategy

#### Development Environment
- **Database**: SQLite for rapid development and testing
- **File**: `med13.db` (automatically created)
- **Migration**: Alembic handles schema changes
- **Testing**: Isolated database per test run

#### Production Environment
- **Database**: PostgreSQL via Google Cloud SQL
- **Instance**: Dedicated Cloud SQL instance with high availability
- **Connection**: Connection pooling via SQLAlchemy
- **Migration**: Automated Alembic migrations during deployment
- **Backup**: Automated daily backups with point-in-time recovery
- **Monitoring**: Query performance and connection pool metrics

#### Database Schema Management
```bash
# Development workflow
make db-create         # Create SQLite database
make db-migrate        # Run pending migrations
alembic revision --autogenerate -m "Add data sources table"

# Production deployment
# Migrations run automatically during Cloud Run deployment
# Rollback scripts available for emergency rollbacks
```

## Secrets Management

### Multi-Service Secrets Architecture

**Secrets are organized by service and environment:**

#### API Secrets (`med13-api` service)
- `clinvar-api-key`: ClinVar API access token
- `pubmed-api-key`: PubMed API key
- `crossref-api-key`: Crossref API token
- `omim-api-key`: OMIM API key
- `jwt-secret-key`: JWT signing secret
- `database-password`: PostgreSQL password

#### UI Secrets (`med13-curation`, `med13-admin` services)
- `oauth-client-secret`: OAuth2 client secret
- `api-key`: For backend API authentication
- `analytics-key`: Analytics service credentials

#### Shared Infrastructure Secrets
- `gcp-service-account-key`: Cloud service account credentials
- `cloudsql-instance-connection-name`: Database connection details

### Service Account Configuration

**Per-service, per-environment service accounts:**

```bash
# Create service accounts for each service
services=("api" "curation" "admin")
envs=("dev" "staging" "prod")

for service in "${services[@]}"; do
  for env in "${envs[@]}"; do
    # Create service account
    gcloud iam service-accounts create "med13-${service}-${env}" \
      --description="MED13 ${service} service - ${env} environment"

    # Grant service-specific permissions
    SA="med13-${service}-${env}@YOUR_PROJECT.iam.gserviceaccount.com"

    # All services need Secret Manager access
    gcloud projects add-iam-policy-binding YOUR_PROJECT \
      --member="serviceAccount:$SA" \
      --role="roles/secretmanager.secretAccessor"

    # API service needs Cloud SQL access
    if [ "$service" = "api" ]; then
      gcloud projects add-iam-policy-binding YOUR_PROJECT \
        --member="serviceAccount:$SA" \
        --role="roles/cloudsql.client"
    fi

    # UI services need Cloud Run invoker access
    if [[ "$service" =~ ^(curation|admin)$ ]]; then
      gcloud projects add-iam-policy-binding YOUR_PROJECT \
        --member="serviceAccount:$SA" \
        --role="roles/run.invoker"
    fi
  done
done
```

### Secrets Organization Strategy

```
Secret Manager Structure:
/projects/YOUR_PROJECT/secrets/
├── med13-api-dev-clinvar-key
├── med13-api-prod-database-password
├── med13-curation-dev-oauth-secret
├── med13-admin-staging-api-key
└── med13-shared-dev-gcp-sa-key
```

**Benefits:**
- ✅ **Service isolation**: Each service only accesses its own secrets
- ✅ **Environment separation**: Dev/staging/prod secrets are independent
- ✅ **Minimal permissions**: Principle of least privilege
- ✅ **Audit trails**: Complete access logging for compliance

## Security Configuration

### Multi-Service Security Architecture

#### Authentication & Authorization
- **Centralized Auth**: JWT-based authentication across all services
- **Role-Based Access**: Hierarchical permissions (admin, researcher, curator)
- **Service Tokens**: API-to-API authentication between services
- **OAuth2 Integration**: Google Cloud Identity Platform for user auth
- **Session Management**: Secure token handling with automatic expiration

#### Network Security
- **HTTPS Only**: Cloud Run enforces SSL/TLS for all services
- **VPC Networks**: Isolated network per environment (dev/staging/prod)
- **Cloud SQL Security**: Private IP connections, no public access
- **Service Mesh**: Internal service communication via secure channels
- **Firewall Rules**: Restrictive ingress/egress rules per service

#### Data Protection
- **Encryption at Rest**: Cloud SQL automatic encryption
- **Encryption in Transit**: TLS 1.3 for all communications
- **Secrets Management**: Google Secret Manager with audit trails
- **Database Security**: Row-level security and query parameterization
- **Backup Encryption**: Encrypted database backups with access controls

## Cost Optimization

### Multi-Service Cost Architecture

**Costs are distributed across independent services:**

#### Compute Costs (Cloud Run)
```
Per Service Monthly Estimates:
├── med13-api (FastAPI backend)
│   ├── CPU: $15-50/month (depends on API load)
│   ├── Memory: $20-70/month (512MB-2GB instances)
│   └── Requests: $0-10/month (first 2M free)
├── med13-curation (Legacy Dash UI - retired) [decommissioned]
└── med13-admin (Next.js UI)
    ├── CPU: $3-10/month (admin usage patterns)
    ├── Memory: $8-20/month (React SPA)
    └── Requests: $0-3/month (admin workflows)
```

#### Data Costs (Cloud SQL PostgreSQL)
```
Production Database Costs:
├── Storage: $0.10/GB/month (~$50-100/month for 500GB-1TB)
├── CPU: $20-50/month (depending on instance type)
├── Backup: $0.08/GB/month (~$40/month for 500GB)
└── Network: $0.01/GB egress (minimal for internal traffic)
Total: $110-190/month
```

#### Additional Services
```
Supporting Infrastructure:
├── Secret Manager: $0.06/secret/month (~$10/month for 15 secrets)
├── Cloud Storage: $0.02/GB/month (~$5-10/month for backups)
├── Cloud Load Balancing: $18.00/month (global load balancer)
└── Cloud Monitoring: $0.01/GB ingested (~$20/month for logs)
Total: $50-60/month
```

### Total Monthly Cost Estimates

**Development Environment:** $50-100/month
- Single Cloud Run instance for each service
- Smaller Cloud SQL instance
- Minimal monitoring

**Production Environment:** $300-500/month
- Multi-instance Cloud Run scaling
- Production Cloud SQL instance
- Full monitoring and logging
- Load balancing and CDN

### Cost Optimization Strategies

#### Service-Level Optimization
- **Instance Sizing**: Right-size CPU/memory per service workload
- **Scaling Configuration**: Set appropriate min/max instances
- **Traffic Patterns**: Optimize based on usage (admin vs researcher patterns)

#### Database Optimization
- **Connection Pooling**: Reuse connections to reduce overhead
- **Query Optimization**: Index optimization and query performance
- **Storage Tiers**: Use appropriate storage classes for backups

#### Monitoring Optimization
- **Log Sampling**: Sample logs in high-traffic scenarios
- **Metrics Retention**: Configure appropriate retention periods
- **Alert Optimization**: Tune alerting thresholds to reduce noise

## Monitoring & Observability

### Multi-Service Monitoring Architecture

**Comprehensive observability across all services:**

#### Service-Level Metrics (Per Cloud Run Service)
```
med13-api (FastAPI Backend):
├── HTTP Metrics: Request count, latency, error rates (4xx/5xx)
├── Performance: CPU utilization, memory usage, instance scaling
├── Business: API calls per endpoint, data source ingestion rates
└── Errors: Application exceptions, database connection issues

med13-curation (Legacy Dash UI - retired):
├── User Metrics: Page views, session duration, user interactions
├── Performance: Load times, rendering performance, API call latency
├── Errors: JavaScript errors, failed API requests
└── Usage: Feature adoption, workflow completion rates

med13-admin (Next.js UI):
├── Admin Metrics: CRUD operation counts, bulk action performance
├── Performance: Page load times, bundle sizes, API response times
├── Security: Failed auth attempts, permission violations
└── Business: Data source management operations, user admin actions
```

#### Database Monitoring (Cloud SQL)
```
PostgreSQL Metrics:
├── Connection Pool: Active/idle connections, connection timeouts
├── Query Performance: Slow queries, index usage, cache hit rates
├── Storage: Table sizes, growth trends, backup status
├── Replication: Lag times, sync status (if using read replicas)
└── Health: Uptime, failover events, maintenance windows
```

#### Infrastructure Monitoring
```
Google Cloud Services:
├── Load Balancer: Request distribution, backend health, SSL certs
├── Cloud Storage: Bucket usage, access patterns, data transfer
├── Secret Manager: Access patterns, rotation status
└── VPC Network: Traffic patterns, security violations
```

### Observability Stack

#### Logging Strategy
```bash
# Structured logging with service-specific contexts
{
  "timestamp": "2024-01-15T10:30:00Z",
  "service": "med13-api",
  "level": "INFO",
  "request_id": "abc-123-def",
  "user_id": "user-456",
  "operation": "create_data_source",
  "duration_ms": 250,
  "status": "success"
}
```

#### Alerting Configuration
```
Critical Alerts:
├── Service Down: Any service unavailable for >5 minutes
├── High Error Rate: >5% of requests failing for >10 minutes
├── Database Issues: Connection failures or slow queries
└── Security: Failed auth attempts or unusual access patterns

Performance Alerts:
├── High Latency: API responses >2 seconds for >5 minutes
├── High CPU/Memory: Service utilization >80% for >10 minutes
└── Database Slow: Query response time >1 second for >5 minutes
```

#### Dashboards and Visualization
```
Custom Dashboards:
├── Service Overview: All services health and performance
├── API Analytics: Endpoint usage, error rates, performance
├── User Experience: Page load times, error rates, feature usage
├── Database Health: Connection pools, query performance, storage
└── Security Monitoring: Auth failures, unusual access patterns
```

## Setup Instructions

### Prerequisites
1. **Google Cloud Project** with billing enabled
2. **GitHub Repository** with Actions enabled
3. **Python 3.12+** development environment
4. **Node.js 18+** (for Next.js admin interface)
5. **Docker** (for local development)

### Multi-Service Infrastructure Setup

#### 1. Google Cloud Services Configuration
```bash
# Enable required APIs for all services
gcloud services enable run.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable sqladmin.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable monitoring.googleapis.com

# Create Cloud SQL PostgreSQL instance (production)
gcloud sql instances create med13-prod \
  --database-version=POSTGRES_15 \
  --cpu=2 \
  --memory=4GB \
  --region=us-central1 \
  --storage-size=100GB \
  --storage-type=SSD

# Create databases for each environment
gcloud sql databases create med13_prod --instance=med13-prod
gcloud sql databases create med13_staging --instance=med13-prod
```

#### 2. Service Accounts Setup
```bash
# Run the service account creation script from Secrets Management section
# This creates per-service, per-environment service accounts

# Export service account keys to GitHub secrets
# GCP_SA_KEY_API_PROD, GCP_SA_KEY_CURATION_PROD, etc.
```

#### 3. Storage Buckets Setup
```bash
# Create data retention buckets
gsutil mb -p YOUR_PROJECT -c standard gs://med13-data-sources
gsutil lifecycle set retention-policy-90-days gs://med13-data-sources

gsutil mb -p YOUR_PROJECT -c coldline gs://med13-data-archive
gsutil lifecycle set retention-policy-1-year gs://med13-data-archive

# Set up CORS for frontend access (if needed)
gsutil cors set cors-config.json gs://med13-data-sources
```

#### 4. Secrets Configuration
```bash
# Create secrets for each service (see Secrets Management section)
# Example: API service secrets
echo -n "your-clinvar-api-key" | \
  gcloud secrets create med13-api-prod-clinvar-key \
  --data-file=-

# Set up IAM permissions for service accounts to access secrets
```

### Development Environment Setup

#### Local Development with Docker Compose
```yaml
# docker-compose.yml (create this file)
version: '3.8'
services:
  api:
    build: .
    ports:
      - "8080:8080"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/med13_dev
      - SECRET_KEY=dev-secret-key
    depends_on:
      - db
    volumes:
      - ./src:/app/src

  db:
    image: postgres:15
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: med13_dev
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

#### Local Development Commands
```bash
# Start all services
docker-compose up -d

# Run database migrations
docker-compose exec api alembic upgrade head

# View logs
docker-compose logs -f api
docker-compose logs -f curation

# Stop services
docker-compose down
```

### Production Deployment

#### Automated Deployment via GitHub Actions
1. **Push to main branch**: Triggers staging deployment
2. **Create GitHub release**: Triggers production deployment
3. **Monitor deployments**: Check Cloud Run console for all services

#### Manual Deployment (if needed)
```bash
# Deploy API service
gcloud run deploy med13-api \
  --source . \
  --region=us-central1 \
  --service-account=med13-api-prod@YOUR_PROJECT.iam.gserviceaccount.com \
  --set-env-vars=DATABASE_URL=postgresql://...

# Deploy curation service
gcloud run deploy med13-curation \
  --source . \
  --region=us-central1 \
  --service-account=med13-curation-prod@YOUR_PROJECT.iam.gserviceaccount.com

# Deploy admin service (when ready)
gcloud run deploy med13-admin \
  --source src/web/.next \
  --region=us-central1 \
  --service-account=med13-admin-prod@YOUR_PROJECT.iam.gserviceaccount.com
```

#### Service URLs After Deployment
- **API**: `https://med13-api-[hash]-uc.a.run.app`
- **Curation**: `https://med13-curation-[hash]-uc.a.run.app`
- **Admin**: `https://med13-admin-[hash]-uc.a.run.app` (future)

### Post-Deployment Configuration

#### Domain Setup (Optional)
```bash
# Map custom domains to services
gcloud run domain-mappings create \
  --service=med13-api \
  --domain=api.med13foundation.org

gcloud run domain-mappings create \
  --service=med13-curation \
  --domain=curate.med13foundation.org

gcloud run domain-mappings create \
  --service=med13-admin \
  --domain=admin.med13foundation.org
```

#### Monitoring Setup
1. **Enable Cloud Monitoring** for all services
2. **Set up alerts** for critical metrics
3. **Configure dashboards** for service monitoring
4. **Set up log exports** to BigQuery (optional)

#### Additional Environments (Optional)
```bash
# Create staging environment
gcloud run deploy med13-api-staging \
  --source . \
  --region=us-central1 \
  --service-account=med13-api-staging@YOUR_PROJECT.iam.gserviceaccount.com

# Create development environment
gcloud run deploy med13-api-dev \
  --source . \
  --region=us-central1 \
  --service-account=med13-api-dev@YOUR_PROJECT.iam.gserviceaccount.com \
  --allow-unauthenticated  # Allow public access for development
```

## Maintenance & Operations

### Multi-Service Maintenance Strategy

#### Backup Strategy
- **Database**: Automated PostgreSQL backups with point-in-time recovery
- **Application**: Infrastructure as code in GitHub with version control
- **Secrets**: Versioned in Google Secret Manager with audit trails
- **Code**: Git-based version control with immutable releases

#### Update Process (Per Service)
```bash
# Independent service updates
1. Make code changes (service-specific)
2. Push to feature branch
3. Create pull request with service label (api, curation, admin)
4. Automated testing runs for affected services
5. Merge triggers deployment of specific service(s)
6. Monitor service health post-deployment
```

#### Service-Specific Rollbacks
```bash
# Rollback individual services independently
gcloud run services update-traffic med13-api \
  --to-tags rollback=true \
  --tag-traffic rollback=100

# Service remains available during rollback
# Other services unaffected
```

### Disaster Recovery

#### Service-Level Recovery
- **API Service**: Database backups + cached responses during recovery
- **UI Services**: Static fallbacks + service degradation
- **Database**: Point-in-time recovery with minimal data loss
- **Secrets**: Backup copies in secure storage

#### Cross-Service Dependencies
- **API Unavailable**: UI services show cached data/offline mode
- **Database Issues**: API returns cached responses where possible
- **UI Service Down**: Users redirected to alternative interfaces

## Future Considerations

### Potential Enhancements
- **Multi-region deployment** for global availability
- **Cloud Armor** for DDoS protection
- **Memorystore** for caching frequently accessed data
- **Dataflow** for complex ETL pipelines
- **Vertex AI** for ML-powered curation assistance

### Scaling Triggers
- Monitor usage patterns for 3-6 months
- Consider read replicas for high read workloads
- Evaluate Cloud Run Jobs for batch processing
- Plan for multi-region expansion as user base grows

## Compliance & Security Notes

While not currently required, prepare for future healthcare compliance:
- **HIPAA**: Data encryption and access controls
- **GDPR**: Data subject rights and consent management
- **Audit Logging**: Comprehensive activity tracking
- **Data Residency**: Geographic data storage requirements

## Data Retention Policy

### Retention Guidelines
- **Raw source files**: Store in Cloud Storage bucket with 90-day retention
- **Processed data**: Retain indefinitely in SQLite for research integrity
- **Audit logs**: 7-year retention for compliance and provenance tracking
- **Backups**: 30-day retention with weekly long-term archives
- **Temporary files**: Immediate deletion after processing

### Cloud Storage Setup
```bash
# Create data sources bucket with retention policy
gsutil mb -p YOUR_PROJECT -c standard gs://med13-data-sources
gsutil lifecycle set retention-policy-90-days gs://med13-data-sources

# Create archive bucket for long-term storage
gsutil mb -p YOUR_PROJECT -c coldline gs://med13-data-archive
```

### Database Backup Strategy
- **Manual backups**: Via `make backup-db` command
- **File-based recovery**: Restore from SQLite backup files
- **Version control**: Database schema tracked in code migrations

---

## Infrastructure as Code Evolution

### Current State: Manual + Scripted Setup

The infrastructure currently uses a hybrid approach:
- **Manual Setup**: Initial GCP project configuration
- **Scripted Automation**: Service account creation and permission grants
- **IaC Ready**: Documented commands ready for Terraform migration

### Future: Full Infrastructure as Code

#### Terraform Migration Path
```hcl
# Future infrastructure modules
├── modules/
│   ├── cloud-run/     # Service deployment configurations
│   ├── cloud-sql/     # Database instance management
│   ├── networking/    # VPC and security configurations
│   ├── monitoring/    # Alert and dashboard configurations
│   └── secrets/       # Secret management automation
│
├── environments/
│   ├── dev/          # Development environment config
│   ├── staging/      # Staging environment config
│   └── prod/         # Production environment config
│
└── main.tf           # Root configuration with remote state
```

#### Benefits of IaC Migration
- **Version Control**: Infrastructure changes tracked in Git
- **Reproducibility**: Consistent environments across deployments
- **Collaboration**: Code review for infrastructure changes
- **Compliance**: Audit trail for infrastructure modifications
- **Testing**: Automated testing of infrastructure changes

---

*This infrastructure guide reflects the current Clean Architecture implementation with multi-service design. Regular updates will capture new services, scaling decisions, and infrastructure improvements as the MED13 platform evolves.*
