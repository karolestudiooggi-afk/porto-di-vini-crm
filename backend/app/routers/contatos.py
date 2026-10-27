import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from openpyxl import Workbook
from psycopg import AsyncConnection

from app.audit import registrar
from app.auth import require_perm
from app.db import get_conn
from app.schemas.common import Page
from app.schemas.contatos import (
    ContatoDetail,
    ContatoFiltros,
    ContatoListItem,
    ContatoPatch,
    ContatoStats,
    ImportReport,
    TimelineItem,
)
from app.services.importacao import import_rows, parse_upload


router = APIRouter(prefix="/contatos", tags=["contatos"])

_ORDER = {
    "interacao_recente": "last_interaction DESC NULLS LAST, id DESC",
    "mensagem_recente": "last_message_at DESC NULLS LAST, id DESC",
    "cadastro_recente": "created_at DESC, id DESC",
    "az": "nome ASC NULLS LAST, id ASC",
    "za": "nome DESC NULLS LAST, id DESC",
}

_COMBINED_TAGS = """ARRAY(
  SELECT DISTINCT tag
  FROM unnest(coalesce(tags, '{}') || coalesce(tags_manuais, '{}')) tag
  ORDER BY tag
)"""


def _export_value(value):
    if isinstance(value, list):
        return "; ".join(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


@dataclass
class Filters:
    where: list[str] = field(default_factory=lambda: ["deleted_at IS NULL"])
    args: list = field(default_factory=list)

    @property
    def sql(self) -> str:
        return " AND ".join(self.where)


def _build_filters(
    busca: str | None = None,
    canal: str | None = None,
    status: str | None = None,
    idioma: str | None = None,
    origem: str | None = None,
    tags: list[str] | None = None,
    etiquetas: list[str] | None = None,
    com_email: bool | None = None,
    com_telefone: bool | None = None,
    recebe_email: bool | None = None,
    ja_recebeu: bool | None = None,
) -> Filters:
    filtros = Filters()
    if busca:
        termo = f"%{busca.strip()}%"
        filtros.where.append(
            "(nome ILIKE %s OR telefone ILIKE %s OR email ILIKE %s "
            "OR domani_user_id ILIKE %s)"
        )
        filtros.args.extend([termo] * 4)
    for coluna, valor in (
        ("canal", canal),
        ("status", status),
        ("idioma", idioma),
        ("origem", origem),
    ):
        if valor:
            filtros.where.append(f"{coluna} = %s")
            filtros.args.append(valor)
    if tags:
        filtros.where.append(f"{_COMBINED_TAGS} && %s::text[]")
        filtros.args.append(tags)
    if etiquetas:
        filtros.where.append("etiquetas && %s::text[]")
        filtros.args.append(etiquetas)
    for coluna, valor in (("email_norm", com_email), ("telefone_norm", com_telefone)):
        if valor is not None:
            filtros.where.append(f"{coluna} IS {'NOT ' if valor else ''}NULL")

    # "Recebe campanha?" — usa EXATAMENTE a mesma regra do disparo
    # (services/segmentos.py). Se divergir, a tela mostra um número e a campanha
    # sai com outro, e ninguém entende por quê.
    #
    # Recebe = tem e-mail, não recusou, e não está na lista de descadastro.
    _RECEBE = """
          email_norm IS NOT NULL
      AND coalesce(opt_in_email, true) IS TRUE
      AND NOT EXISTS (
            SELECT 1 FROM email.suppressions s WHERE s.email = email_norm
          )
    """
    if recebe_email is not None:
        filtros.where.append(
            f"({_RECEBE})" if recebe_email else f"NOT ({_RECEBE})"
        )

    # "Já recebeu campanha?" — para montar o próximo envio sem repetir quem já
    # foi alcançado. Sem isto, "selecionar os primeiros N" traz sempre as mesmas
    # pessoas, porque a ordem não muda entre um disparo e outro.
    #
    # Conta só o que SAIU de fato ('enviado'): quem está pendente ou falhou ainda
    # não recebeu nada e deve continuar disponível.
    # "Já recebeu" inclui quem está AGENDADO para receber.
    #
    # O caso real: montar na segunda as campanhas de terça, quarta e quinta. Se o
    # filtro olhasse só `enviado`, nenhuma teria saído ainda — as três seleções
    # trariam as MESMAS pessoas, e cada uma receberia três vezes na semana.
    #
    # Então conta também quem está `pendente` ou `processando` numa campanha
    # viva. Campanha CANCELADA ou que FALHOU fica de fora: quem estava nela não
    # recebeu nada e não pode ficar excluído para sempre.
    _JA_RECEBEU = """
      EXISTS (
        SELECT 1 FROM email.recipients r
          JOIN email.campaigns cp ON cp.id = r.campaign_id
         WHERE r.contato_id = crm.contatos.id
           AND (
                 r.status = 'enviado'
              OR (r.status IN ('pendente', 'processando')
                  AND cp.status NOT IN ('cancelada', 'falhou'))
           )
      )
    """
    if ja_recebeu is not None:
        filtros.where.append(
            f"({_JA_RECEBEU})" if ja_recebeu else f"NOT ({_JA_RECEBEU})"
        )
    return filtros


def _filters_from_params(
    busca: str | None,
    canal: str | None,
    status: str | None,
    idioma: str | None,
    origem: str | None,
    tags: list[str] | None,
    etiquetas: list[str] | None,
    com_email: bool | None,
    com_telefone: bool | None,
    recebe_email: bool | None = None,
    ja_recebeu: bool | None = None,
) -> Filters:
    return _build_filters(
        busca, canal, status, idioma, origem, tags, etiquetas, com_email, com_telefone,
        recebe_email, ja_recebeu
    )


@router.get("", response_model=Page[ContatoListItem])
async def listar(
    busca: str | None = None,
    ordenar: str = "interacao_recente",
    canal: str | None = None,
    status: str | None = None,
    idioma: str | None = None,
    origem: str | None = None,
    tags: list[str] | None = Query(default=None),
    etiquetas: list[str] | None = Query(default=None),
    com_email: bool | None = None,
    com_telefone: bool | None = None,
    recebe_email: bool | None = None,
    ja_recebeu: bool | None = None,
    # Teto alto de propósito: a tela permite selecionar um lote grande de contatos
    # de uma vez (aquecimento de domínio, envio parcial). Com 250 o pedido de 500
    # voltava 422 e o botão parecia quebrado.
    limit: int = Query(default=50, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("contatos:read")),
) -> dict:
    filtros = _filters_from_params(
        busca, canal, status, idioma, origem, tags, etiquetas, com_email, com_telefone,
        recebe_email, ja_recebeu
    )
    order = _ORDER.get(ordenar, _ORDER["interacao_recente"])
    total = (
        await (
            await conn.execute(
                f"SELECT count(*) AS total FROM crm.contatos WHERE {filtros.sql}",
                filtros.args,
            )
        ).fetchone()
    )["total"]
    rows = await (
        await conn.execute(
            f"""SELECT id, nome, telefone, email, canal, status, origem,
                       {_COMBINED_TAGS} AS tags, etiquetas,
                       last_interaction, url_foto_perfil
                FROM crm.contatos
                WHERE {filtros.sql}
                ORDER BY {order}
                LIMIT %s OFFSET %s""",
            filtros.args + [limit, offset],
        )
    ).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "items": rows}


