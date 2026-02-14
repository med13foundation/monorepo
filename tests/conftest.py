"""
Test configuration and shared fixtures for MED13 Resource Library tests.

Provides pytest fixtures, test database setup, and common test utilities
across unit, integration, and end-to-end tests.
"""

import os
from collections.abc import Generator
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

import src.models.database  # noqa: F401
from src.database.sqlite_utils import build_sqlite_connect_args, configure_sqlite_engine
from src.database.url_resolver import (
    resolve_async_database_url,
    to_async_database_url,
)
from src.models.database.audit import AuditLog  # noqa: F401
from src.models.database.base import Base
from src.models.database.user import UserModel  # noqa: F401

# The original `from src.models.database.base import Base` was here, but it's moved up.

# Test database configuration (absolute path to avoid divergent relative paths)
# Support pytest-xdist by using unique database files per worker

worker_id = os.environ.get("PYTEST_XDIST_WORKER", "")
process_id = os.getpid()
db_suffix_parts = [part for part in (worker_id, str(process_id)) if part]
db_filename = f"test_med13_{'_'.join(db_suffix_parts)}.db"
TEST_DB_PATH = Path.cwd() / db_filename
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH}"

# Set core env vars early so imports (e.g., SessionLocal) bind to the test DB.
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("ASYNC_DATABASE_URL", to_async_database_url(TEST_DATABASE_URL))
os.environ.setdefault("TESTING", "true")
os.environ.setdefault(
    "MED13_DEV_JWT_SECRET",
    "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz",
)


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "VARCHAR(36)"


# Configure pytest-asyncio to use auto mode
# With asyncio_mode = auto in pytest.ini, pytest-asyncio automatically
# manages event loops, so we don't need an explicit event_loop fixture


@pytest.fixture(scope="session")
def test_engine():
    """Create a test database engine."""
    # Use in-memory SQLite for fast tests
    test_engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture(scope="function")
def db_session(test_engine) -> Generator[Session]:
    """Provide a database session for tests."""
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


def _apply_test_environment(existing_db_url: str) -> None:
    use_postgres = existing_db_url.startswith("postgresql")
    if not use_postgres:
        os.environ["DATABASE_URL"] = TEST_DATABASE_URL
        os.environ["ASYNC_DATABASE_URL"] = to_async_database_url(TEST_DATABASE_URL)
    elif not os.environ.get("ASYNC_DATABASE_URL"):
        os.environ["ASYNC_DATABASE_URL"] = to_async_database_url(existing_db_url)

    os.environ["TESTING"] = "true"
    os.environ["MED13_DEV_JWT_SECRET"] = (
        "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz"
    )


def _wire_container_dependencies() -> None:
    from src.infrastructure.dependency_injection import container as container_module
    from src.infrastructure.security.jwt_provider import JWTProvider

    test_secret = os.environ["MED13_DEV_JWT_SECRET"]
    container_module.container.jwt_secret_key = test_secret
    container_module.container.jwt_provider = JWTProvider(
        secret_key=test_secret,
        algorithm=container_module.container.jwt_algorithm,
    )
    resolved_db_url = resolve_async_database_url()
    engine_kwargs: dict[str, object] = {"echo": False, "pool_pre_ping": True}
    if os.environ.get("TESTING") == "true" and not resolved_db_url.startswith("sqlite"):
        # Avoid cross-event-loop reuse of asyncpg connections during test runs.
        engine_kwargs["poolclass"] = NullPool
    if resolved_db_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = build_sqlite_connect_args(
            include_thread_check=False,
        )
        engine_kwargs["poolclass"] = NullPool

    async_engine = create_async_engine(resolved_db_url, **engine_kwargs)
    if resolved_db_url.startswith("sqlite"):
        configure_sqlite_engine(async_engine.sync_engine)

    container_module.container.database_url = resolved_db_url
    container_module.container.engine = async_engine
    container_module.container.async_session_factory = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    container_module.container._authentication_service = None
    container_module.container._authentication_service_loop = None
    container_module.container._user_repository = None
    container_module.container._session_repository = None


def _propagate_session_local(session_module: ModuleType) -> None:
    import sys

    for module_name in (
        "tests.e2e.test_curation_detail_endpoint",
        "tests.e2e.test_curation_workflow",
        "tests.integration.test_space_discovery_isolation",
        "tests.e2e.test_auth_regression",
    ):
        if module_name not in sys.modules:
            try:
                __import__(module_name)
            except ImportError:
                continue
        module = sys.modules.get(module_name)
        if module:
            module.SessionLocal = session_module.SessionLocal
            module.engine = session_module.engine


