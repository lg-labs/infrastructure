# Kafka Dashboard BFF — FastAPI + kafka-python + sqlmodel
#
# Multi-stage NO en MVP: la imagen de python:3.12-alpine + estas deps
# pesa ~120 MB; el ahorro de un multi-stage no compensa la complejidad.

FROM python:3.12-alpine

# Build tools necesarias para compilar algunas wheels (cffi, etc.)
RUN apk add --no-cache --virtual .build-deps gcc musl-dev libffi-dev \
 && apk add --no-cache wget tini

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && apk del .build-deps

COPY app/ /app/app/
# config/ se monta como volumen ro (owners.yaml versionado en repo)

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# tini para reaping correcto + señales limpias
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["fastapi", "run", "/app/app/main.py", "--host", "0.0.0.0", "--port", "8000"]