@router.get("/stats", response_model=ContatoStats)
async def stats(
    busca: str | None = None,
    canal: str | None = None,
    status: str | None = None,
    idioma: str | None = None,
    origem: str | None = None,
    tags: list[str] | None = Query(default=None),
    etiquetas: list[str] | None = Query(default=None),
    com_email: bool | None = None,
    com_telefone: bool | None = None,
    recebe_email: bool | None = None,
    ja_recebeu: bool | None = None,
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("contatos:read")),
) -> dict:
    filtros = _filters_from_params(
        busca, canal, status, idioma, origem, tags, etiquetas, com_email, com_telefone,
        recebe_email, ja_recebeu
    )
    return await (
        await conn.execute(
            f"""SELECT count(*) AS total,
                       count(*) FILTER (WHERE telefone_norm IS NOT NULL) AS com_telefone,
                       count(*) FILTER (WHERE email_norm IS NOT NULL) AS com_email,
                       count(*) FILTER (WHERE last_interaction IS NOT NULL) AS com_interacao,
                       count(*) FILTER (
                         WHERE opt_in_email IS TRUE OR opted_in_email IS TRUE
                       ) AS com_opt_in_email
                FROM crm.contatos
                WHERE {filtros.sql}""",
            filtros.args,
        )
    ).fetchone()


