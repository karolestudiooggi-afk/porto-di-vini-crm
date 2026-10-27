"""Monitor de reputação: Tripadvisor e Reclame Aqui pelos e-mails de notificação.

Fluxo de um e-mail, venha ele da caixa (IMAP) ou de um .eml enviado pela tela:

  1. `email_bruto.ler`         → bytes MIME viram texto, links e alts;
  2. `monitor_regras.origem_de` → é do Tripadvisor, do Reclame Aqui ou de fora;
  3. o leitor da plataforma    → unidade, nota, título, texto, autor, link;
  4. faltou o essencial?       → a IA completa a partir do MESMO e-mail, e só
                                 aceita o que estiver escrito nele;
  5. palavras de crise e nível → `critico`, `nivel`;
  6. grava o e-mail original e o item; avisa o NichoChat se a regra mandar.

Idempotente de ponta a ponta: o Message-ID não entra duas vezes, e a mesma
avaliação avisada por dois e-mails (aviso + lembrete) vira um item só.

A leitura da caixa roda dentro da API, como o agente do iFood: sobe junto,
passa a cada `MONITOR_INTERVALO_MIN` minutos e respeita `WORKER_DESLIGADO`.
"""

from __future__ import annotations

import asyncio
import email
import email.policy
import imaplib
import io
import json
import logging
import mailbox
import re
import tempfile
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
from psycopg import AsyncConnection

from app.config import settings
from app.services.integracoes import email_bruto, monitor_regras as regras

logger = logging.getLogger("integracoes.monitor")

ORIGENS = regras.ORIGENS
ESPERA_INICIAL_SEG = 45
TEMPO_MAXIMO_SEG = 10 * 60
_TRAVA_EXPIRA_MIN = 15
_MAX_POR_PASSADA = 300
_LIMITE_BRUTO = 3_000_000
# Só avisa o que aconteceu há pouco. Sem isto, a primeira leitura (que traz
# 180 dias de histórico) dispararia centenas de alertas de crise antigos.
_JANELA_AVISO_H = 48
_MESES_IMAP = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class ErroCaixa(Exception):
    """A caixa não abriu: credencial errada, pasta inexistente, servidor fora."""


# ------------------------------ configuração --------------------------------

async def config(conn: AsyncConnection, origem: str) -> dict:
    row = await (await conn.execute(
        """SELECT origem, ativo, aviso, webhook_url, atualizado_em
             FROM integra.monitor_config WHERE origem = %s""", (origem,))).fetchone()
    return dict(row) if row else {"origem": origem, "ativo": True, "aviso": "negativos",
                                  "webhook_url": None, "atualizado_em": None}


async def salvar_config(conn: AsyncConnection, origem: str, campos: dict,
                        usuario_id: str | None) -> dict:
    permitidos = {"ativo", "aviso", "webhook_url"}
    campos = {k: (v.strip() or None) if isinstance(v, str) else v
              for k, v in campos.items() if k in permitidos}
    await conn.execute(
        "INSERT INTO integra.monitor_config (origem) VALUES (%s) ON CONFLICT DO NOTHING", (origem,))
    if campos:
        sets = ", ".join(f"{k} = %s" for k in campos)
        await conn.execute(
            f"""UPDATE integra.monitor_config
                   SET {sets}, atualizado_em = now(), atualizado_por = %s
                 WHERE origem = %s""", [*campos.values(), usuario_id, origem])
    return await config(conn, origem)


async def palavras(conn: AsyncConnection) -> list[str]:
    row = await (await conn.execute(
        "SELECT palavras_criticas FROM integra.monitor_ajustes WHERE id")).fetchone()
    return list(row["palavras_criticas"]) if row else []


async def salvar_palavras(conn: AsyncConnection, lista: list[str],
                          usuario_id: str | None) -> dict:
    """Troca a lista e recalcula `critico` de tudo o que já está guardado: a
    palavra nova passa a valer para o histórico, e o gráfico de crise conta
    certo desde o primeiro dia."""
    limpas: list[str] = []
    for p in lista:
        p = " ".join(str(p).split()).strip()
        if p and regras.normalizar(p) not in {regras.normalizar(x) for x in limpas}:
            limpas.append(p[:60])
    await conn.execute(
        """INSERT INTO integra.monitor_ajustes (id, palavras_criticas, atualizado_em, atualizado_por)
           VALUES (true, %s, now(), %s)
           ON CONFLICT (id) DO UPDATE SET palavras_criticas = EXCLUDED.palavras_criticas,
                                          atualizado_em = now(),
                                          atualizado_por = EXCLUDED.atualizado_por""",
        (limpas, usuario_id))
    mudaram = 0
    rows = await (await conn.execute(
        "SELECT id, titulo, texto, critico, palavras FROM integra.monitor_itens")).fetchall()
    for r in rows:
        achadas = regras.palavras_criticas(f"{r['titulo'] or ''}\n{r['texto'] or ''}", limpas)
        if bool(achadas) != r["critico"] or achadas != list(r["palavras"] or []):
            await conn.execute(
                "UPDATE integra.monitor_itens SET critico = %s, palavras = %s WHERE id = %s",
                (bool(achadas), achadas, r["id"]))
            mudaram += 1
    return {"palavras": limpas, "itens_recalculados": mudaram}


