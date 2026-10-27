"""Base de parceiros e o público das campanhas da aba Parceiros.

A base de parceiros NÃO é a de clientes. Ela mora em `email.parceiros`, entra
por planilha e só é usada por campanha com `lista = 'parceiros'`. Nada daqui
aparece na tela de Contatos, e nada de `crm.contatos` entra numa campanha de
parceiros.

REGRAS QUE NUNCA SÃO OPCIONAIS (as mesmas da base de clientes, por lista)
------------------------------------------------------------------------
1. **Sem e-mail não entra** — a coluna é obrigatória, mas a regra fica no SQL
   para o número da prévia nunca divergir do que sai.
2. **Descadastrou da lista de parceiros, não recebe mais** — e isso sobrevive à
   exclusão da ficha (`email.supressoes_lista`): reimportar a planilha não
   reinscreve ninguém.
3. **Supressão global também vale** — bounce (caixa que não existe) e
   reclamação de spam são do endereço, não da lista. E quem pediu para sair da
   lista de clientes também fica fora: mandar proposta comercial para quem já
   disse "não quero e-mail de vocês" é o atalho para o botão de spam, e o
   domínio é o mesmo dos dois remetentes.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from email_validator import EmailNotValidError, validate_email
from openpyxl import load_workbook
from psycopg import AsyncConnection

from app.services import importacao

MAX_ARQUIVO = importacao.MAX_FILE_SIZE

_SELECT = """
SELECT p.id, p.nome, p.empresa, p.email, p.email_norm, p.telefone, p.cargo,
       p.cidade, p.tags
FROM email.parceiros p
"""

_REGRAS = """
      p.email_norm IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM email.suppressions s WHERE s.email = p.email_norm)
  AND NOT EXISTS (SELECT 1 FROM email.supressoes_lista l
                   WHERE l.lista = 'parceiros' AND l.email = p.email_norm)
"""


# --------------------------------- público ----------------------------------

def _where(seg: dict) -> tuple[str, list, str]:
    """WHERE + args + rótulo, como em `segmentos._where`, para a base de parceiros."""
    where = [_REGRAS]
    args: list = []
    partes: list[str] = []

    if seg.get("tags"):
        where.append("p.tags && %s")
        args.append(list(seg["tags"]))
        partes.append("tags " + ", ".join(seg["tags"]))

    # Mesmo cuidado da base de clientes: não mandar duas campanhas seguidas para
    # a mesma empresa, contando também o que já está agendado e não saiu.
    if seg.get("sem_email_dias"):
        where.append("""
          NOT EXISTS (
            SELECT 1 FROM email.recipients r
              JOIN email.campaigns cp ON cp.id = r.campaign_id
             WHERE r.parceiro_id = p.id
               AND (
                     (r.status = 'enviado'
                      AND r.sent_at >= now() - make_interval(days => %s))
                  OR (r.status IN ('pendente', 'processando')
                      AND cp.status NOT IN ('cancelada', 'falhou'))
               )
          )
        """)
        args.append(int(seg["sem_email_dias"]))
        partes.append(f"sem e-mail há {seg['sem_email_dias']} dias")

    if seg.get("ids"):
        where.append("p.id = ANY(%s)")
        args.append([int(i) for i in seg["ids"]])
        partes.append(f"seleção manual ({len(seg['ids'])})")

    label = " · ".join(partes) if partes else "Toda a base de parceiros"
    return " AND ".join(where), args, label


def variaveis(p: dict) -> dict:
    """A linha do parceiro no formato que `render.variaveis_de` espera."""
    nome = (p.get("nome") or "").strip()
    return {
        "nome": nome,
        "primeiro_nome": nome.split(" ")[0] if nome else "",
        "email": p.get("email") or "",
        "empresa": p.get("empresa") or "",
    }


async def resolver(conn: AsyncConnection, seg: dict) -> list[dict]:
    where, args, _ = _where(seg)
    return await (
        await conn.execute(f"{_SELECT} WHERE {where} ORDER BY p.id", args)
    ).fetchall()


async def previa(conn: AsyncConnection, seg: dict) -> dict:
    """Mesmo formato da prévia de clientes, para a tela ser uma só."""
    where, args, label = _where(seg)
    total = (await (await conn.execute(
        f"SELECT count(*) AS n FROM email.parceiros p WHERE {where}", args)).fetchone())["n"]
    amostra = await (await conn.execute(
        f"{_SELECT} WHERE {where} ORDER BY p.id LIMIT 6", args)).fetchall()
    return {
        "total": total,
        "com_email": total,
        "label": label,
        "amostra": [
            {"id": r["id"], "nome": r["nome"] or r["empresa"], "email": r["email"]}
            for r in amostra
        ],
    }


async def contar_excluidos(conn: AsyncConnection, seg: dict) -> dict:
    """Quem o filtro pegaria mas as regras barraram — nas chaves da tela de
    clientes: `recusou` é quem saiu da lista de parceiros, `suprimido` é o
    bloqueio global (bounce, spam, descadastro de cliente)."""
    where, args, _ = _where(seg)
    sem_regras = where.replace(_REGRAS, " TRUE ")
    row = await (await conn.execute(
        f"""
        SELECT
          count(*) FILTER (WHERE p.email_norm IS NULL) AS sem_email,
          count(*) FILTER (WHERE EXISTS (
              SELECT 1 FROM email.supressoes_lista l
               WHERE l.lista = 'parceiros' AND l.email = p.email_norm)) AS recusou,
          count(*) FILTER (WHERE EXISTS (
              SELECT 1 FROM email.suppressions s WHERE s.email = p.email_norm)) AS suprimido
        FROM email.parceiros p WHERE {sem_regras}
        """, args)).fetchone()
    return {"sem_email": row["sem_email"], "recusou": row["recusou"],
            "excluido": 0, "suprimido": row["suprimido"]}


# --------------------------------- listagem ---------------------------------

# Situação de cada parceiro, calculada — não gravada. Gravar exigiria manter em
# dia a cada descadastro e a cada bounce, e um campo desatualizado aqui mostraria
# "recebe" para quem não recebe.
_SITUACAO = """
CASE
  WHEN EXISTS (SELECT 1 FROM email.supressoes_lista l
                WHERE l.lista = 'parceiros' AND l.email = p.email_norm) THEN 'descadastrou'
  WHEN EXISTS (SELECT 1 FROM email.suppressions s WHERE s.email = p.email_norm) THEN 'bloqueado'
  ELSE 'recebe'
