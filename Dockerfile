FROM python:3.13.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

RUN groupadd --system med13 && useradd --system --gid med13 --create-home med13

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN chown -R med13:med13 /app

USER med13

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