async def unidades_conhecidas(conn: AsyncConnection) -> list[str]:
    """As unidades com que o texto do e-mail é comparado: as lojas cadastradas
    nas integrações (Google e iFood) e as que alguém já corrigiu à mão aqui."""
    rows = await (await conn.execute(
        """SELECT nome AS u FROM integra.lojas
           UNION SELECT unidade FROM integra.monitor_unidades""")).fetchall()
    return sorted({r["u"] for r in rows if r["u"]})


async def _chave_ia(conn: AsyncConnection) -> str:
    """A chave da OpenAI — só a do .env do servidor (OPENAI_API_KEY)."""
    return settings.openai_api_key or ""


# ----------------------------------- IA -------------------------------------

_PROMPT_IA = """Você extrai dados de um e-mail de notificação do {plataforma} enviado a um restaurante.
Responda SOMENTE com um objeto JSON com estas chaves: tipo, unidade, nota, titulo, texto, autor, cidade.

Regras:
- Copie os trechos EXATAMENTE como aparecem no e-mail. Nunca resuma, traduza ou invente.
- Use null para tudo o que não estiver escrito no e-mail.
- tipo: "avaliacao" (avaliação nova no Tripadvisor), "reclamacao" (reclamação nova no Reclame Aqui), "interacao" (o consumidor respondeu ou mandou mensagem numa reclamação), "resultado" (o consumidor avaliou uma reclamação) ou "aviso" (qualquer outra coisa: newsletter, ranking, lembrete de prazo, dica).
- nota: número. No Tripadvisor de 1 a 5 (bolhas); no Reclame Aqui de 0 a 10. null se não houver.
- unidade: o nome da loja/unidade citada (ex.: "Unidade Centro", "Unidade Norte"), se houver.
- texto: o texto escrito pelo cliente (a avaliação, a reclamação ou a réplica), não o texto da plataforma."""


def _no_email(trecho: str | None, corpo_normalizado: str) -> bool:
    """A IA só pode devolver o que está no e-mail: confere pelos primeiros 40
    caracteres, sem acento e sem diferença de espaço."""
    if not trecho:
        return False
    alvo = regras.normalizar(trecho)[:40]
    return bool(alvo) and alvo in corpo_normalizado


async def completar_com_ia(conn: AsyncConnection, origem: str, e: email_bruto.Email,
                           item: dict | None, unidades: list[str],
                           http: httpx.AsyncClient | None = None) -> dict | None:
    """Preenche o que o leitor não achou. Nunca sobrescreve o que ele achou.

    Devolve o item completado, um item novo (quando o leitor não reconheceu o
    e-mail e a IA reconheceu), ou None se não há chave ou a IA disse "aviso".
    """
    chave = await _chave_ia(conn)
    if not chave:
        return item
    payload = {
        "model": settings.openai_model,
        "temperature": 0,
        "max_tokens": 900,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _PROMPT_IA.format(plataforma=regras.NOME[origem])},
            {"role": "user", "content": f"Assunto: {e.assunto}\nRemetente: {e.remetente}\n\n{e.texto[:7000]}"},
        ],
    }
    try:
        cli = http or httpx.AsyncClient(timeout=60)
        try:
            res = await cli.post(settings.openai_base_url, json=payload,
                                 headers={"Authorization": f"Bearer {chave}"})
        finally:
            if http is None:
                await cli.aclose()
        dados = json.loads(res.json()["choices"][0]["message"]["content"])
    except Exception:  # IA fora do ar não pode travar a leitura da caixa
        logger.warning("IA não completou o e-mail %s", e.message_id, exc_info=True)
        return item

    corpo = regras.normalizar(e.assunto + "\n" + e.texto)
    tipo = dados.get("tipo")
    validos = {"tripadvisor": {"avaliacao"},
               "reclameaqui": {"reclamacao", "interacao", "resultado"}}[origem]
    if item is None:
        if tipo not in validos:
            return None
        item = {"tipo": tipo, "externo_id": None, "loja_id": None, "unidade": None,
                "nota": None, "nota_maxima": 5 if origem == "tripadvisor" else (10 if tipo == "resultado" else None),
                "titulo": None, "texto": None, "autor": None, "cidade": None, "link": None}

    for campo in ("titulo", "texto", "autor", "cidade"):
        valor = dados.get(campo)
        if not item.get(campo) and isinstance(valor, str) and _no_email(valor, corpo):
            item[campo] = valor.strip()[:4000]
    if not item.get("unidade") and isinstance(dados.get("unidade"), str):
        u = dados["unidade"].strip()
        item["unidade"] = regras.casar_unidade(u, unidades) or (u if _no_email(u, corpo) else None)
    if item.get("nota") is None and dados.get("nota") is not None:
        try:
            n = float(dados["nota"])
            teto = item.get("nota_maxima") or 5
            if 0 <= n <= teto:
                item["nota"] = n
        except (TypeError, ValueError):
            pass
    item["_ia"] = True
    return item


# ------------------------------ processamento -------------------------------

async def _registrar_email(conn: AsyncConnection, e: email_bruto.Email, origem: str | None,
                           via: str, bruto: bytes | None, situacao: str,
                           motivo: str | None = None) -> int:
    row = await (await conn.execute(
        """INSERT INTO integra.monitor_emails
             (message_id, origem, remetente, assunto, enviado_em, via, bruto, situacao, motivo)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (message_id) DO UPDATE SET origem = EXCLUDED.origem
           RETURNING id""",
        (e.message_id, origem, e.remetente[:300], e.assunto[:500], e.enviado_em, via,
         bruto if bruto and len(bruto) <= _LIMITE_BRUTO else None, situacao, motivo))).fetchone()
    return row["id"]


