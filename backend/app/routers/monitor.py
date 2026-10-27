"""Tripadvisor e Reclame Aqui — lidos pelos e-mails de notificação.

Fica fora do router de /integracoes de propósito: lá as rotas têm a forma
/integracoes/{origem}/... com origem = ifood|google, e um caminho
/integracoes/monitor/... cairia nelas. Na tela, as duas plataformas aparecem
junto com iFood e Google, na aba Integrações.

Permissões, as mesmas das integrações:
  - integracoes:manage → ver painel e lista, marcar como tratado, subir .eml;
  - integracoes:config → ligar aviso, trocar palavras de crise, ler a caixa
                         agora, reprocessar o histórico.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from psycopg import AsyncConnection
from pydantic import BaseModel, Field

from app.audit import registrar
from app.auth import require_perm
from app.db import get_conn
from app.services.integracoes import monitor

router = APIRouter(prefix="/monitor", tags=["monitor"])

OrigemMonitor = Literal["tripadvisor", "reclameaqui"]
_LIMITE_UPLOAD = 60 * 1024 * 1024
_MAX_ARQUIVOS = 50


class ConfigMonitorPatch(BaseModel):
    ativo: bool | None = None
    aviso: Literal["nenhum", "criticos", "negativos", "todos"] | None = None
    webhook_url: str | None = Field(default=None, max_length=500)


class PalavrasIn(BaseModel):
    palavras: list[str] = Field(max_length=300)


class ItemPatch(BaseModel):
    tratado: bool | None = None
    observacao: str | None = Field(default=None, max_length=4000)
    unidade: str | None = Field(default=None, max_length=120)


@router.get("")
async def situacao(conn: AsyncConnection = Depends(get_conn),
                   _: dict = Depends(require_perm("integracoes:manage"))):
    """Estado da caixa, números por plataforma, configuração e palavras."""
    return await monitor.situacao(conn)


@router.get("/emails")
async def emails(limite: int = Query(50, ge=1, le=200),
                 conn: AsyncConnection = Depends(get_conn),
                 _: dict = Depends(require_perm("integracoes:manage"))):
    """E-mails que não viraram item (e por quê) — é onde se descobre que o
    encaminhamento está mandando a coisa errada, ou que o layout mudou."""
    return await monitor.emails_ignorados(conn, limite)


@router.put("/palavras")
async def salvar_palavras(body: PalavrasIn, conn: AsyncConnection = Depends(get_conn),
                          user: dict = Depends(require_perm("integracoes:config"))):
    r = await monitor.salvar_palavras(conn, body.palavras, user["id"])
    await registrar(conn, user["id"], "editar_palavras_criticas", "monitor:palavras",
                    {"total": len(r["palavras"])})
    return r


@router.post("/ler", status_code=202)
async def ler_agora(tarefas: BackgroundTasks, conn: AsyncConnection = Depends(get_conn),
                    user: dict = Depends(require_perm("integracoes:config"))):
    """Lê a caixa agora, em segundo plano. A trava impede duas leituras juntas."""
    from app.config import settings

    if not settings.monitor_caixa_configurada:
        raise HTTPException(409, "a caixa de e-mail ainda não foi configurada no servidor")
    tarefas.add_task(monitor.rodar_na_api)
    await registrar(conn, user["id"], "ler_caixa_monitor", "monitor:caixa")
    return {"iniciado": True}


@router.post("/importar")
async def importar(arquivos: list[UploadFile] = File(...),
                   conn: AsyncConnection = Depends(get_conn),
                   user: dict = Depends(require_perm("integracoes:manage"))):
    """E-mails enviados pela tela (.eml, .mbox ou .zip de .eml).

    Serve para trazer o histórico antes de a caixa estar ligada, e para testar
    com um e-mail real. Não dispara aviso: é passado, não é novidade.
    """
    if len(arquivos) > _MAX_ARQUIVOS:
        raise HTTPException(
            413, f"no máximo {_MAX_ARQUIVOS} arquivos por envio — para mais, mande um .zip "
                 "ou o .mbox exportado do Gmail")
    lidos: list[tuple[str, bytes]] = []
    total = 0
    for a in arquivos:
        conteudo = await a.read()
        total += len(conteudo)
        if total > _LIMITE_UPLOAD:
            raise HTTPException(413, "arquivos grandes demais (limite de 60 MB por envio)")
        lidos.append((a.filename or "email.eml", conteudo))
    rel = await monitor.importar(conn, lidos)
    await registrar(conn, user["id"], "importar_emails_monitor", "monitor:importar",
                    {k: v for k, v in rel.items() if k != "erros"})
    return rel


@router.post("/reprocessar")
async def reprocessar(conn: AsyncConnection = Depends(get_conn),
                      user: dict = Depends(require_perm("integracoes:config"))):
    """Lê de novo todos os e-mails guardados com as regras atuais."""
    rel = await monitor.reprocessar(conn)
    await registrar(conn, user["id"], "reprocessar_monitor", "monitor:reprocessar", rel)
    return rel


@router.patch("/{origem}/config")
async def salvar_config(origem: OrigemMonitor, body: ConfigMonitorPatch,
                        conn: AsyncConnection = Depends(get_conn),
                        user: dict = Depends(require_perm("integracoes:config"))):
    campos = body.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(422, "nada para atualizar")
    url = (campos.get("webhook_url") or "").strip()
    if url and not url.lower().startswith(("http://", "https://")):
        raise HTTPException(422, "o webhook precisa começar com https://")
    cfg = await monitor.salvar_config(conn, origem, campos, user["id"])
    await registrar(conn, user["id"], "editar_config_monitor", f"monitor:{origem}",
                    {"campos": sorted(campos)})
    return cfg


@router.get("/{origem}/painel")
async def painel(origem: OrigemMonitor, dias: int = Query(90, ge=7, le=730),
                 conn: AsyncConnection = Depends(get_conn),
                 _: dict = Depends(require_perm("integracoes:manage"))):
    return await monitor.painel(conn, origem, dias)


@router.get("/{origem}/itens")
async def listar(origem: OrigemMonitor,
                 tipo: str | None = None, unidade: str | None = None,
                 nivel: str | None = None, critico: bool | None = None,
                 pendente: bool | None = None, busca: str | None = None,
                 dias: int | None = Query(None, ge=1, le=3650),
                 page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=200),
                 conn: AsyncConnection = Depends(get_conn),
                 _: dict = Depends(require_perm("integracoes:manage"))):
    return await monitor.itens(conn, origem, tipo=tipo or None, unidade=unidade or None,
                               nivel=nivel or None, critico=critico, pendente=pendente,
                               busca=busca or None, dias=dias, page=page, page_size=page_size)


@router.get("/itens/{item_id}")
async def detalhe(item_id: int, conn: AsyncConnection = Depends(get_conn),
                  _: dict = Depends(require_perm("integracoes:manage"))):
    d = await monitor.detalhe(conn, item_id)
    if d is None:
        raise HTTPException(404, "item não encontrado")
    return d


@router.patch("/itens/{item_id}")
async def marcar(item_id: int, body: ItemPatch, conn: AsyncConnection = Depends(get_conn),
                 user: dict = Depends(require_perm("integracoes:manage"))):
    campos = body.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(422, "nada para atualizar")
    d = await monitor.marcar(conn, item_id, campos, user["id"])
    if d is None:
        raise HTTPException(404, "item não encontrado")
    await registrar(conn, user["id"], "marcar_item_monitor", f"monitor:item:{item_id}",
                    {k: v for k, v in campos.items() if k != "observacao"})
    return d