END
"""


def _filtro_lista(busca: str | None, tag: str | None, situacao: str | None) -> tuple[str, list]:
    where = ["TRUE"]
    args: list = []
    if busca:
        termo = f"%{busca.strip().lower()}%"
        where.append("(lower(coalesce(p.nome,'')) LIKE %s OR lower(coalesce(p.empresa,'')) LIKE %s "
                     "OR p.email_norm LIKE %s)")
        args += [termo, termo, termo]
    if tag:
        where.append("%s = ANY(p.tags)")
        args.append(tag)
    if situacao in ("recebe", "descadastrou", "bloqueado"):
        where.append(f"({_SITUACAO}) = %s")
        args.append(situacao)
    return " AND ".join(where), args


async def listar(conn: AsyncConnection, *, busca: str | None = None, tag: str | None = None,
                 situacao: str | None = None, page: int = 1, page_size: int = 50) -> dict:
    where, args = _filtro_lista(busca, tag, situacao)
    total = (await (await conn.execute(
        f"SELECT count(*) AS n FROM email.parceiros p WHERE {where}", args)).fetchone())["n"]
    rows = await (await conn.execute(
        f"""SELECT p.id, p.nome, p.empresa, p.email, p.telefone, p.cargo, p.cidade,
                   p.tags, p.observacoes, p.origem, p.created_at, p.updated_at,
                   {_SITUACAO} AS situacao,
                   (SELECT max(r.sent_at) FROM email.recipients r
                     WHERE r.parceiro_id = p.id AND r.status = 'enviado') AS ultimo_envio
              FROM email.parceiros p
             WHERE {where}
             ORDER BY p.created_at DESC, p.id DESC
             LIMIT %s OFFSET %s""",
        [*args, page_size, (page - 1) * page_size])).fetchall()
    return {"items": [dict(r) for r in rows], "total": total,
            "page": page, "page_size": page_size}


async def numeros(conn: AsyncConnection) -> dict:
    row = await (await conn.execute(
        f"""SELECT count(*) AS total,
                   count(*) FILTER (WHERE ({_SITUACAO}) = 'recebe')       AS recebem,
                   count(*) FILTER (WHERE ({_SITUACAO}) = 'descadastrou') AS descadastrados,
                   count(*) FILTER (WHERE ({_SITUACAO}) = 'bloqueado')    AS bloqueados
              FROM email.parceiros p""")).fetchone()
    return dict(row)


async def tags(conn: AsyncConnection) -> list[str]:
    rows = await (await conn.execute(
        "SELECT DISTINCT unnest(tags) AS t FROM email.parceiros ORDER BY 1")).fetchall()
    return [r["t"] for r in rows if r["t"]]


# ---------------------------------- edição ----------------------------------

_EDITAVEIS = ("nome", "empresa", "email", "telefone", "cargo", "cidade", "tags", "observacoes")


def normalizar_email(valor: str) -> str:
    """Valida o formato. Não testa se a caixa existe — isso o bounce diz."""
    try:
        return validate_email((valor or "").strip(), check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise ValueError(f"e-mail inválido: {exc}") from exc


def _limpar(campos: dict) -> dict:
    saida: dict = {}
    for k, v in campos.items():
        if k not in _EDITAVEIS:
            continue
        if k == "tags":
            saida[k] = sorted({str(t).strip() for t in (v or []) if str(t).strip()})
        elif k == "email":
            saida[k] = normalizar_email(v)
        else:
            saida[k] = (str(v).strip() or None) if v is not None else None
    return saida


async def obter(conn: AsyncConnection, parceiro_id: int) -> dict | None:
    row = await (await conn.execute(
        f"""SELECT p.id, p.nome, p.empresa, p.email, p.telefone, p.cargo, p.cidade,
                   p.tags, p.observacoes, p.origem, p.created_at, p.updated_at,
                   {_SITUACAO} AS situacao,
                   (SELECT max(r.sent_at) FROM email.recipients r
                     WHERE r.parceiro_id = p.id AND r.status = 'enviado') AS ultimo_envio
              FROM email.parceiros p WHERE p.id = %s""", (parceiro_id,))).fetchone()
    return dict(row) if row else None


async def criar(conn: AsyncConnection, campos: dict) -> dict:
    dados = _limpar(campos)
    if not dados.get("email"):
        raise ValueError("informe o e-mail")
    existe = await (await conn.execute(
        "SELECT id FROM email.parceiros WHERE email_norm = crm.fn_email_norm(%s)",
        (dados["email"],))).fetchone()
    if existe:
        raise ValueError("já existe um parceiro com este e-mail")
    cols = list(dados)
    row = await (await conn.execute(
        f"""INSERT INTO email.parceiros ({", ".join(cols)}, origem)
            VALUES ({", ".join(["%s"] * len(cols))}, 'manual') RETURNING id""",
        [dados[c] for c in cols])).fetchone()
    return await obter(conn, row["id"])


async def editar(conn: AsyncConnection, parceiro_id: int, campos: dict) -> dict | None:
    dados = _limpar(campos)
    if "email" in dados:
        outro = await (await conn.execute(
            "SELECT id FROM email.parceiros WHERE email_norm = crm.fn_email_norm(%s) AND id <> %s",
            (dados["email"], parceiro_id))).fetchone()
        if outro:
            raise ValueError("já existe outro parceiro com este e-mail")
    if dados:
        sets = ", ".join(f"{k} = %s" for k in dados)
        await conn.execute(f"UPDATE email.parceiros SET {sets} WHERE id = %s",
                           [*dados.values(), parceiro_id])
    return await obter(conn, parceiro_id)


async def excluir(conn: AsyncConnection, parceiro_id: int) -> bool:
    """Apaga a ficha. O descadastro (se houver) e o histórico das campanhas ficam."""
    res = await conn.execute("DELETE FROM email.parceiros WHERE id = %s", (parceiro_id,))
    return (res.rowcount or 0) > 0


# -------------------------------- importação --------------------------------

# Cabeçalhos de planilha comercial: cada um escreve de um jeito.
_ALIASES = {
    "nome": "nome", "name": "nome", "contato": "nome", "nome_do_contato": "nome",
    "responsavel": "nome", "full_name": "nome", "nome_completo": "nome",
    "empresa": "empresa", "company": "empresa", "razao_social": "empresa",
    "nome_fantasia": "empresa", "organizacao": "empresa", "estabelecimento": "empresa",
    "parceiro": "empresa", "marca": "empresa",
    "email": "email", "e_mail": "email", "email_corporativo": "email",
    "email_do_contato": "email", "mail": "email",
    "telefone": "telefone", "celular": "telefone", "whatsapp": "telefone",
    "phone": "telefone", "fone": "telefone",
    "cargo": "cargo", "funcao": "cargo", "role": "cargo", "position": "cargo",
    "cidade": "cidade", "city": "cidade", "municipio": "cidade",
    "tags": "tags", "tag": "tags", "segmento": "tags", "categoria": "tags",
    "observacoes": "observacoes", "observacao": "observacoes", "obs": "observacoes",
    "notas": "observacoes", "notes": "observacoes",
}


def _cabecalho(valor: Any) -> str:
    # importacao._header tira acento e espaço e já entende as colunas de
    # consentimento (opt_in_email); por cima, os nomes de planilha comercial.
    base = importacao._header(valor)
    if base in _ALIASES:
        return _ALIASES[base]
    # "E-mail corporativo", "Email do responsável", "E-mail comercial"…: toda
    # coluna com e-mail no nome é a do e-mail. As de consentimento ("aceita
    # e-mail") já chegaram aqui como opt_in_email.
    if base != "opt_in_email" and ("email" in base or "e_mail" in base):
        return "email"
    return base


def _linha(bruta: dict[str, Any]) -> dict:
    v = {_cabecalho(k): val for k, val in bruta.items() if k}
    return {
        "nome": importacao._text(v.get("nome")),
        "empresa": importacao._text(v.get("empresa")),
        "email": importacao._text(v.get("email")),
        "telefone": importacao._text(v.get("telefone")),
        "cargo": importacao._text(v.get("cargo")),
        "cidade": importacao._text(v.get("cidade")),
        "observacoes": importacao._text(v.get("observacoes")),
        "tags": importacao._tags(v.get("tags")),
        "opt_in_email": importacao._consentimento(v.get("opt_in_email")),
    }


def ler_arquivo(conteudo: bytes, nome_arquivo: str) -> list[dict]:
    """CSV (vírgula, ponto e vírgula ou tab) ou XLSX, primeira linha = cabeçalho."""
    if len(conteudo) > MAX_ARQUIVO:
        raise ValueError("arquivo grande demais (limite de 30 MB)")
    ext = Path(nome_arquivo).suffix.lower()
    if ext == ".csv":
        texto = importacao._decodificar(conteudo)
        try:
            dialeto = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t")
        except csv.Error:
            dialeto = csv.excel
        brutas = list(csv.DictReader(io.StringIO(texto), dialect=dialeto))
    elif ext == ".xlsx":
        wb = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
        linhas = wb.active.iter_rows(values_only=True)
        try:
            cab = [str(c) if c is not None else "" for c in next(linhas)]
        except StopIteration:
            return []
        brutas = [dict(zip(cab, vals, strict=False)) for vals in linhas]
    else:
        raise ValueError("formato inválido; envie .csv ou .xlsx")
    return [_linha(b) for b in brutas if any(v not in (None, "") for v in b.values())]


async def importar(conn: AsyncConnection, linhas: list[dict], arquivo: str) -> dict:
    """Insere ou atualiza pelo e-mail. Uma linha ruim não derruba as outras.

    Na atualização vale o que veio preenchido na planilha (é a fonte da base de
    parceiros); célula vazia não apaga o que já existe. Tags se somam.

    Quem a planilha marca como "não quer receber" entra no descadastro da lista
    — e quem já tinha descadastrado continua fora, mesmo que a planilha diga sim.
    """
    rel = {"total_linhas": len(linhas), "criados": 0, "atualizados": 0,
           "ignorados": 0, "descadastrados": 0, "erros": []}
    for n, linha in enumerate(linhas, start=2):
        if not linha.get("email"):
            rel["ignorados"] += 1
            rel["erros"].append(f"linha {n}: sem e-mail")
            continue
        try:
            async with conn.transaction():
                email = normalizar_email(linha["email"])
                row = await (await conn.execute(
                    """INSERT INTO email.parceiros
                         (nome, empresa, email, telefone, cargo, cidade, tags, observacoes, origem)
                       VALUES (%s, %s, %s, %s, %s, %s, %s::text[], %s, %s)
                       ON CONFLICT (email_norm) DO UPDATE SET
                         nome        = coalesce(EXCLUDED.nome, email.parceiros.nome),
                         empresa     = coalesce(EXCLUDED.empresa, email.parceiros.empresa),
                         telefone    = coalesce(EXCLUDED.telefone, email.parceiros.telefone),
                         cargo       = coalesce(EXCLUDED.cargo, email.parceiros.cargo),
                         cidade      = coalesce(EXCLUDED.cidade, email.parceiros.cidade),
                         observacoes = coalesce(EXCLUDED.observacoes, email.parceiros.observacoes),
                         tags = ARRAY(SELECT DISTINCT t FROM unnest(
                                  email.parceiros.tags || EXCLUDED.tags) t ORDER BY t)
                       RETURNING (xmax = 0) AS novo, email_norm""",
                    (linha.get("nome"), linha.get("empresa"), email, linha.get("telefone"),
                     linha.get("cargo"), linha.get("cidade"), linha.get("tags") or [],
                     linha.get("observacoes"), f"importação: {arquivo}"[:200]),
                )).fetchone()
                rel["criados" if row["novo"] else "atualizados"] += 1
                if linha.get("opt_in_email") is False:
                    await conn.execute(
                        """INSERT INTO email.supressoes_lista (lista, email, motivo)
                           VALUES ('parceiros', %s, 'importacao') ON CONFLICT DO NOTHING""",
                        (row["email_norm"],))
                    rel["descadastrados"] += 1
        except Exception as exc:  # noqa: BLE001 — o relatório mostra a linha e segue
            rel["ignorados"] += 1
            rel["erros"].append(f"linha {n}: {exc}")
    return rel