async def _montar_item(conn: AsyncConnection, origem: str, e: email_bruto.Email,
                       unidades: list[str], lista_palavras: list[str],
                       http: httpx.AsyncClient | None) -> dict | None:
    """O item pronto para gravar, ou None se o e-mail não é avaliação/reclamação."""
    item = regras.LEITORES[origem](e, unidades)
    if item is None:
        # O leitor não reconheceu. Pode ser aviso de verdade (ranking,
        # lembrete) ou um layout novo da plataforma: a IA decide, se houver.
        item = await completar_com_ia(conn, origem, e, None, unidades, http)
        if item is None:
            return None
    else:
        if regras.faltando(item | {"origem": origem}):
            item = await completar_com_ia(conn, origem, e, item, unidades, http)

    # O de-para corrigido à mão vale mais que o nome que veio no e-mail.
    if item.get("loja_id"):
        row = await (await conn.execute(
            "SELECT unidade FROM integra.monitor_unidades WHERE origem = %s AND loja_id = %s",
            (origem, item["loja_id"]))).fetchone()
        if row:
            item["unidade"] = row["unidade"]

    falta = regras.faltando(item | {"origem": origem})
    item["extraido_por"] = "ia" if item.pop("_ia", False) and not falta else (
        "parcial" if falta else "regra")
    item["palavras"] = regras.palavras_criticas(
        f"{item.get('titulo') or ''}\n{item.get('texto') or ''}", lista_palavras)
    item["critico"] = bool(item["palavras"])
    item["nivel"] = regras.nivel(item)
    item["origem"] = origem
    item["ocorrido_em"] = e.enviado_em or datetime.now(timezone.utc)
    for campo, teto in (("titulo", 500), ("texto", 8000), ("autor", 200), ("cidade", 120),
                        ("unidade", 120), ("link", 2000)):
        if item.get(campo):
            item[campo] = str(item[campo])[:teto]
    return item


_COLUNAS = ("origem", "tipo", "externo_id", "loja_id", "unidade", "nota", "nota_maxima",
            "titulo", "texto", "autor", "cidade", "link", "ocorrido_em", "nivel",
            "critico", "palavras", "extraido_por")


async def processar_bruto(conn: AsyncConnection, bruto: bytes, via: str = "imap", *,
                          avisar: bool = True, http: httpx.AsyncClient | None = None,
                          contexto: dict | None = None) -> dict:
    """Um e-mail inteiro, do MIME ao item gravado (e avisado, se for o caso).

    `contexto` evita reler unidades/palavras/config a cada e-mail de uma
    passada. Devolve {"resultado": novo|repetido|ignorado|erro, ...}.
    """
    try:
        e = email_bruto.ler(bruto)
    except Exception as exc:  # noqa: BLE001 — e-mail ilegível não para a passada
        return {"resultado": "erro", "motivo": f"e-mail ilegível: {exc}"}

    ja = await (await conn.execute(
        "SELECT id FROM integra.monitor_emails WHERE message_id = %s", (e.message_id,))).fetchone()
    if ja:
        return {"resultado": "repetido", "assunto": e.assunto}

    origem = regras.origem_de(e)
    if origem is None:
        await _registrar_email(conn, e, None, via, None, "ignorado",
                               "não é do Tripadvisor nem do Reclame Aqui")
        await conn.commit()
        return {"resultado": "ignorado", "assunto": e.assunto}

    ctx = contexto if contexto is not None else {}
    if "unidades" not in ctx:
        ctx["unidades"] = await unidades_conhecidas(conn)
        ctx["palavras"] = await palavras(conn)
    if origem not in ctx:
        ctx[origem] = await config(conn, origem)

    item = await _montar_item(conn, origem, e, ctx["unidades"], ctx["palavras"], http)
    if item is None:
        await _registrar_email(conn, e, origem, via, bruto, "ignorado",
                               "aviso da plataforma que não é avaliação nem reclamação")
        await conn.commit()
        return {"resultado": "ignorado", "origem": origem, "assunto": e.assunto}

    email_id = await _registrar_email(conn, e, origem, via, bruto, "processado")
    row = await (await conn.execute(
        f"""INSERT INTO integra.monitor_itens (email_id, {", ".join(_COLUNAS)})
            VALUES (%s, {", ".join(["%s"] * len(_COLUNAS))})
            ON CONFLICT (origem, tipo, externo_id)
              WHERE externo_id IS NOT NULL AND tipo IN ('avaliacao', 'reclamacao')
              DO NOTHING
            RETURNING id""",
        [email_id, *(item.get(c) for c in _COLUNAS)])).fetchone()
    if row is None:
        await conn.execute(
            "UPDATE integra.monitor_emails SET motivo = %s WHERE id = %s",
            ("mesma avaliação/reclamação de outro e-mail (lembrete)", email_id))
        await conn.commit()
        return {"resultado": "repetido", "origem": origem, "assunto": e.assunto}
    await conn.commit()

    item["id"] = row["id"]
    if avisar and ctx[origem].get("ativo", True):
        await _avisar(conn, ctx[origem], item, http)
    return {"resultado": "novo", "origem": origem, "item_id": row["id"],
            "critico": item["critico"], "assunto": e.assunto}


