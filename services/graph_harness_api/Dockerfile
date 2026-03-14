FROM python:3.13.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    PYTHONPATH=/app \
    GRAPH_HARNESS_SERVICE_HOST=0.0.0.0 \
    GRAPH_HARNESS_SERVICE_PORT=8091 \
    GRAPH_HARNESS_SERVICE_RELOAD=0

RUN apt-get update \
    && apt-get install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system med13 \
    && useradd --system --gid med13 --create-home med13

WORKDIR /app

COPY services/graph_harness_api/requirements.txt /tmp/graph_harness_api_requirements.txt

RUN pip install --upgrade pip \
    && pip install -r /tmp/graph_harness_api_requirements.txt

COPY artana.toml ./artana.toml
COPY services ./services
COPY src ./src

FROM base AS test

COPY .dockerignore ./.dockerignore
COPY AGENTS.md ./AGENTS.md
COPY README.md ./README.md
COPY Makefile ./Makefile
COPY architecture_overrides.json ./architecture_overrides.json
COPY pyproject.toml ./pyproject.toml
COPY pytest.ini ./pytest.ini
COPY docker-compose.postgres.yml ./docker-compose.postgres.yml
COPY .env.postgres.example ./.env.postgres.example
COPY main.py ./main.py
COPY src/web/types ./src/web/types
COPY docs ./docs
COPY scripts ./scripts
COPY tests ./tests

RUN mkdir -p /app/venv/bin \
    && ln -sf /usr/local/bin/alembic /app/venv/bin/alembic \
    && pip install ".[dev]"

CMD ["pytest"]

FROM base AS runtime

RUN chown -R med13:med13 /app

USER med13

EXPOSE 8091

CMD ["python", "-m", "services.graph_harness_api"]