def _wire_sync_session() -> None:
    from src.database import session as session_module

    sync_db_url = os.environ["DATABASE_URL"]
    sync_engine_kwargs: dict[str, object] = {"future": True, "pool_pre_ping": True}
    if sync_db_url.startswith("sqlite"):
        sync_engine_kwargs["connect_args"] = build_sqlite_connect_args()
        sync_engine_kwargs["poolclass"] = NullPool

    sync_engine = create_engine(sync_db_url, **sync_engine_kwargs)
    if sync_db_url.startswith("sqlite"):
        configure_sqlite_engine(sync_engine)

    session_module.DATABASE_URL = sync_db_url
    session_module.engine = sync_engine
    session_module.SessionLocal = sessionmaker(
        bind=sync_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    Base.metadata.create_all(bind=sync_engine)
    _propagate_session_local(session_module)


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables."""
    original_env = os.environ.copy()

    existing_db_url = os.environ.get("DATABASE_URL", "")
    _apply_test_environment(existing_db_url)
    _wire_container_dependencies()
    _wire_sync_session()

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture(scope="session")
def postgres_required():
    """Skip test if PostgreSQL is not available."""
    url = os.getenv("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("PostgreSQL required")


@pytest.fixture
def sample_gene_data():
    """Provide sample gene data for testing."""
    return {
        "gene_id": "MED13_TEST",
        "symbol": "MED13",
        "name": "Mediator complex subunit 13",
        "description": "Test gene for MED13",
        "gene_type": "protein_coding",
        "chromosome": "17",
        "start_position": 60000000,
        "end_position": 60010000,
        "ensembl_id": "ENSG00000108510",
        "ncbi_gene_id": 9968,
        "uniprot_id": "Q9UHV7",
    }


@pytest.fixture
def sample_variant_data():
    """Provide sample variant data for testing."""
    return {
        "variant_id": "VCV000000001",
        "clinvar_id": "RCV000000001",
        "variation_name": "c.123A>G",
        "gene_references": ["MED13"],
        "clinical_significance": "Pathogenic",
        "chromosome": "17",
        "start_position": 60001234,
        "hgvs_notations": {"c": "c.123A>G", "p": "p.Arg41Gly"},
    }


@pytest.fixture
def sample_phenotype_data():
    """Provide sample phenotype data for testing."""
    return {
        "hpo_id": "HP:0001249",
        "hpo_term": "Intellectual disability",
        "definition": "Subnormal intellectual functioning",
        "category": "Clinical",
        "gene_references": ["MED13"],
    }


@pytest.fixture
def sample_provenance():
    """Provide sample provenance data for testing."""
    from datetime import UTC, datetime

    from src.domain.value_objects.provenance import DataSource, Provenance

    return Provenance(
        source=DataSource.CLINVAR,
        acquired_at=datetime.now(UTC),
        acquired_by="test_system",
        processing_steps=["normalized", "validated"],
        validation_status="valid",
        quality_score=0.95,
    )


@pytest.fixture
def mock_api_response():
    """Provide a mock API response fixture."""

    class MockResponse:
        def __init__(self, status_code=200, json_data=None, text=""):
            self.status_code = status_code
            self.json_data = json_data or {}
            self.text = text

        def json(self):
            return self.json_data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}")

    return MockResponse


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    )
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "e2e: marks tests as end-to-end tests")


# Test data fixtures
@pytest.fixture
def test_data_factory():
    """Factory for creating test data of various types."""

    def create_data(data_type: str, **kwargs):
        factories = {
            "gene": lambda: {
                "gene_id": kwargs.get("gene_id", "TEST001"),
                "symbol": kwargs.get("symbol", "TEST"),
                "name": kwargs.get("name", "Test Gene"),
                "gene_type": kwargs.get("gene_type", "protein_coding"),
                **kwargs,
            },
            "variant": lambda: {
                "variant_id": kwargs.get("variant_id", "VCV000TEST"),
                "clinvar_id": kwargs.get("clinvar_id", "RCV000TEST"),
                "variation_name": kwargs.get("variation_name", "c.123A>G"),
                "gene_references": kwargs.get("gene_references", ["TEST"]),
                **kwargs,
            },
            "phenotype": lambda: {
                "hpo_id": kwargs.get("hpo_id", "HP:000TEST"),
                "hpo_term": kwargs.get("hpo_term", "Test phenotype"),
                "gene_references": kwargs.get("gene_references", ["TEST"]),
                **kwargs,
            },
        }

        factory = factories.get(data_type)
        if not factory:
            raise ValueError(f"Unknown data type: {data_type}")

        return factory()

    return create_data


# Database cleanup utilities
@pytest.fixture(autouse=True)
def clean_database(db_session):
    """Automatically clean database between tests."""
    # This runs before each test
    yield
    # This runs after each test
    db_session.rollback()


# Custom test markers
@pytest.fixture
def skip_if_no_database():
    """Skip test if database is not available."""
    try:
        from src.database.session import engine

        engine.execute("SELECT 1")
    except Exception:
        pytest.skip("Database not available")


@pytest.fixture
def skip_if_no_external_api():
    """Skip test if external APIs are not available."""
    if os.getenv("SKIP_EXTERNAL_TESTS"):
        pytest.skip("External API tests disabled")
