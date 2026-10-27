import csv
import io
import unicodedata
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from email_validator import EmailNotValidError, validate_email
from psycopg import AsyncConnection


# 30 MB. Uma exportação do RD Station com ~24 mil leads e 40 colunas em UTF-16
# passa de 10 MB — o limite antigo barrava a base inteira de um cliente real.
MAX_FILE_SIZE = 30 * 1024 * 1024

_ALIASES = {
    "nome": "nome",
    "name": "nome",
    "full_name": "nome",
    "nome_completo": "nome",
    "telefone": "telefone",
    "phone": "telefone",
    # Celular vai para uma chave PRÓPRIA. Mapeá-lo para "telefone" fazia as duas
    # colunas disputarem o mesmo campo — e, como o dicionário guarda só o último,
    # um "Telefone" vazio apagava o "Celular" preenchido. Foi o que aconteceu com
    # uma base real: 24 mil contatos importados sem telefone nenhum.
    "celular": "celular",
    "mobile": "celular",
    "whatsapp": "celular",
    "email": "email",
    "e_mail": "email",
    "primeiro_nome": "primeiro_nome",
    "first_name": "primeiro_nome",
    "sobrenome": "sobrenome",
    "last_name": "sobrenome",
    "genero": "genero",
    "gender": "genero",
    "locale": "locale",
    "idioma": "idioma",
    "language": "idioma",
    "status": "status",
    "tags": "tags",
    "tag": "tags",
    "observacoes": "observacoes",
    "observacao": "observacoes",
    "notes": "observacoes",
    # Consentimento. Estas colunas NÃO são opcionais quando existem no arquivo:
    # ignorá-las faz quem recusou entrar na base como se nunca tivesse sido
    # perguntado — e passar a receber campanha. É violação de LGPD, não detalhe.
    "status_para_comunicacao_por_email": "opt_in_email",
    "status_de_comunicacao": "opt_in_email",
    "opt_in": "opt_in_email",
    "opt_in_email": "opt_in_email",
    "aceita_email": "opt_in_email",
    "base_legal_para_comunicacao": "base_legal",
    "base_legal": "base_legal",
}

_FIELDS = (
    "nome",
    "telefone",
    "email",
    "primeiro_nome",
    "sobrenome",
    "genero",
    "locale",
    "idioma",
    "status",
    "observacoes",
)


