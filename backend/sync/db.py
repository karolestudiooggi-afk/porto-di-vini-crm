"""Upsert do Domani na ficha unificada `crm.contatos`."""

from __future__ import annotations

import logging
import os

import psycopg

logger = logging.getLogger(__name__)


_HAS_NEW_ACTIVITY = """
    crm.contatos.deleted_at IS NOT NULL
    AND GREATEST(
      %(last_interaction)s,
      %(last_message_at)s,
      %(subscribed)s
    ) > crm.contatos.deleted_at
"""


_DOMANI_SET = """
    telefone = COALESCE(%(telefone)s, crm.contatos.telefone),
    email = COALESCE(%(email)s, crm.contatos.email),
    nome = COALESCE(%(nome)s, crm.contatos.nome),
    primeiro_nome = COALESCE(%(primeiro_nome)s, crm.contatos.primeiro_nome),
    sobrenome = COALESCE(%(sobrenome)s, crm.contatos.sobrenome),
    genero = COALESCE(%(genero)s, crm.contatos.genero),
    locale = COALESCE(%(locale)s, crm.contatos.locale),
    idioma = COALESCE(%(idioma)s, crm.contatos.idioma),
    url_foto_perfil = COALESCE(%(url_foto_perfil)s, crm.contatos.url_foto_perfil),
    domani_user_id = COALESCE(%(domani_user_id)s, crm.contatos.domani_user_id),
    canal = COALESCE(%(canal)s, crm.contatos.canal),
    status = %(status)s,
    subscribed = %(subscribed)s,
    last_interaction = %(last_interaction)s,
    last_message_at = %(last_message_at)s,
    last_message_type = %(last_message_type)s,
    opt_in_email = %(opt_in_email)s,
    opted_in_email = %(opted_in_email)s,
    opted_in_through = %(opted_in_through)s,
    tags = %(tags)s,
    origem = 'Domani',
    origens = (
      SELECT array_agg(DISTINCT source ORDER BY source)
      FROM unnest(coalesce(crm.contatos.origens, '{{}}'::text[]) || ARRAY['Domani']) source
    ),
    deleted_at = CASE
      WHEN ({new_activity}) THEN NULL
      ELSE crm.contatos.deleted_at
    END,
    deleted_by = CASE
      WHEN ({new_activity}) THEN NULL
      ELSE crm.contatos.deleted_by
    END,
    domani_synced_at = now(),
    updated_at = now()
""".format(new_activity=_HAS_NEW_ACTIVITY)


UPSERT_CONTACT_SQL = f"""
WITH updated_by_user_ns AS (
    UPDATE crm.contatos
    SET {_DOMANI_SET}
    WHERE user_ns = %(user_ns)s AND %(user_ns)s IS NOT NULL
    RETURNING id
),
candidate_by_phone AS (
    SELECT id
    FROM crm.contatos
    WHERE NOT EXISTS (SELECT 1 FROM updated_by_user_ns)
      AND telefone_norm = crm.fn_phone_canon(%(telefone)s)
      AND crm.fn_phone_canon(%(telefone)s) IS NOT NULL
    LIMIT 1
),
updated_by_phone AS (
    UPDATE crm.contatos
    SET user_ns = COALESCE(crm.contatos.user_ns, %(user_ns)s),
        {_DOMANI_SET}
    WHERE id IN (SELECT id FROM candidate_by_phone)
    RETURNING id
),
candidate_by_email AS (
    SELECT min(id) AS id
    FROM crm.contatos
    WHERE NOT EXISTS (SELECT 1 FROM updated_by_user_ns)
      AND NOT EXISTS (SELECT 1 FROM updated_by_phone)
      AND email_norm = crm.fn_email_norm(%(email)s)
      AND crm.fn_email_norm(%(email)s) IS NOT NULL
    HAVING count(*) = 1
),
updated_by_email AS (
    UPDATE crm.contatos
    SET user_ns = COALESCE(crm.contatos.user_ns, %(user_ns)s),
        {_DOMANI_SET}
    WHERE id IN (SELECT id FROM candidate_by_email)
    RETURNING id
),
candidate_by_social AS (
    SELECT id
    FROM crm.contatos
    WHERE NOT EXISTS (SELECT 1 FROM updated_by_user_ns)
      AND NOT EXISTS (SELECT 1 FROM updated_by_phone)
      AND NOT EXISTS (SELECT 1 FROM updated_by_email)
      AND canal = %(canal)s
      AND domani_user_id = %(domani_user_id)s
      AND %(canal)s IS NOT NULL
      AND %(domani_user_id)s IS NOT NULL
    LIMIT 1
),
updated_by_social AS (
    UPDATE crm.contatos
    SET user_ns = COALESCE(crm.contatos.user_ns, %(user_ns)s),
        {_DOMANI_SET}
    WHERE id IN (SELECT id FROM candidate_by_social)
    RETURNING id
),
inserted AS (
    INSERT INTO crm.contatos (
      user_ns, domani_user_id, canal, telefone, email,
      nome, primeiro_nome, sobrenome, genero, locale, idioma, url_foto_perfil,
      status, subscribed, last_interaction, last_message_at, last_message_type,
      opt_in_email, opted_in_email, opted_in_through,
      tags, origem, origens, domani_synced_at
    )
    SELECT
      %(user_ns)s, %(domani_user_id)s, %(canal)s, %(telefone)s, %(email)s,
      %(nome)s, %(primeiro_nome)s, %(sobrenome)s, %(genero)s, %(locale)s,
      %(idioma)s, %(url_foto_perfil)s,
      %(status)s, %(subscribed)s, %(last_interaction)s, %(last_message_at)s,
      %(last_message_type)s, %(opt_in_email)s, %(opted_in_email)s,
      %(opted_in_through)s, %(tags)s, 'Domani', ARRAY['Domani'], now()
    WHERE NOT EXISTS (SELECT 1 FROM updated_by_user_ns)
      AND NOT EXISTS (SELECT 1 FROM updated_by_phone)
      AND NOT EXISTS (SELECT 1 FROM updated_by_email)
      AND NOT EXISTS (SELECT 1 FROM updated_by_social)
    RETURNING id
)
SELECT id FROM updated_by_user_ns
UNION ALL SELECT id FROM updated_by_phone
UNION ALL SELECT id FROM updated_by_email
UNION ALL SELECT id FROM updated_by_social
UNION ALL SELECT id FROM inserted;
"""


