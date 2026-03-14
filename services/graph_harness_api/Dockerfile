FROM python:3.13.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    GRAPH_HARNESS_SERVICE_HOST=0.0.0.0 \
    GRAPH_HARNESS_SERVICE_PORT=8091 \
    GRAPH_HARNESS_SERVICE_RELOAD=0

RUN groupadd --system med13 \
    && useradd --system --gid med13 --create-home med13

WORKDIR /app

COPY services/graph_harness_api/requirements.txt /tmp/graph_harness_api_requirements.txt

RUN pip install --upgrade pip \
    && pip install -r /tmp/graph_harness_api_requirements.txt

COPY artana.toml ./artana.toml
COPY services ./services
COPY src ./src

RUN chown -R med13:med13 /app

USER med13

EXPOSE 8091

CMD ["python", "-m", "services.graph_harness_api"]