@router.get("/filtros", response_model=ContatoFiltros)
async def opcoes_de_filtro(
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("contatos:read")),
) -> dict:
    row = await (
        await conn.execute(
            """SELECT
                 coalesce(array_agg(DISTINCT canal) FILTER (WHERE canal IS NOT NULL), '{}') AS canais,
                 coalesce(array_agg(DISTINCT status) FILTER (WHERE status IS NOT NULL), '{}') AS status,
                 coalesce(array_agg(DISTINCT origem) FILTER (WHERE origem IS NOT NULL), '{}') AS origens,
                 coalesce(array_agg(DISTINCT idioma) FILTER (WHERE idioma IS NOT NULL), '{}') AS idiomas
               FROM crm.contatos
               WHERE deleted_at IS NULL"""
        )
    ).fetchone()
    arrays = await (
        await conn.execute(
            """SELECT
                 coalesce((SELECT array_agg(DISTINCT value ORDER BY value)
                           FROM crm.contatos c,
                           unnest(coalesce(c.tags, '{}') || coalesce(c.tags_manuais, '{}')) value
                           WHERE c.deleted_at IS NULL), '{}') AS tags,
                 coalesce((SELECT array_agg(DISTINCT value ORDER BY value)
                           FROM crm.contatos c, unnest(c.etiquetas) value
                           WHERE c.deleted_at IS NULL), '{}') AS etiquetas"""
        )
    ).fetchone()
    return {
        "canais": sorted(row["canais"]),
        "status": sorted(row["status"]),
        "origens": sorted(row["origens"]),
        "idiomas": sorted(row["idiomas"]),
        "tags": arrays["tags"],
        "etiquetas": arrays["etiquetas"],
    }


@router.post("/import", response_model=ImportReport)
async def importar(
    arquivo: UploadFile = File(...),
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("contatos:import")),
) -> dict:
    contents = await arquivo.read()
    try:
        rows = parse_upload(contents, arquivo.filename or "")
    except Exception as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    report = await import_rows(rows, conn)
    await registrar(
        conn,
        user["id"],
        "importar",
        "contatos",
        {
            "arquivo": arquivo.filename,
            "total_linhas": report["total_linhas"],
            "criados": report["criados"],
            "atualizados": report["atualizados"],
            "restaurados": report["restaurados"],
            "ignorados": report["ignorados"],
        },
    )
    return report


@router.get("/export")
async def exportar(
    formato: str = Query(default="csv", pattern="^(csv|xlsx)$"),
    busca: str | None = None,
    canal: str | None = None,
    status: str | None = None,
    idioma: str | None = None,
    origem: str | None = None,
    tags: list[str] | None = Query(default=None),
    etiquetas: list[str] | None = Query(default=None),
    com_email: bool | None = None,
    com_telefone: bool | None = None,
    recebe_email: bool | None = None,
    ja_recebeu: bool | None = None,
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("contatos:export")),
) -> Response:
    filtros = _filters_from_params(
        busca, canal, status, idioma, origem, tags, etiquetas, com_email, com_telefone,
        recebe_email, ja_recebeu
    )
    colunas = [
        "id", "nome", "telefone", "email", "canal", "status", "origem", "idioma",
        "origens", "tags", "etiquetas", "observacoes", "last_interaction",
        "last_message_at",
    ]
    rows = await (
        await conn.execute(
            f"""SELECT id, nome, telefone, email, canal, status, origem, idioma,
                       origens, {_COMBINED_TAGS} AS tags, etiquetas, observacoes,
                       last_interaction, last_message_at
                FROM crm.contatos
                WHERE {filtros.sql}
                ORDER BY last_interaction DESC NULLS LAST, id DESC""",
            filtros.args,
        )
    ).fetchall()
    if formato == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Contatos"
        sheet.append(colunas)
        for row in rows:
            sheet.append(
                [_export_value(row[c]) for c in colunas]
            )
        binary = io.BytesIO()
        workbook.save(binary)
        return Response(
            content=binary.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=contatos.xlsx"
            },
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(colunas)
    for row in rows:
        writer.writerow([_export_value(row[c]) for c in colunas])
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=contatos.csv"},
    )


