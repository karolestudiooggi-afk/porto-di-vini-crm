import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import lifespan as lifespan_banco
from app.routers import (
    acesso, avaliacao, contatos, dashboard, email, health, integracoes, monitor,
    tracking, usuarios, webhooks,
)
from app.services.integracoes import agente, leitor_google
from app.services.integracoes import monitor as monitor_svc

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app_: FastAPI) -> AsyncIterator[None]:
    """Abre o pool do banco e põe o agente do iFood para rodar.

    O agente vive dentro do processo da API, como no painel de origem: sobe
    junto, roda a cada 15 minutos e não depende de timer. WORKER_DESLIGADO no
    .env sobe a API sem ele.
    """
    async with lifespan_banco(app_):
        tarefas: list[asyncio.Task] = []
        if settings.agente_ligado:
            tarefas.append(asyncio.create_task(agente.agendar()))
            # Busca do Google pelo NichoChat: sobe sempre; sem a API do
            # NichoChat configurada, cada passada só confere e volta a dormir.
            tarefas.append(asyncio.create_task(leitor_google.agendar()))
            # Leitura da caixa do Tripadvisor/Reclame Aqui: só com caixa
            # configurada. WORKER_DESLIGADO desliga as três rotinas.
            if settings.monitor_caixa_configurada:
                tarefas.append(asyncio.create_task(monitor_svc.agendar()))
        else:
            logger.info("rotinas desligadas por WORKER_DESLIGADO "
                        "(agente do iFood, leitura do Google e caixa do monitor)")
        try:
            yield
        finally:
            # Cancela ANTES de o pool fechar: as passadas usam conexão dele.
            for tarefa in tarefas:
                tarefa.cancel()
                with suppress(asyncio.CancelledError):
                    await tarefa


app = FastAPI(
    title=f"CRM Domani · {settings.cliente_nome} · API",
    description=(
        "API principal do CRM Domani. O Domani é a fonte de contatos; "
        "novas fontes entram em schemas e routers independentes."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=settings.allowed_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(usuarios.router)
# Pública: quem abre o link do convite ainda não tem conta.
app.include_router(acesso.router)
app.include_router(contatos.router)
app.include_router(dashboard.router)
app.include_router(email.router)
# Públicas: chamadas pelo cliente de e-mail do destinatário, que não tem sessão.
app.include_router(tracking.router)
# Parceiros (Alpha Code, Tagme): autenticados por chave, não por sessão.
app.include_router(webhooks.router)
# Avaliação: /avaliacao/conta e /responder são PÚBLICAS (QR na mesa, sem login).
app.include_router(avaliacao.router)
# Integrações (iFood e Google Meu Negócio). Tudo exige sessão, menos
# /integracoes/google/callback, validada pelo `state` assinado do OAuth.
app.include_router(integracoes.router)
# Tripadvisor e Reclame Aqui, lidos pelos e-mails de notificação.
app.include_router(monitor.router)
