FROM python:3.13.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    PIP_ROOT_USER_ACTION=ignore \
    PYTHONPATH=/app \
    GRAPH_SERVICE_HOST=0.0.0.0 \
    GRAPH_SERVICE_PORT=8080 \
    GRAPH_SERVICE_RELOAD=0

RUN groupadd --system med13 \
    && useradd --system --gid med13 --create-home med13

WORKDIR /app

COPY services/graph_api/requirements.txt /tmp/graph_api_requirements.txt

RUN pip install --upgrade pip \
    && pip install -r /tmp/graph_api_requirements.txt

COPY services ./services
COPY src ./src

FROM base AS test

COPY services/graph_api/requirements-dev.txt /tmp/graph_api_requirements_dev.txt
COPY .dockerignore ./.dockerignore
COPY AGENTS.md ./AGENTS.md
COPY README.md ./README.md
COPY Makefile ./Makefile
COPY architecture_overrides.json ./architecture_overrides.json
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
    && pip install -r /tmp/graph_api_requirements_dev.txt

CMD ["pytest"]

FROM base AS runtime

RUN chown -R med13:med13 /app

USER med13

EXPOSE 8080

CMD ["python", "-m", "services.graph_api"]
