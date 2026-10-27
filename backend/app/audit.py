from psycopg import AsyncConnection
from psycopg.types.json import Json


async def registrar(
    conn: AsyncConnection,
    usuario_id: str,
    acao: str,
    recurso: str,
    detalhe: dict | None = None,
    ip: str | None = None,
) -> None:
    await conn.execute(
        """INSERT INTO app.auditoria (usuario_id, acao, recurso, detalhe, ip)
           VALUES (%s, %s, %s, %s, %s)""",
        (usuario_id, acao, recurso, Json(detalhe) if detalhe else None, ip),
    )
