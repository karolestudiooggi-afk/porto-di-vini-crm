"""Avaliação/NPS.

PÚBLICAS (o cliente final não está logado — QR na recepção):
  - GET  /avaliacao/conta/{slug}   → nome da unidade + profissionais, p/ a tela
  - POST /avaliacao/responder      → recebe a nota, classifica, grava, alerta

AUTENTICADAS (painel dentro do CRM, `avaliacoes:manage`):
  - GET   /avaliacao/nps           → NPS geral, por unidade, por colaborador
  - GET   /avaliacao/contas        → unidades e a configuração de cada uma
  - PATCH /avaliacao/contas/{slug} → google_url, webhook_url, limite, ativo
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from psycopg import AsyncConnection

from app.audit import registrar
from app.auth import require_perm
from app.db import get_conn
from app.schemas.avaliacao import AvaliacaoIn, AvaliacaoOut, ContaPublica, NpsResumo
from app.services import avaliacao as svc

router = APIRouter(prefix="/avaliacao", tags=["avaliacao"])


@router.get("/conta/{slug}", response_model=ContaPublica)
async def conta_publica(slug: str, conn: AsyncConnection = Depends(get_conn)):
    """Dados que a tela pública pode ver — sem webhook nem google_url."""
    conta = await svc.get_conta(conn, slug)
    if not conta or not conta["ativo"]:
        raise HTTPException(404, "Unidade não encontrada")
    return {
        "slug": conta["slug"], "nome": conta["nome"],
        "colaboradores": await svc.colaboradores_da_unidade(conn, slug),
    }


@router.post("/responder", response_model=AvaliacaoOut)
async def responder(body: AvaliacaoIn, conn: AsyncConnection = Depends(get_conn)):
    conta = await svc.get_conta(conn, body.slug)
    if not conta or not conta["ativo"]:
        raise HTTPException(404, "Unidade não encontrada")

    categoria = svc.classificar(body.nota, conta["limite_promotor"])
    await svc.salvar_resposta(conn, body.slug, body.nota, categoria,
                              body.comentario or "", body.nome, body.whatsapp,
                              body.colaborador)

    if categoria == "detrator":
        await svc.alertar_whatsapp(conta["webhook_url"], conta["nome"], body.nota,
                                   body.comentario or "", body.nome or "",
                                   body.whatsapp or "", body.colaborador or "")

    # Só nota máxima é empurrada para o Google. A classificação de NPS continua a
    # mesma (promotor = nota >= limite); o que muda é a ROTA: um promotor de 4
    # estrelas conta como promotor no painel, mas cai na tela de agradecimento.
    manda_google = body.nota >= 5
    return {
        "ok": True,
        "categoria": categoria,
        "rota": "google" if manda_google else "obrigado",
        "google_url": conta["google_url"] if manda_google and conta["google_url"] else None,
    }


@router.get("/nps", response_model=NpsResumo)
async def nps(conn: AsyncConnection = Depends(get_conn),
              user: dict = Depends(require_perm("avaliacoes:manage")),
              janela: int | None = None):
    return await svc.resumo_nps(conn, janela)


@router.get("/contas")
async def contas(conn: AsyncConnection = Depends(get_conn),
                 user: dict = Depends(require_perm("avaliacoes:manage"))):
    """Unidades com a configuração completa (para a tela de QR/ajustes)."""
    return await svc.listar_contas(conn)


class ContaPatch(BaseModel):
    google_url: str | None = None
    webhook_url: str | None = None
    limite_promotor: int | None = None
    ativo: bool | None = None


@router.patch("/contas/{slug}")
async def editar_conta(slug: str, patch: ContaPatch,
                       conn: AsyncConnection = Depends(get_conn),
                       user: dict = Depends(require_perm("avaliacoes:manage"))):
    """Configura a unidade: link do Google, webhook de alerta, limite e ativação."""
    campos = patch.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(422, "nada para atualizar")
    sets = ", ".join(f"{k} = %s" for k in campos)
    res = await conn.execute(
        f"UPDATE avaliacao.contas SET {sets} WHERE slug=%s",
        list(campos.values()) + [slug])
    if res.rowcount == 0:
        raise HTTPException(404, "unidade não encontrada")
    await registrar(conn, user["id"], "editar_conta_avaliacao", f"avaliacao:{slug}", campos)
    return await svc.get_conta(conn, slug)
