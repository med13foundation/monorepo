FROM python:3.13.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100

RUN apt-get update \
    && apt-get install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system med13 \
    && useradd --system --gid med13 --create-home med13

WORKDIR /app

COPY pyproject.toml README.md ./
COPY alembic.ini ./
COPY artana.toml ./
COPY main.py ./
COPY alembic ./alembic
COPY src ./src

RUN pip install --upgrade pip \
    && pip install .

RUN chown -R med13:med13 /app

USER med13

EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