async def reprocessar(conn: AsyncConnection, *, http: httpx.AsyncClient | None = None) -> dict:
    """Passa de novo todos os e-mails guardados pelas regras atuais.

    Serve para quando uma regra melhora (ou a primeira amostra real chega):
    o histórico inteiro passa a ser lido do jeito novo. O que a equipe marcou
    (tratado, observação) e a unidade corrigida à mão ficam.
    """
    rel = {"emails": 0, "atualizados": 0, "novos": 0, "ignorados": 0}
    ctx = {"unidades": await unidades_conhecidas(conn), "palavras": await palavras(conn)}
    rows = await (await conn.execute(
        """SELECT e.id, e.bruto, i.id AS item_id
             FROM integra.monitor_emails e
             LEFT JOIN integra.monitor_itens i ON i.email_id = e.id
            WHERE e.bruto IS NOT NULL ORDER BY e.id""")).fetchall()
    for r in rows:
        rel["emails"] += 1
        e = email_bruto.ler(bytes(r["bruto"]))
        origem = regras.origem_de(e)
        item = await _montar_item(conn, origem, e, ctx["unidades"], ctx["palavras"], http) \
            if origem else None
        if item is None:
            rel["ignorados"] += 1
            continue
        if r["item_id"]:
            sets = ", ".join(f"{c} = %s" for c in _COLUNAS)
            try:
                async with conn.transaction():
                    await conn.execute(
                        f"UPDATE integra.monitor_itens SET {sets} WHERE id = %s",
                        [*(item.get(c) for c in _COLUNAS), r["item_id"]])
                rel["atualizados"] += 1
            except Exception:  # o id externo novo colidiu com outro item
                logger.warning("reprocesso: item %s não atualizado", r["item_id"], exc_info=True)
        else:
            novo = await (await conn.execute(
                f"""INSERT INTO integra.monitor_itens (email_id, {", ".join(_COLUNAS)})
                    VALUES (%s, {", ".join(["%s"] * len(_COLUNAS))})
                    ON CONFLICT DO NOTHING RETURNING id""",
                [r["id"], *(item.get(c) for c in _COLUNAS)])).fetchone()
            if novo:
                await conn.execute(
                    "UPDATE integra.monitor_emails SET situacao='processado', motivo=NULL WHERE id=%s",
                    (r["id"],))
                rel["novos"] += 1
        await conn.commit()
    return rel


# --------------------------------- avisos -----------------------------------

def deve_avisar(cfg: dict, item: dict) -> bool:
    regra = cfg.get("aviso") or "negativos"
    if regra == "nenhum" or not (cfg.get("webhook_url") or "").strip():
        return False
    ocorrido = item.get("ocorrido_em")
    if ocorrido and ocorrido < datetime.now(timezone.utc) - timedelta(hours=_JANELA_AVISO_H):
        return False
    if regra == "todos":
        return True
    if regra == "criticos":
        return bool(item.get("critico"))
    return bool(item.get("critico")) or item.get("nivel") == "negativa"


def corpo_aviso(item: dict) -> dict:
    """O que o fluxo do NichoChat recebe. `critico` e `nivel` deixam o fluxo
    rotear (crise para a diretoria, nota baixa para o atendimento) sem
    comparar texto."""
    base = settings.app_url.rstrip("/")
    return {
        "evento": "reputacao_nova",
        "cliente": settings.cliente_nome,
        "origem": item["origem"],
        "plataforma": regras.NOME[item["origem"]],
        "tipo": item["tipo"],
        "unidade": item.get("unidade"),
        "nota": float(item["nota"]) if item.get("nota") is not None else None,
        "nota_maxima": item.get("nota_maxima"),
        "nivel": item.get("nivel"),
        "critico": bool(item.get("critico")),
        "palavras": item.get("palavras") or [],
        "titulo": item.get("titulo"),
        "texto": (item.get("texto") or "")[:1000],
        "autor": item.get("autor"),
        "cidade": item.get("cidade"),
        "link": f"{base}/integracoes?origem={item['origem']}&item={item['id']}",
        "link_plataforma": item.get("link"),
        "ocorrido_em": item["ocorrido_em"].isoformat() if item.get("ocorrido_em") else None,
    }


async def _avisar(conn: AsyncConnection, cfg: dict, item: dict,
                  http: httpx.AsyncClient | None = None) -> bool:
    if not deve_avisar(cfg, item):
        return False
    try:
        cli = http or httpx.AsyncClient(timeout=15)
        try:
            res = await cli.post(cfg["webhook_url"].strip(), json=corpo_aviso(item))
        finally:
            if http is None:
                await cli.aclose()
        if res.status_code >= 300:
            logger.warning("webhook do monitor devolveu %s (item %s)", res.status_code, item["id"])
            return False
    except Exception:
        logger.warning("webhook do monitor falhou (item %s)", item["id"], exc_info=True)
        return False
    await conn.execute("UPDATE integra.monitor_itens SET avisado_em = now() WHERE id = %s",
                       (item["id"],))
    await conn.commit()
    return True


# ------------------------------ arquivos (.eml) ------------------------------

