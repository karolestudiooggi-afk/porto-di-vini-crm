import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import AsyncConnection

from app.audit import registrar
from app.auth import current_user, require_perm
from app.config import settings
from app.db import get_conn
from app.schemas.usuarios import (
    AuditoriaItem, ConviteIn, ConviteOut, Usuario, UsuarioMe, UsuarioPatch,
)
from app.services import email_transacional


router = APIRouter(tags=["usuários"])


@router.get("/usuarios/me", response_model=UsuarioMe)
async def me(user: dict = Depends(current_user)) -> dict:
    return {**user, "permissoes": sorted(user["permissoes"])}


@router.get("/usuarios", response_model=list[Usuario])
async def listar(
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("usuarios:read")),
) -> list[dict]:
    return await (
        await conn.execute(
            """SELECT u.id::text, u.nome, u.email, p.nome AS papel,
                      u.status, u.ultimo_acesso
               FROM app.usuarios u
               JOIN app.papeis p ON p.id = u.papel_id
               ORDER BY lower(u.nome) NULLS LAST, lower(u.email)"""
        )
    ).fetchall()


@router.get("/usuarios/convites", response_model=list[ConviteOut])
async def listar_convites(
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("usuarios:read")),
) -> list[dict]:
    """Convites pendentes, para a tela mostrar quem ainda não entrou."""
    return await (
        await conn.execute(
            """SELECT c.id, c.email, p.nome AS papel, c.status,
                      c.created_at, c.expira_em
               FROM app.convites c
               JOIN app.papeis p ON p.id = c.papel_id
               WHERE c.status = 'pendente'
               ORDER BY c.created_at DESC"""
        )
    ).fetchall()


@router.post("/usuarios/convites", response_model=ConviteOut)
async def convidar(
    body: ConviteIn,
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("usuarios:manage")),
) -> dict:
    """Convida alguém para o CRM e envia o link de criação de senha."""
    email = body.email.strip().lower()

    ja_existe = await (
        await conn.execute(
            "SELECT 1 FROM app.usuarios WHERE lower(email) = %s AND status = 'ativo'",
            (email,),
        )
    ).fetchone()
    if ja_existe:
        raise HTTPException(409, detail="esta pessoa já tem acesso ao CRM")

    papel = await (
        await conn.execute("SELECT id FROM app.papeis WHERE nome = %s", (body.papel,))
    ).fetchone()
    if papel is None:
        raise HTTPException(422, detail="papel inválido")

    # Reconvidar substitui o convite anterior: dois links válidos para a mesma
    # pessoa só criam confusão sobre qual usar.
    await conn.execute(
        "UPDATE app.convites SET status='cancelado', token=NULL "
        "WHERE lower(email) = %s AND status = 'pendente'",
        (email,),
    )

    token = secrets.token_urlsafe(32)
    convite = await (
        await conn.execute(
            """INSERT INTO app.convites (email, papel_id, token, convidado_por)
               VALUES (%s, %s, %s, %s)
               RETURNING id, email, %s AS papel, status, created_at, expira_em""",
            (email, papel["id"], token, user["id"], body.papel),
        )
    ).fetchone()

    link = f"{settings.app_url.rstrip('/')}/api/definir-senha?token={token}"
    try:
        email_transacional.convite(email, link, user["email"], body.papel)
    except Exception as exc:
        # O convite fica gravado mesmo se o e-mail falhar — assim o admin pode
        # copiar o link e mandar por outro meio, em vez de perder o convite.
        raise HTTPException(
            502,
            detail=f"Convite criado, mas o e-mail não saiu ({exc}). "
                   f"Envie este link à pessoa: {link}",
        ) from exc

    await registrar(conn, user["id"], "convidar_usuario", f"convite:{convite['id']}",
                    {"email": email, "papel": body.papel})
    return convite


@router.delete("/usuarios/convites/{convite_id}", status_code=204)
async def cancelar_convite(
    convite_id: int,
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("usuarios:manage")),
) -> None:
    res = await conn.execute(
        "UPDATE app.convites SET status='cancelado', token=NULL "
        "WHERE id = %s AND status = 'pendente'",
        (convite_id,),
    )
    if res.rowcount == 0:
        raise HTTPException(404, detail="convite não encontrado ou já usado")
    await registrar(conn, user["id"], "cancelar_convite", f"convite:{convite_id}")


@router.patch("/usuarios/{usuario_id}", response_model=Usuario)
async def editar_usuario(
    usuario_id: str,
    body: UsuarioPatch,
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("usuarios:manage")),
) -> dict:
    """Muda o papel ou desativa alguém.

    Ninguém pode desativar a própria conta: seria possível ficar sem nenhum
    administrador no sistema, e aí só por SQL para voltar.
    """
    if usuario_id == user["id"] and body.status == "inativo":
        raise HTTPException(409, detail="você não pode desativar a própria conta")

    campos, valores = [], []
    if body.papel is not None:
        papel = await (
            await conn.execute("SELECT id FROM app.papeis WHERE nome = %s", (body.papel,))
        ).fetchone()
        if papel is None:
            raise HTTPException(422, detail="papel inválido")
        campos.append("papel_id = %s")
        valores.append(papel["id"])
    if body.status is not None:
        campos.append("status = %s")
        valores.append(body.status)
    if not campos:
        raise HTTPException(422, detail="nada para atualizar")

    row = await (
        await conn.execute(
            f"""UPDATE app.usuarios SET {", ".join(campos)} WHERE id = %s
                RETURNING id::text, nome, email,
                          (SELECT nome FROM app.papeis WHERE id = papel_id) AS papel,
                          status, ultimo_acesso""",
            valores + [usuario_id],
        )
    ).fetchone()
    if row is None:
        raise HTTPException(404, detail="usuário não encontrado")

    await registrar(conn, user["id"], "editar_usuario", f"usuario:{usuario_id}",
                    body.model_dump(exclude_none=True))
    return row


@router.get("/auditoria", response_model=list[AuditoriaItem])
async def auditoria(
    limit: int = Query(default=100, ge=1, le=500),
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("auditoria:read")),
) -> list[dict]:
    return await (
        await conn.execute(
            """SELECT id, usuario_id::text, acao, recurso, detalhe, created_at
               FROM app.auditoria
               ORDER BY created_at DESC
               LIMIT %s""",
            (limit,),
        )
    ).fetchall()
