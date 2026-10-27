from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg import AsyncConnection

from app.config import settings
from app.db import get_conn
from app.rbac import PERMISSOES


bearer = HTTPBearer(auto_error=False)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(401, detail="token inválido") from exc


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    conn: AsyncConnection = Depends(get_conn),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, detail="sem token")

    claims = _decode(credentials.credentials)
    user_id = claims.get("sub")
    email = (claims.get("email") or "").strip().lower()
    if not user_id or not email:
        raise HTTPException(401, detail="token sem sub/email")

    row = await (
        await conn.execute(
            """SELECT u.id::text, u.email, p.nome AS papel,
                      coalesce(array_agg(pp.permissao)
                        FILTER (WHERE pp.permissao IS NOT NULL), '{}') AS permissoes
               FROM app.usuarios u
               JOIN app.papeis p ON p.id = u.papel_id
               LEFT JOIN app.papel_permissoes pp ON pp.papel_id = p.id
               WHERE u.id = %s AND u.status = 'ativo'
               GROUP BY u.id, u.email, p.nome""",
            (user_id,),
        )
    ).fetchone()
    if row is None:
        # Sem usuário: pode ser alguém convidado que está entrando pela primeira
        # vez. O convite é consumido AQUI, e não no momento de definir a senha —
        # assim, criar conta no Supabase Auth sozinho não dá acesso a nada.
        row = await _aceitar_convite(conn, user_id, email)
    if row is None:
        raise HTTPException(403, detail="acesso não autorizado (sem convite)")

    await conn.execute(
        "UPDATE app.usuarios SET ultimo_acesso = now() WHERE id = %s",
        (user_id,),
    )
    return {
        "id": row["id"],
        "email": row["email"],
        "papel": row["papel"],
        "permissoes": set(row["permissoes"] or []),
    }


async def _aceitar_convite(conn, user_id: str, email: str):
    """Consome o convite pendente e cria o usuário com o papel escolhido."""
    convite = await (
        await conn.execute(
            """SELECT id, papel_id FROM app.convites
                WHERE lower(email) = lower(%s)
                  AND status = 'pendente'
                  AND expira_em > now()
                ORDER BY created_at DESC LIMIT 1""",
            (email,),
        )
    ).fetchone()
    if convite is None:
        return None

    # Reivindica atomicamente: com dois requests simultâneos (a pessoa clicando
    # duas vezes), só um vence e o outro não cria usuário duplicado.
    reivindicado = await (
        await conn.execute(
            "UPDATE app.convites SET status='aceito' "
            "WHERE id = %s AND status = 'pendente' RETURNING papel_id",
            (convite["id"],),
        )
    ).fetchone()
    if reivindicado is None:
        return None

    await conn.execute(
        """INSERT INTO app.usuarios (id, nome, email, papel_id, status)
           VALUES (%s, %s, %s, %s, 'ativo')
           ON CONFLICT (id) DO NOTHING""",
        (user_id, email.split("@")[0], email, reivindicado["papel_id"]),
    )

    return await (
        await conn.execute(
            """SELECT u.id::text, u.email, p.nome AS papel,
                      coalesce(array_agg(pp.permissao)
                        FILTER (WHERE pp.permissao IS NOT NULL), '{}') AS permissoes
               FROM app.usuarios u
               JOIN app.papeis p ON p.id = u.papel_id
               LEFT JOIN app.papel_permissoes pp ON pp.papel_id = p.id
               WHERE u.id = %s
               GROUP BY u.id, u.email, p.nome""",
            (user_id,),
        )
    ).fetchone()


def require_perm(perm: str) -> Callable:
    if perm not in PERMISSOES:
        raise ValueError(f"permissão desconhecida: {perm!r}")

    async def dependency(user: dict = Depends(current_user)) -> dict:
        if perm not in user["permissoes"]:
            raise HTTPException(403, detail=f"permissão necessária: {perm}")
        return user

    return dependency