def _decodificar(contents: bytes) -> str:
    """Descobre a codificação do arquivo pelo BOM, com UTF-8 como padrão.

    O RD Station exporta em UTF-16 e o Excel às vezes em Latin-1. Ler tudo como
    UTF-8 não levanta erro — só devolve texto corrompido, e o problema aparece
    depois, com a base já suja.
    """
    if contents[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return contents.decode("utf-16")
    if contents[:3] == b"\xef\xbb\xbf":
        return contents.decode("utf-8-sig")
    try:
        return contents.decode("utf-8")
    except UnicodeDecodeError:
        return contents.decode("latin-1")


def _consentimento(valor: Any) -> bool | None:
    """Interpreta a coluna de consentimento.

    Devolve None quando o arquivo não diz nada — aí a ficha fica sem informação e
    é o CRM que decide. Mas quando o arquivo diz NÃO, isso é respeitado: recusa
    explícita nunca vira "não sei".
    """
    if valor is None:
        return None
    texto = str(valor).strip().lower()
    if texto in ("", "-"):
        return None
    if texto in ("false", "0", "nao", "não", "no", "recusado", "descadastrado",
                 "opt-out", "opt out", "unsubscribed", "bounce"):
        return False
    if texto in ("true", "1", "sim", "yes", "consentimento", "consentido",
                 "opt-in", "opt in", "subscribed"):
        return True
    return None


def _header(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    normalized = "_".join(text.strip().lower().replace("-", " ").split())
    return _ALIASES.get(normalized, normalized)


# Textos que representam ausência de valor em exportações reais. "None" e "null"
# entram porque ferramentas exportam o literal em vez de célula vazia — sem isto,
# o cliente recebe um e-mail começando com "Olá None".
_VAZIOS = {"", "-", "none", "null", "n/a", "na", "nan", "undefined"}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if normalized.lower() in _VAZIOS:
        return None
    return normalized


def _tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        normalized = str(value)
        for separator in (";", "|"):
            normalized = normalized.replace(separator, ",")
        values = normalized.split(",")
    return sorted({str(item).strip() for item in values if str(item).strip()})


def _normalize_row(raw: dict[str, Any]) -> dict:
    values = {_header(key): value for key, value in raw.items() if key}
    row = {field: _text(values.get(field)) for field in _FIELDS}
    row["tags"] = _tags(values.get("tags"))

    # Telefone: vale o primeiro que tiver conteúdo. Numa exportação é comum uma
    # das duas colunas vir vazia, e a que tem o número é que interessa.
    row["telefone"] = _text(values.get("telefone")) or _text(values.get("celular"))

    # Consentimento: duas colunas podem falar dele. Se QUALQUER uma disser "não",
    # vale o não — recusa em um lugar é recusa, ponto.
    status = _consentimento(values.get("opt_in_email"))
    legal = _consentimento(values.get("base_legal"))
    if status is False or legal is False:
        row["opt_in_email"] = False
    elif status is True or legal is True:
        row["opt_in_email"] = True
    else:
        row["opt_in_email"] = None
    row.pop("base_legal", None)
    return row


def parse_upload(contents: bytes, filename: str) -> list[dict]:
    if len(contents) > MAX_FILE_SIZE:
        raise ValueError("arquivo excede o limite de 10 MB")

    extension = Path(filename).suffix.lower()
    raw_rows: list[dict[str, Any]]
    if extension == ".csv":
        text = _decodificar(contents)
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        raw_rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
    elif extension == ".xlsx":
        workbook = load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        try:
            headers = [_header(value) for value in next(rows)]
        except StopIteration:
            return []
        raw_rows = [dict(zip(headers, values, strict=False)) for values in rows]
    else:
        raise ValueError("formato inválido; envie um arquivo .csv ou .xlsx")

    return [_normalize_row(row) for row in raw_rows if any(row.values())]


async def import_rows(rows: list[dict], conn: AsyncConnection) -> dict:
    report = {
        "total_linhas": len(rows),
        "criados": 0,
        "atualizados": 0,
        "restaurados": 0,
        "ignorados": 0,
        "erros": [],
    }
    for line_number, row in enumerate(rows, start=2):
        if not row.get("telefone") and not row.get("email"):
            report["ignorados"] += 1
            report["erros"].append(
                f"linha {line_number}: informe ao menos telefone ou email"
            )
            continue
        try:
            async with conn.transaction():
                if row.get("email"):
                    try:
                        row["email"] = validate_email(
                            row["email"], check_deliverability=False
                        ).normalized
                    except EmailNotValidError as exc:
                        raise ValueError(f"email inválido: {exc}") from exc
                identity = await (
                    await conn.execute(
                        """SELECT
                             crm.fn_phone_canon(%s) AS telefone_norm,
                             crm.fn_email_norm(%s) AS email_norm,
                             (SELECT id FROM crm.contatos
                              WHERE telefone_norm = crm.fn_phone_canon(%s)
                                AND crm.fn_phone_canon(%s) IS NOT NULL
                              LIMIT 1) AS telefone_id,
                             (SELECT min(id) FROM crm.contatos
                              WHERE email_norm = crm.fn_email_norm(%s)
                                AND crm.fn_email_norm(%s) IS NOT NULL
                              HAVING count(*) = 1) AS email_id,
                             (SELECT count(*) FROM crm.contatos
                              WHERE email_norm = crm.fn_email_norm(%s)
                                AND crm.fn_email_norm(%s) IS NOT NULL) AS email_matches""",
                        (
                            row.get("telefone"), row.get("email"),
                            row.get("telefone"), row.get("telefone"),
                            row.get("email"), row.get("email"),
                            row.get("email"), row.get("email"),
                        ),
                    )
                ).fetchone()

                if row.get("telefone") and identity["telefone_norm"] is None:
                    raise ValueError("telefone inválido")
                if row.get("email") and identity["email_norm"] is None:
                    raise ValueError("email inválido")
                phone_id = identity["telefone_id"]
                email_id = identity["email_id"]
                if phone_id and email_id and phone_id != email_id:
                    raise ValueError(
                        "telefone e email pertencem a contatos diferentes"
                    )
                if not phone_id and identity["email_matches"] > 1:
                    raise ValueError("email associado a mais de um contato")

                contato_id = phone_id or email_id
                if contato_id:
                    existing = await (
                        await conn.execute(
                            "SELECT deleted_at FROM crm.contatos WHERE id = %s",
                            (contato_id,),
                        )
                    ).fetchone()
                    await conn.execute(
                        """UPDATE crm.contatos SET
                             nome = coalesce(nome, %s),
                             telefone = coalesce(telefone, %s),
                             email = coalesce(email, %s),
                             primeiro_nome = coalesce(primeiro_nome, %s),
                             sobrenome = coalesce(sobrenome, %s),
                             genero = coalesce(genero, %s),
                             locale = coalesce(locale, %s),
                             idioma = coalesce(idioma, %s),
                             status = coalesce(status, %s),
                             observacoes = coalesce(observacoes, %s),
                             tags_manuais = ARRAY(
                               SELECT DISTINCT tag
                               FROM unnest(coalesce(tags_manuais, '{}') || %s::text[]) tag
                               ORDER BY tag
                             ),
                             -- Consentimento: quem já recusou NUNCA volta a
                             -- receber por causa de uma importação. Uma planilha
                             -- desatualizada não pode reinscrever quem pediu para
                             -- sair — isso é o oposto do que a pessoa decidiu.
                             opt_in_email = CASE
                               WHEN opt_in_email IS FALSE THEN false
                               ELSE coalesce(%s::boolean, opt_in_email)
                             END,
                             origem = coalesce(origem, 'Importação'),
                             origens = ARRAY(
                               SELECT DISTINCT fonte
                               FROM unnest(coalesce(origens, '{}') || ARRAY['Importação']) fonte
                               ORDER BY fonte
                             ),
                             deleted_at = NULL,
                             deleted_by = NULL
                           WHERE id = %s""",
                        tuple(row.get(field) for field in _FIELDS)
                        + (row["tags"], row.get("opt_in_email"), contato_id),
                    )
                    report["atualizados"] += 1
                    if existing["deleted_at"] is not None:
                        report["restaurados"] += 1
                else:
                    await conn.execute(
                        """INSERT INTO crm.contatos (
                             nome, telefone, email, primeiro_nome, sobrenome,
                             genero, locale, idioma, status, observacoes,
                             tags_manuais, opt_in_email, origem, origens
                           ) VALUES (
                             %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                             %s::text[], %s::boolean, 'Importação', ARRAY['Importação']
                           )""",
                        tuple(row.get(field) for field in _FIELDS)
                        + (row["tags"], row.get("opt_in_email")),
                    )
                    report["criados"] += 1
        except Exception as exc:
            report["ignorados"] += 1
            report["erros"].append(f"linha {line_number}: {exc}")
    return report