def abrir_arquivos(arquivos: list[tuple[str, bytes]]) -> tuple[list[bytes], list[str]]:
    """.eml, .mbox (exportação do Gmail/Takeout) ou .zip com .eml dentro."""
    brutos: list[bytes] = []
    erros: list[str] = []
    for nome, conteudo in arquivos:
        ext = Path(nome or "").suffix.lower()
        try:
            if ext in (".eml", ".txt", ""):
                brutos.append(conteudo)
            elif ext == ".mbox":
                with tempfile.NamedTemporaryFile(suffix=".mbox") as tmp:
                    tmp.write(conteudo)
                    tmp.flush()
                    for m in mailbox.mbox(tmp.name):
                        brutos.append(m.as_bytes())
            elif ext == ".zip":
                with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
                    for info in z.infolist():
                        if info.filename.lower().endswith(".eml") and info.file_size <= _LIMITE_BRUTO:
                            brutos.append(z.read(info))
            else:
                erros.append(f"{nome}: formato não suportado (use .eml, .mbox ou .zip)")
        except Exception as exc:  # noqa: BLE001
            erros.append(f"{nome}: não foi possível abrir ({exc})")
    return brutos, erros


async def importar(conn: AsyncConnection, arquivos: list[tuple[str, bytes]]) -> dict:
    """E-mails enviados pela tela. Não avisam o NichoChat: é histórico."""
    brutos, erros = abrir_arquivos(arquivos)
    rel = {"lidos": len(brutos), "novos": 0, "repetidos": 0, "ignorados": 0,
           "criticos": 0, "erros": erros}
    ctx: dict = {}
    async with httpx.AsyncClient(timeout=60) as http:
        for b in brutos:
            r = await processar_bruto(conn, b, "upload", avisar=False, http=http, contexto=ctx)
            chave = {"novo": "novos", "repetido": "repetidos", "ignorado": "ignorados"}.get(r["resultado"])
            if chave:
                rel[chave] += 1
            else:
                rel["erros"].append(r.get("motivo") or "erro")
            if r.get("critico"):
                rel["criticos"] += 1
    return rel


# ---------------------------------- IMAP ------------------------------------

def _pasta(nome: str) -> str:
    nome = (nome or "INBOX").strip()
    return f'"{nome}"' if " " in nome and not nome.startswith('"') else nome


def _since(dias: int) -> str:
    d = date.today() - timedelta(days=dias)
    return f"{d.day:02d}-{_MESES_IMAP[d.month - 1]}-{d.year}"


def _cabecalhos(data) -> dict[int, dict]:
    """Resposta do FETCH de cabeçalhos → {uid: {remetente, assunto, message_id}}."""
    saida: dict[int, dict] = {}
    for parte in data or []:
        if not isinstance(parte, tuple) or len(parte) < 2:
            continue
        m = re.search(rb"UID (\d+)", parte[0])
        if not m:
            continue
        h = email.message_from_bytes(parte[1], policy=email.policy.default)
        saida[int(m.group(1))] = {"remetente": str(h.get("from", "")),
                                  "assunto": str(h.get("subject", ""))}
    return saida


