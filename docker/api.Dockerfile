# API FastAPI + sync Domani + agendador (a mesma imagem serve aos três).
# Contexto do build: a raiz do repositório (ver docker-compose.yml).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    TZ=America/Sao_Paulo

# tzdata: a API e o agendador trabalham no fuso America/Sao_Paulo (zoneinfo).
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.11.32

WORKDIR /app

# Dependências primeiro (camada reaproveitada enquanto o uv.lock não muda).
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY docker/agendador.py docker/criar_admin.py ./docker/

# Sem root. /estado guarda o checkpoint do sync e o registro do agendador
# (volume `estado` no compose).
RUN useradd --system --uid 10001 --home-dir /app crm \
 && mkdir -p /estado \
 && chown crm /estado
USER crm

EXPOSE 8081
CMD ["uvicorn", "app.main:app", "--host=0.0.0.0", "--port=8081", "--root-path=/api", "--proxy-headers", "--forwarded-allow-ips=*"]