@router.get("/{contato_id}", response_model=ContatoDetail)
async def detalhe(
    contato_id: int,
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("contatos:read")),
) -> dict:
    row = await (
        await conn.execute(
            f"""SELECT c.*, c.tags AS tags_domani, {_COMBINED_TAGS} AS tags
                FROM crm.contatos c
                WHERE id = %s AND deleted_at IS NULL""",
            (contato_id,),
        )
    ).fetchone()
    if row is None:
        raise HTTPException(404, detail="contato não encontrado")
    return row


@router.get("/{contato_id}/timeline", response_model=Page[TimelineItem])
async def timeline(
    contato_id: int,
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("contatos:read")),
) -> dict:
    contato = await (
        await conn.execute(
            """SELECT last_interaction, last_message_at, last_message_type
               FROM crm.contatos WHERE id = %s AND deleted_at IS NULL""",
            (contato_id,),
        )
    ).fetchone()
    if contato is None:
        raise HTTPException(404, detail="contato não encontrado")

    items = []
    if contato["last_interaction"]:
        items.append(
            {
                "quando": contato["last_interaction"],
                "fonte": "Domani",
                "tipo": "interacao",
                "descricao": "Última interação registrada no Domani",
            }
        )
    if contato["last_message_at"]:
        tipo = contato["last_message_type"] or "não informado"
        items.append(
            {
                "quando": contato["last_message_at"],
                "fonte": "Domani",
                "tipo": "mensagem",
                "descricao": f"Última mensagem registrada ({tipo})",
            }
        )
    items.sort(key=lambda item: item["quando"], reverse=True)
    return {
        "total": len(items),
        "limit": limit,
        "offset": offset,
        "items": items[offset : offset + limit],
    }


@router.patch("/{contato_id}", response_model=ContatoDetail)
async def editar_observacoes(
    contato_id: int,
    patch: ContatoPatch,
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("contatos:write")),
) -> dict:
    if "observacoes" in patch.model_fields_set:
        row = await (
            await conn.execute(
                """UPDATE crm.contatos SET observacoes = %s
                   WHERE id = %s AND deleted_at IS NULL RETURNING *""",
                (patch.observacoes, contato_id),
            )
        ).fetchone()
        if row is None:
            raise HTTPException(404, detail="contato não encontrado")
        await registrar(
            conn,
            user["id"],
            "editar_observacoes",
            f"contato:{contato_id}",
            {"observacoes": patch.observacoes},
        )
        return await detalhe(contato_id, conn, user)
    return await detalhe(contato_id, conn, user)


@router.delete("/{contato_id}", status_code=204)
async def excluir(
    contato_id: int,
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("contatos:delete")),
) -> Response:
    row = await (
        await conn.execute(
            """UPDATE crm.contatos
               SET deleted_at = now(), deleted_by = %s
               WHERE id = %s AND deleted_at IS NULL
               RETURNING user_ns, telefone_norm, email_norm, last_interaction""",
            (user["id"], contato_id),
        )
    ).fetchone()
    if row is None:
        raise HTTPException(404, detail="contato não encontrado")
    await registrar(
        conn,
        user["id"],
        "excluir",
        f"contato:{contato_id}",
        {
            "exclusao_logica": True,
            "restaura_com_nova_atividade_domani": True,
            "tinha_user_ns": row["user_ns"] is not None,
            "tinha_telefone": row["telefone_norm"] is not None,
            "tinha_email": row["email_norm"] is not None,
            "ultima_interacao": (
                row["last_interaction"].isoformat() if row["last_interaction"] else None
            ),
        },
    )
    return Response(status_code=204)