def buscar_na_caixa(ultimo_uid: int, uidvalidity: int | None,
                    limite: int = _MAX_POR_PASSADA) -> dict:
    """Uma visita à caixa (bloqueante — roda numa thread).

    Abre em modo leitura (EXAMINE): não marca nada como lido, não move, não
    apaga. Baixa só o cabeçalho de tudo o que é novo e o e-mail inteiro só do
    que parece ser das plataformas — a caixa pode ser compartilhada.
    """
    s = settings
    try:
        cli = imaplib.IMAP4_SSL(s.monitor_imap_host, s.monitor_imap_porta, timeout=60)
    except Exception as exc:
        raise ErroCaixa(f"não foi possível conectar em {s.monitor_imap_host}: {exc}") from exc
    try:
        try:
            cli.login(s.monitor_imap_usuario, s.monitor_imap_senha)
        except imaplib.IMAP4.error as exc:
            raise ErroCaixa(
                "usuário ou senha recusados pela caixa. No Gmail/Google Workspace é "
                "preciso uma senha de app, não a senha normal.") from exc
        tipo, _ = cli.select(_pasta(s.monitor_imap_pasta), readonly=True)
        if tipo != "OK":
            raise ErroCaixa(f"a pasta {s.monitor_imap_pasta!r} não existe nesta caixa")
        _, val = cli.response("UIDVALIDITY")
        validade = int((val or [b"0"])[0] or 0) if val and val[0] else 0
        recomecar = ultimo_uid == 0 or (uidvalidity is not None and validade != uidvalidity)

        if recomecar:
            tipo, data = cli.uid("SEARCH", None, "SINCE", _since(s.monitor_historico_dias))
        else:
            tipo, data = cli.uid("SEARCH", None, "UID", f"{ultimo_uid + 1}:*")
        piso = 0 if recomecar else ultimo_uid
        uids = sorted(int(x) for x in ((data or [b""])[0] or b"").split() if int(x) > piso)
        restam = max(0, len(uids) - limite)
        uids = uids[:limite]

        mensagens: list[dict] = []
        for i in range(0, len(uids), 50):
            lote = uids[i:i + 50]
            tipo, data = cli.uid("FETCH", ",".join(map(str, lote)),
                                 "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
            cab = _cabecalhos(data)
            for uid in lote:
                h = cab.get(uid, {"remetente": "", "assunto": ""})
                bruto = None
                if regras.parece_da_plataforma(h["remetente"], h["assunto"]):
                    tipo, corpo = cli.uid("FETCH", str(uid), "(BODY.PEEK[])")
                    bruto = next((p[1] for p in corpo or [] if isinstance(p, tuple)), None)
                mensagens.append({"uid": uid, **h, "bruto": bruto})
        return {"uidvalidity": validade, "recomecou": recomecar,
                "mensagens": mensagens, "restam": restam}
    finally:
        try:
            cli.logout()
        except Exception:
            pass


async def _tomar_trava(conn: AsyncConnection) -> bool:
    await conn.execute("INSERT INTO integra.monitor_caixa (id) VALUES (true) ON CONFLICT DO NOTHING")
    row = await (await conn.execute(
        f"""UPDATE integra.monitor_caixa SET lendo_desde = now()
             WHERE id AND (lendo_desde IS NULL
                           OR lendo_desde < now() - interval '{_TRAVA_EXPIRA_MIN} minutes')
            RETURNING id""")).fetchone()
    await conn.commit()
    return row is not None


async def ler_caixa(conn: AsyncConnection) -> dict | None:
    """Uma passada pela caixa. None se outra já está rodando."""
    if not settings.monitor_caixa_configurada:
        return {"erro": "caixa de e-mail não configurada"}
    if not await _tomar_trava(conn):
        return None
    resumo = {"vistos": 0, "novos": 0, "repetidos": 0, "ignorados": 0, "fora": 0,
              "criticos": 0, "restam": 0, "erro": None}
    try:
        estado = await (await conn.execute(
            "SELECT uidvalidity, ultimo_uid FROM integra.monitor_caixa WHERE id")).fetchone()
        try:
            achado = await asyncio.to_thread(
                buscar_na_caixa, estado["ultimo_uid"] or 0, estado["uidvalidity"])
        except ErroCaixa as exc:
            resumo["erro"] = str(exc)
            await conn.execute(
                """UPDATE integra.monitor_caixa
                      SET ultimo_erro = %s, ultimo_erro_em = now() WHERE id""", (str(exc),))
            await conn.commit()
            return resumo
        if achado["recomecou"]:
            await conn.execute(
                "UPDATE integra.monitor_caixa SET uidvalidity = %s, ultimo_uid = 0 WHERE id",
                (achado["uidvalidity"],))
        ctx: dict = {}
        async with httpx.AsyncClient(timeout=60) as http:
            for m in achado["mensagens"]:
                resumo["vistos"] += 1
                if m["bruto"] is None:
                    resumo["fora"] += 1
                else:
                    r = await processar_bruto(conn, m["bruto"], "imap", http=http, contexto=ctx)
                    chave = {"novo": "novos", "repetido": "repetidos"}.get(r["resultado"], "ignorados")
                    resumo[chave] += 1
                    resumo["criticos"] += 1 if r.get("critico") else 0
                # Anda o marcador e-mail a e-mail: se o processo cair, a próxima
                # passada continua daqui (e o Message-ID barra repetição).
                await conn.execute(
                    "UPDATE integra.monitor_caixa SET ultimo_uid = greatest(ultimo_uid, %s) WHERE id",
                    (m["uid"],))
                await conn.commit()
        resumo["restam"] = achado["restam"]
        await conn.execute(
            """UPDATE integra.monitor_caixa
                  SET ultima_leitura = now(), ultimo_erro = NULL, ultimo_erro_em = NULL
                WHERE id""")
        await conn.commit()
        logger.info("caixa: %s vistos, %s novos, %s críticos", resumo["vistos"],
                    resumo["novos"], resumo["criticos"])
        return resumo
    finally:
        await conn.rollback()
        await conn.execute("UPDATE integra.monitor_caixa SET lendo_desde = NULL WHERE id")
        await conn.commit()


async def rodar_na_api() -> None:
    from app.db import get_pool  # import tardio: o pool só existe com a API de pé

    try:
        async with get_pool().connection() as conn:
            r = await asyncio.wait_for(ler_caixa(conn), timeout=TEMPO_MAXIMO_SEG)
            # Caixa com muito atraso (primeira leitura de 180 dias): emenda a
            # próxima passada em vez de esperar o intervalo inteiro.
            while r and r.get("restam") and not r.get("erro"):
                r = await asyncio.wait_for(ler_caixa(conn), timeout=TEMPO_MAXIMO_SEG)
    except Exception:
        logger.exception("leitura da caixa do monitor falhou")


async def agendar() -> None:
    """Lê a caixa em intervalo fixo, dentro do processo da API."""
    intervalo = max(2, settings.monitor_intervalo_min)
    logger.info("monitor de reputação: lendo a caixa a cada %s min", intervalo)
    await asyncio.sleep(ESPERA_INICIAL_SEG)
    while True:
        await rodar_na_api()
        await asyncio.sleep(intervalo * 60)


# ------------------------------ consultas tela ------------------------------

async def situacao(conn: AsyncConnection) -> dict:
    caixa = await (await conn.execute(
        """SELECT ultima_leitura, ultimo_erro, ultimo_erro_em, ultimo_uid,
                  (lendo_desde IS NOT NULL
                   AND lendo_desde > now() - interval '15 minutes') AS lendo
             FROM integra.monitor_caixa WHERE id""")).fetchone() or {}
    emails = await (await conn.execute(
        """SELECT count(*) FILTER (WHERE situacao = 'processado') AS processados,
                  count(*) FILTER (WHERE situacao = 'ignorado')   AS ignorados,
                  count(*) FILTER (WHERE situacao = 'erro')       AS erros
             FROM integra.monitor_emails""")).fetchone()
    por_origem = {r["origem"]: dict(r) for r in await (await conn.execute(
        """SELECT origem, count(*) AS itens,
                  count(*) FILTER (WHERE ocorrido_em >= now() - interval '7 days') AS ultimos_7d,
                  count(*) FILTER (WHERE (critico OR nivel = 'negativa') AND tratado_em IS NULL) AS pendentes,
                  max(ocorrido_em) AS ultimo_em
             FROM integra.monitor_itens GROUP BY origem""")).fetchall()}
    usuario = settings.monitor_imap_usuario
    return {
        "caixa": {
            "configurada": settings.monitor_caixa_configurada,
            "endereco": usuario or None,
            "servidor": settings.monitor_imap_host or None,
            "pasta": settings.monitor_imap_pasta,
            "intervalo_min": settings.monitor_intervalo_min,
            "agendada": settings.monitor_caixa_configurada and settings.agente_ligado,
            "ultima_leitura": caixa.get("ultima_leitura"),
            "ultimo_erro": caixa.get("ultimo_erro"),
            "ultimo_erro_em": caixa.get("ultimo_erro_em"),
            "lendo": bool(caixa.get("lendo")),
        },
        "emails": dict(emails),
        "ia": bool(await _chave_ia(conn)),
        "origens": {
            o: {**(por_origem.get(o) or {"itens": 0, "ultimos_7d": 0, "pendentes": 0, "ultimo_em": None}),
                "config": await config(conn, o)}
            for o in ORIGENS
        },
        "palavras": await palavras(conn),
    }


def _semanas(rows: list[dict], inicio: date, fim: date) -> list[dict]:
    """Uma linha por semana do período, com zero onde não houve nada — senão
    o gráfico emenda as semanas com dado e esconde justamente os buracos."""
    por = {r["semana"]: r for r in rows}
    seg = inicio - timedelta(days=inicio.weekday())
    saida = []
    while seg <= fim:
        saida.append(por.get(seg) or {"semana": seg, "total": 0, "negativas": 0,
                                      "positivas": 0, "criticos": 0, "media": None})
        seg += timedelta(days=7)
    return saida


async def painel(conn: AsyncConnection, origem: str, dias: int) -> dict:
    filtro = "origem = %s AND ocorrido_em >= now() - make_interval(days => %s)"
    args = (origem, dias)
    numeros = await (await conn.execute(
        f"""SELECT count(*) AS total,
                   count(*) FILTER (WHERE nivel = 'negativa') AS negativas,
                   count(*) FILTER (WHERE nivel = 'positiva') AS positivas,
                   count(*) FILTER (WHERE critico) AS criticos,
                   count(*) FILTER (WHERE (critico OR nivel = 'negativa') AND tratado_em IS NULL) AS pendentes,
                   round(avg(nota) FILTER (WHERE tipo IN ('avaliacao', 'resultado')), 2) AS media,
                   count(*) FILTER (WHERE ocorrido_em >= now() - interval '7 days') AS ultimos_7d,
                   count(*) FILTER (WHERE tipo = 'reclamacao') AS reclamacoes,
                   count(*) FILTER (WHERE tipo = 'resultado') AS avaliadas,
                   count(*) FILTER (WHERE extraido_por = 'parcial') AS parciais
              FROM integra.monitor_itens WHERE {filtro}""", args)).fetchone()
    semanas = await (await conn.execute(
        f"""SELECT date_trunc('week', ocorrido_em AT TIME ZONE 'America/Sao_Paulo')::date AS semana,
                   count(*) AS total,
                   count(*) FILTER (WHERE nivel = 'negativa') AS negativas,
                   count(*) FILTER (WHERE nivel = 'positiva') AS positivas,
                   count(*) FILTER (WHERE critico) AS criticos,
                   round(avg(nota), 2) AS media
              FROM integra.monitor_itens WHERE {filtro}
             GROUP BY 1 ORDER BY 1""", args)).fetchall()
    unidades = await (await conn.execute(
        f"""SELECT coalesce(unidade, 'Sem unidade') AS unidade, count(*) AS total,
                   count(*) FILTER (WHERE nivel = 'negativa') AS negativas,
                   count(*) FILTER (WHERE critico) AS criticos,
                   round(avg(nota), 2) AS media
              FROM integra.monitor_itens WHERE {filtro}
             GROUP BY 1 ORDER BY total DESC, 1 LIMIT 25""", args)).fetchall()
    palavras_ = await (await conn.execute(
        f"""SELECT p AS palavra, count(*) AS total
              FROM integra.monitor_itens, unnest(palavras) AS p
             WHERE {filtro} GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 15""", args)).fetchall()
    notas = await (await conn.execute(
        f"""SELECT floor(nota)::int AS nota, count(*) AS total
              FROM integra.monitor_itens
             WHERE {filtro} AND nota IS NOT NULL AND tipo IN ('avaliacao', 'resultado')
             GROUP BY 1 ORDER BY 1""", args)).fetchall()
    hoje = (await (await conn.execute(
        "SELECT (now() AT TIME ZONE 'America/Sao_Paulo')::date AS d")).fetchone())["d"]
    return {
        "numeros": dict(numeros),
        "semanas": _semanas([dict(s) for s in semanas], hoje - timedelta(days=dias - 1), hoje)
                   if semanas else [],
        "unidades": [dict(u) for u in unidades],
        "palavras": [dict(p) for p in palavras_],
        "notas": [dict(n) for n in notas],
    }


async def itens(conn: AsyncConnection, origem: str, *, tipo: str | None = None,
                unidade: str | None = None, nivel: str | None = None,
                critico: bool | None = None, pendente: bool | None = None,
                busca: str | None = None, dias: int | None = None,
                page: int = 1, page_size: int = 30) -> dict:
    where = ["i.origem = %s"]
    args: list = [origem]
    if tipo:
        where.append("i.tipo = %s")
        args.append(tipo)
    if unidade:
        where.append("coalesce(i.unidade, 'Sem unidade') = %s")
        args.append(unidade)
    if nivel:
        where.append("i.nivel = %s")
        args.append(nivel)
    if critico is not None:
        where.append("i.critico = %s")
        args.append(critico)
    if pendente:
        where.append("(i.critico OR i.nivel = 'negativa') AND i.tratado_em IS NULL")
    if busca:
        termo = f"%{busca.strip().lower()}%"
        where.append("(lower(coalesce(i.titulo,'')) LIKE %s OR lower(coalesce(i.texto,'')) LIKE %s "
                     "OR lower(coalesce(i.autor,'')) LIKE %s)")
        args += [termo, termo, termo]
    if dias:
        where.append("i.ocorrido_em >= now() - make_interval(days => %s)")
        args.append(dias)
    w = " AND ".join(where)
    total = (await (await conn.execute(
        f"SELECT count(*) AS n FROM integra.monitor_itens i WHERE {w}", args)).fetchone())["n"]
    rows = await (await conn.execute(
        f"""SELECT i.id, i.origem, i.tipo, i.externo_id, i.unidade, i.nota, i.nota_maxima,
                   i.titulo, i.texto, i.autor, i.cidade, i.link, i.ocorrido_em, i.nivel,
                   i.critico, i.palavras, i.extraido_por, i.tratado_em, i.observacao,
                   i.avisado_em, u.email AS tratado_por
              FROM integra.monitor_itens i
              LEFT JOIN app.usuarios u ON u.id = i.tratado_por
             WHERE {w}
             ORDER BY i.ocorrido_em DESC, i.id DESC
             LIMIT %s OFFSET %s""", [*args, page_size, (page - 1) * page_size])).fetchall()
    return {"items": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


async def detalhe(conn: AsyncConnection, item_id: int) -> dict | None:
    row = await (await conn.execute(
        """SELECT i.*, u.email AS tratado_por_email, e.assunto AS email_assunto,
                  e.remetente AS email_remetente, e.via AS email_via, e.bruto
             FROM integra.monitor_itens i
             LEFT JOIN integra.monitor_emails e ON e.id = i.email_id
             LEFT JOIN app.usuarios u ON u.id = i.tratado_por
            WHERE i.id = %s""", (item_id,))).fetchone()
    if row is None:
        return None
    d = dict(row)
    bruto = d.pop("bruto", None)
    # O texto do e-mail original, para conferir o que o leitor extraiu.
    d["email_texto"] = email_bruto.ler(bytes(bruto)).texto[:20000] if bruto else None
    d["tratado_por"] = d.pop("tratado_por_email", None)
    return d


async def marcar(conn: AsyncConnection, item_id: int, campos: dict, usuario_id: str) -> dict | None:
    """Tratado / observação / unidade. Corrigir a unidade de um item do
    Tripadvisor ensina o de-para do local: os próximos já chegam certos."""
    atual = await (await conn.execute(
        "SELECT origem, loja_id FROM integra.monitor_itens WHERE id = %s", (item_id,))).fetchone()
    if atual is None:
        return None
    if "tratado" in campos:
        if campos["tratado"]:
            await conn.execute(
                """UPDATE integra.monitor_itens SET tratado_em = coalesce(tratado_em, now()),
                          tratado_por = coalesce(tratado_por, %s) WHERE id = %s""",
                (usuario_id, item_id))
        else:
            await conn.execute(
                "UPDATE integra.monitor_itens SET tratado_em = NULL, tratado_por = NULL WHERE id = %s",
                (item_id,))
    if "observacao" in campos:
        await conn.execute("UPDATE integra.monitor_itens SET observacao = %s WHERE id = %s",
                           ((campos["observacao"] or "").strip() or None, item_id))
    if "unidade" in campos:
        unidade = (campos["unidade"] or "").strip() or None
        await conn.execute("UPDATE integra.monitor_itens SET unidade = %s WHERE id = %s",
                           (unidade, item_id))
        if unidade and atual["loja_id"]:
            await conn.execute(
                """INSERT INTO integra.monitor_unidades (origem, loja_id, unidade)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (origem, loja_id) DO UPDATE SET unidade = EXCLUDED.unidade""",
                (atual["origem"], atual["loja_id"], unidade))
            # As outras avaliações do mesmo local também passam para a unidade certa.
            await conn.execute(
                """UPDATE integra.monitor_itens SET unidade = %s
                    WHERE origem = %s AND loja_id = %s""",
                (unidade, atual["origem"], atual["loja_id"]))
    return await detalhe(conn, item_id)


async def emails_ignorados(conn: AsyncConnection, limite: int = 50) -> list[dict]:
    rows = await (await conn.execute(
        """SELECT id, origem, remetente, assunto, enviado_em, lido_em, via, situacao, motivo
             FROM integra.monitor_emails
            WHERE situacao <> 'processado' OR motivo IS NOT NULL
            ORDER BY lido_em DESC LIMIT %s""", (limite,))).fetchall()
    return [dict(r) for r in rows]