RESET_LABELS_SQL = """
UPDATE crm.contatos
SET etiquetas = ARRAY[]::text[]
WHERE user_ns IS NOT NULL;
"""


SET_LABEL_SQL = """
UPDATE crm.contatos
SET etiquetas = CASE
  WHEN NOT (%(label_name)s = ANY(coalesce(etiquetas, ARRAY[]::text[])))
    THEN coalesce(etiquetas, ARRAY[]::text[]) || %(label_name)s
  ELSE etiquetas
END
WHERE user_ns = ANY(%(user_ns_list)s);
"""


def _db_url() -> str:
    return os.environ["DATABASE_URL"]


def _connect() -> psycopg.Connection:
    """Compatível com o pooler transaction do Supabase."""
    return psycopg.connect(_db_url(), prepare_threshold=None)


def upsert_contacts(contacts: list[dict]) -> int:
    if not contacts:
        return 0

    missing_user_ns = sum(1 for contact in contacts if not contact.get("user_ns"))
    if missing_user_ns:
        logger.warning("%d contato(s) vieram sem user_ns.", missing_user_ns)

    written = 0
    failures = 0
    with _connect() as conn:
        with conn.cursor() as cur:
            for contact in contacts:
                cur.execute("SAVEPOINT contact_upsert")
                try:
                    cur.execute(UPSERT_CONTACT_SQL, _adapt(contact))
                    if cur.fetchone() is None:
                        raise RuntimeError("upsert não retornou o id do contato")
                    cur.execute("RELEASE SAVEPOINT contact_upsert")
                    written += 1
                except Exception:
                    cur.execute("ROLLBACK TO SAVEPOINT contact_upsert")
                    failures += 1
                    logger.exception(
                        "Falha no contato user_ns=%r canal=%r domani_user_id=%r (pulado)",
                        contact.get("user_ns"),
                        contact.get("canal"),
                        contact.get("domani_user_id"),
                    )
        conn.commit()

    if failures:
        logger.warning("%d contato(s) foram pulados por erro de upsert.", failures)
    return written


def replace_all_labels(assignments: dict[str, list[str]]) -> None:
    """Substitui todas as etiquetas Domani em uma única transação.

    O chamador deve terminar de ler a API antes de entrar aqui. Se qualquer
    escrita falhar, o contexto da conexão desfaz o reset e todos os sets.
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(RESET_LABELS_SQL)
            for label_name, user_ns_list in assignments.items():
                if not user_ns_list:
                    continue
                cur.execute(
                    SET_LABEL_SQL,
                    {"label_name": label_name, "user_ns_list": user_ns_list},
                )
        conn.commit()


def _adapt(record: dict) -> dict:
    return {key: _sanitize(value) for key, value in record.items()}


def _sanitize(value):
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize(item) for item in value)
    if isinstance(value, dict):
        return {_sanitize(key): _sanitize(item) for key, item in value.items()}
    return value
