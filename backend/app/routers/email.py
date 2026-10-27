"""Módulo de e-mail: templates, campanhas, prévia de público e disparo.

Duas permissões diferentes de propósito:
  - `campanhas:manage` — montar template, criar campanha, ver relatório;
  - `campanhas:send`   — disparar de verdade (só admin).

O disparo consome cota do plano e não tem desfazer. Separar as permissões evita
que um clique curioso queime 2.500 e-mails.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from psycopg import AsyncConnection
from psycopg.types.json import Json

from app.audit import registrar
from app.auth import require_perm
from app.config import settings
from app.db import get_conn
from app.schemas.email import (
    CampanhaIn, CampanhaOut, CotaOut, DisparoIniciado, ImportacaoParceiros, Lista,
    ParceiroIn, ParceiroOut, ParceiroPatch, ParceirosNumeros, ParceirosPagina,
    PreviaSegmento, TemplateIn, TemplateOut,
)
from app.services import campanhas as svc
from app.services import cota as cota_svc
from app.services import parceiros
from app.services import segmentos
from app.services import storage
from app.services.sender import texto_da_lista

router = APIRouter(prefix="/email", tags=["email"])


# --------------------------------- Cota ------------------------------------

@router.get("/cota", response_model=CotaOut)
async def consultar_cota(
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("campanhas:manage")),
):
    """Quanto do plano já foi usado. A tela mostra antes de deixar disparar."""
    return (await cota_svc.consultar(conn)).como_dict()


@router.post("/uploads")
async def upload_imagem(
    arquivo: UploadFile = File(...),
    _: dict = Depends(require_perm("campanhas:manage")),
):
    """Sobe imagem do editor e devolve a URL pública.

    Pública porque quem busca a imagem é o cliente de e-mail do destinatário, que
    não tem sessão. Por isso também não vale subir aqui nada que não deva ser
    visto por qualquer um com o link.
    """
    try:
        url = await storage.enviar_imagem(
            await arquivo.read(), arquivo.filename or "img",
            arquivo.content_type or "application/octet-stream",
        )
    except storage.ErroUpload as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"url": url}


# ------------------------------- Templates ---------------------------------

@router.get("/templates", response_model=list[TemplateOut])
async def listar_templates(
    lista: Lista | None = None,
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("campanhas:manage")),
):
    """Templates de uma aba (`?lista=clientes|parceiros`); sem filtro, todos."""
    rows = await (await conn.execute(
        """SELECT * FROM email.templates
            WHERE %s::text IS NULL OR lista = %s
            ORDER BY updated_at DESC""", (lista, lista))).fetchall()
    return [dict(r) | {"id": str(r["id"])} for r in rows]


@router.post("/templates", response_model=TemplateOut)
async def criar_template(
    body: TemplateIn,
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("campanhas:manage")),
):
    row = await (await conn.execute(
        """INSERT INTO email.templates (nome, assunto, html, design, lista)
           VALUES (%s, %s, %s, %s, %s) RETURNING *""",
        (body.nome, body.assunto, body.html, Json(body.design) if body.design else None,
         body.lista),
    )).fetchone()
    await registrar(conn, user["id"], "criar_template", f"email.template:{row['id']}",
                    {"lista": body.lista})
    return dict(row) | {"id": str(row["id"])}


@router.put("/templates/{template_id}", response_model=TemplateOut)
async def atualizar_template(
    template_id: str,
    body: TemplateIn,
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("campanhas:manage")),
):
    # A aba do template (lista) não muda na edição: ele nasceu para um público, e
    # trocar por baixo faria a campanha de parceiro usar layout de cliente.
    row = await (await conn.execute(
        """UPDATE email.templates SET nome=%s, assunto=%s, html=%s, design=%s
            WHERE id=%s RETURNING *""",
        (body.nome, body.assunto, body.html,
         Json(body.design) if body.design else None, template_id),
    )).fetchone()
    if row is None:
        raise HTTPException(404, "template não encontrado")
    await registrar(conn, user["id"], "editar_template", f"email.template:{template_id}")
    return dict(row) | {"id": str(row["id"])}


@router.delete("/templates/{template_id}", status_code=204)
async def apagar_template(
    template_id: str,
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("campanhas:manage")),
):
    # Campanha guarda `html_snapshot`, então apagar o template não altera o que já
    # foi enviado — mas a FK impede apagar template em uso por campanha rascunho.
    em_uso = await (await conn.execute(
        "SELECT 1 FROM email.campaigns WHERE template_id=%s LIMIT 1", (template_id,))).fetchone()
    if em_uso:
        raise HTTPException(409, "template usado por uma campanha; não pode ser apagado")
    res = await conn.execute("DELETE FROM email.templates WHERE id=%s", (template_id,))
    if res.rowcount == 0:
        raise HTTPException(404, "template não encontrado")
    await registrar(conn, user["id"], "apagar_template", f"email.template:{template_id}")


# -------------------------------- Segmento ---------------------------------

@router.post("/segmentos/previa", response_model=PreviaSegmento)
async def previa_segmento(
    body: dict,
    lista: Lista = "clientes",
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("campanhas:manage")),
):
    """Quantas pessoas o filtro alcança — e quantas foram barradas, e por quê.

    O segundo número importa tanto quanto o primeiro: sem ele, quem monta a
    campanha vê "300 contatos" na tela de Contatos e "271 destinatários" aqui,
    e conclui que o sistema perdeu gente.
    """
    base = parceiros if lista == "parceiros" else segmentos
    previa = await base.previa(conn, body)
    previa["excluidos"] = await base.contar_excluidos(conn, body)
    return previa


# -------------------------------- Campanhas --------------------------------

@router.get("/campanhas", response_model=list[CampanhaOut])
async def listar_campanhas(
    lista: Lista | None = None,
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("campanhas:manage")),
):
    """Campanhas de uma aba; sem filtro, todas (a visão geral, que marca as de
    parceiro pelo campo `lista`).

    `enviados` é contado AGORA, nos destinatários — o mesmo número do
    relatório. A coluna `email.campaigns.enviados` só é gravada no fim de cada
    leva; durante um envio (ou se a leva morreu no meio, num reinício da API)
    ela mostrava 0 aqui enquanto o relatório já mostrava os que receberam.
    """
    rows = await (await conn.execute(
        """SELECT c.*, t.nome AS template_nome,
                  (SELECT count(*) FROM email.recipients r
                    WHERE r.campaign_id = c.id AND r.status = 'enviado') AS enviados_agora
             FROM email.campaigns c
             LEFT JOIN email.templates t ON t.id = c.template_id
            WHERE %s::text IS NULL OR c.lista = %s
            ORDER BY c.created_at DESC""", (lista, lista))).fetchall()
    saida = []
    for r in rows:
        linha = dict(r)
        linha["enviados"] = linha.pop("enviados_agora")
        saida.append(linha | {"id": str(r["id"])})
    return saida


@router.post("/campanhas", response_model=CampanhaOut)
async def criar_campanha(
    body: CampanhaIn,
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("campanhas:manage")),
):
    seg = body.segmento.model_dump(exclude_none=True)
    base = parceiros if body.lista == "parceiros" else segmentos
    previa = await base.previa(conn, seg)

    # O HTML é congelado na criação: editar o template depois não muda o que esta
    # campanha manda. Sem isso, o relatório descreveria um e-mail que ninguém viu.
    tpl = await (await conn.execute(
        "SELECT html, lista FROM email.templates WHERE id=%s", (body.template_id,))).fetchone()
    if tpl is None:
        raise HTTPException(404, "template não encontrado")
    if tpl["lista"] != body.lista:
        # Cada aba com o seu: template de cliente fala "você que é cliente", e
        # mandá-lo para parceiro (ou o contrário) é erro de quem montou.
        raise HTTPException(
            422, "este template é da aba "
                 f"{'Parceiros' if tpl['lista'] == 'parceiros' else 'Clientes'}; "
                 "escolha um template da mesma aba da campanha")

    row = await (await conn.execute(
        """INSERT INTO email.campaigns
             (nome, template_id, assunto, html_snapshot, segmento, segmento_label,
              remetente, publico, com_email, agendada_para, status, lista)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (body.nome, body.template_id, body.assunto, tpl["html"], Json(seg),
         # O remetente é decidido aqui, pela lista, e gravado na campanha: o
         # relatório mostra por onde saiu mesmo que o .env mude depois.
         previa["label"], texto_da_lista(body.lista), previa["total"], previa["com_email"],
         body.agendada_para,
         # Com data marcada a campanha já nasce 'agendada': é isso que faz o timer
         # encontrá-la. Sem data, fica 'rascunho' e só sai por clique.
         "agendada" if body.agendada_para else "rascunho", body.lista),
    )).fetchone()
    # O público é CONGELADO já na criação, não só no disparo.
    #
    # O caso real: montar na segunda as campanhas de terça, quarta e quinta. Se
    # o público só fosse gerado na hora do envio, nenhuma teria fila ainda — e o
    # filtro "nunca receberam" traria as MESMAS pessoas para as três, porque não
    # haveria nada agendado para excluir. Com a fila criada agora, cada seleção
    # seguinte já enxerga quem está reservado e pega gente nova.
    #
    # É seguro chamar de novo no disparo: a materialização deduplica por
    # (campanha, e-mail) e não reenvia para quem já está na fila.
    await svc.materializar(conn, str(row["id"]))
    await conn.commit()

    await registrar(conn, user["id"], "criar_campanha", f"email.campanha:{row['id']}",
                    {"publico": previa["total"], "segmento": previa["label"],
                     "lista": body.lista})
    return dict(row) | {"id": str(row["id"]), "template_nome": None}


@router.get("/campanhas/{campaign_id}")
async def relatorio_campanha(
    campaign_id: str,
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("campanhas:manage")),
):
    rel = await svc.relatorio(conn, campaign_id)
    if rel is None:
        raise HTTPException(404, "campanha não encontrada")
    rel["campanha"]["id"] = str(rel["campanha"]["id"])
    return rel


@router.get("/campanhas/{campaign_id}/destinatarios")
async def destinatarios(
    campaign_id: str,
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("campanhas:manage")),
):
    """Quem recebeu (ou não), com o motivo.

    É a prova de entrega para mostrar ao cliente, e o lugar onde se descobre por
    que alguém não recebeu — bounce, supressão ou falha temporária.
    """
    rows = await (await conn.execute(
        """SELECT r.id, r.email, r.nome, r.status, r.erro, r.sent_at,
                  count(*) FILTER (WHERE e.tipo='open')  AS aberturas,
                  count(*) FILTER (WHERE e.tipo='click') AS cliques
             FROM email.recipients r
             LEFT JOIN email.events e ON e.recipient_id = r.id
            WHERE r.campaign_id = %s
            GROUP BY r.id
            ORDER BY r.sent_at DESC NULLS LAST, r.created_at""",
        (campaign_id,))).fetchall()
    return [dict(r) | {"id": str(r["id"])} for r in rows]


@router.post("/campanhas/{campaign_id}/enviar", response_model=DisparoIniciado)
async def enviar_campanha(
    campaign_id: str,
    tarefas: BackgroundTasks,
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("campanhas:send")),
):
    """Dispara a campanha. Só admin, e não tem desfazer.

    O envio roda em SEGUNDO PLANO e a resposta volta na hora. Prender o navegador
    até a última mensagem seria inviável: com pausa entre e-mails, uma base de
    10 mil leva horas, e qualquer timeout no caminho derrubaria a conexão no meio
    sem ninguém saber se saiu ou não.

    O que é validado ANTES de responder — campanha já enviada, cota esgotada,
    público vazio — vira erro imediato na tela. O resto acontece em background, e
    o relatório se atualiza sozinho enquanto a campanha está `enviando`.

    Respeita a cota: se não couber tudo agora, manda o que cabe e o timer horário
    continua. Chamar de novo nunca reenvia para quem já recebeu.
    """
    camp = await (
        await conn.execute(
            "SELECT status, agendada_para, "
            "       to_char(agendada_para AT TIME ZONE 'America/Sao_Paulo', "
            "               'DD/MM \"às\" HH24:MI') AS quando "
            "  FROM email.campaigns WHERE id = %s", (campaign_id,)
        )
    ).fetchone()
    if camp is None:
        raise HTTPException(404, "campanha não encontrada")
    if camp["status"] == "enviada":
        raise HTTPException(409, "esta campanha já foi enviada; crie uma nova para reenviar")

    # Campanha AGENDADA não dispara por este botão antes da hora.
    #
    # Aconteceu em produção: a campanha de quarta foi criada com data para o dia
    # seguinte e, 9 segundos depois, a pessoa clicou em "Disparar" por hábito —
    # como faz com as campanhas sem data. O botão mandava na hora, ignorando o
    # agendamento, e 16 pessoas receberam o e-mail de quarta na terça.
    #
    # Agendada sai sozinha pelo timer quando chega a hora. Para antecipar, o
    # caminho é tirar a data da campanha — uma decisão explícita, não um clique.
    if (camp["status"] == "agendada" and camp["agendada_para"] is not None):
        agora = (await (await conn.execute("SELECT now() AS n")).fetchone())["n"]
        if camp["agendada_para"] > agora:
            raise HTTPException(
                409,
                f"esta campanha está agendada para {camp['quando']} e sai sozinha "
                "nesse horário — não é preciso disparar",
            )
    if camp["status"] == "cancelada":
        raise HTTPException(409, "campanha cancelada")

    # Já há disparo em curso? Evita dois processos na mesma campanha — a reserva
    # de lote protegeria, mas é melhor recusar aqui com uma mensagem clara.
    em_curso = await (
        await conn.execute(
            "SELECT 1 FROM email.recipients "
            "WHERE campaign_id = %s AND status = 'processando' LIMIT 1",
            (campaign_id,),
        )
    ).fetchone()
    if em_curso:
        raise HTTPException(409, "já há um envio em andamento nesta campanha")

    cota = await cota_svc.consultar(conn)
    if cota.disponivel <= 0:
        raise HTTPException(429, cota_svc.mensagem_de_bloqueio(cota))

    # Materializa AQUI, ainda no request: assim a resposta já sabe quantos vão
    # receber, e um erro de segmento aparece na hora em vez de sumir no log.
    try:
        await svc.materializar(conn, campaign_id)
        await conn.commit()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    na_fila = (
        await (
            await conn.execute(
                "SELECT count(*) AS n FROM email.recipients "
                "WHERE campaign_id = %s AND status = 'pendente'",
                (campaign_id,),
            )
        ).fetchone()
    )["n"]

    if na_fila == 0:
        raise HTTPException(409, "não há ninguém na fila para receber esta campanha")

    await conn.execute(
        "UPDATE email.campaigns SET status = 'enviando', "
        "started_at = coalesce(started_at, now()) WHERE id = %s",
        (campaign_id,),
    )
    await registrar(conn, user["id"], "disparar_campanha",
                    f"email.campanha:{campaign_id}", {"na_fila": na_fila})
    await conn.commit()

    tarefas.add_task(svc.disparar_em_background, campaign_id, user["id"])

    return {
        "iniciado": True,
        "na_fila": na_fila,
        "cabe_agora": min(na_fila, cota.disponivel),
        "simulado": settings.email_dry_run,
    }


@router.post("/campanhas/{campaign_id}/cancelar", response_model=CampanhaOut)
async def cancelar_campanha(
    campaign_id: str,
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("campanhas:manage")),
):
    """Cancela uma campanha que ainda não terminou.

    O que já saiu não volta — cancelar impede o restante da fila de sair.
    """
    row = await (await conn.execute(
        """UPDATE email.campaigns SET status='cancelada'
            WHERE id=%s AND status IN ('rascunho','agendada','enviando')
            RETURNING *""", (campaign_id,))).fetchone()
    if row is None:
        raise HTTPException(409, "campanha não pode ser cancelada neste estado")
    await registrar(conn, user["id"], "cancelar_campanha", f"email.campanha:{campaign_id}")
    return dict(row) | {"id": str(row["id"]), "template_nome": None}


# -------------------------------- Parceiros --------------------------------
#
# A base da aba Parceiros. Mesmas permissões das campanhas: quem monta campanha
# cuida da lista que ela usa. Disparar continua exigindo `campanhas:send`.

@router.get("/parceiros", response_model=ParceirosPagina)
async def listar_parceiros(
    busca: str | None = None,
    tag: str | None = None,
    situacao: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("campanhas:manage")),
):
    return await parceiros.listar(conn, busca=busca or None, tag=tag or None,
                                  situacao=situacao or None, page=page, page_size=page_size)


@router.get("/parceiros/numeros", response_model=ParceirosNumeros)
async def numeros_parceiros(
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("campanhas:manage")),
):
    return await parceiros.numeros(conn)


@router.get("/parceiros/tags", response_model=list[str])
async def tags_parceiros(
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("campanhas:manage")),
):
    return await parceiros.tags(conn)


@router.post("/parceiros/import", response_model=ImportacaoParceiros)
async def importar_parceiros(
    arquivo: UploadFile = File(...),
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("campanhas:manage")),
):
    """Planilha da base de parceiros (.csv ou .xlsx, primeira linha = cabeçalho).

    Atualiza pelo e-mail: subir a mesma planilha de novo não duplica ninguém.
    """
    nome = arquivo.filename or "planilha"
    try:
        linhas = parceiros.ler_arquivo(await arquivo.read(), nome)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # planilha corrompida, xlsx que não é xlsx
        raise HTTPException(400, f"não foi possível ler o arquivo: {exc}") from exc
    if not linhas:
        raise HTTPException(400, "a planilha está vazia")
    rel = await parceiros.importar(conn, linhas, nome)
    await registrar(conn, user["id"], "importar_parceiros", "email.parceiros",
                    {k: v for k, v in rel.items() if k != "erros"} | {"arquivo": nome})
    return rel


@router.post("/parceiros", response_model=ParceiroOut)
async def criar_parceiro(
    body: ParceiroIn,
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("campanhas:manage")),
):
    try:
        novo = await parceiros.criar(conn, body.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await registrar(conn, user["id"], "criar_parceiro", f"email.parceiro:{novo['id']}")
    return novo


@router.patch("/parceiros/{parceiro_id}", response_model=ParceiroOut)
async def editar_parceiro(
    parceiro_id: int,
    body: ParceiroPatch,
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("campanhas:manage")),
):
    if await parceiros.obter(conn, parceiro_id) is None:
        raise HTTPException(404, "parceiro não encontrado")
    campos = body.model_dump(exclude_unset=True)
    try:
        editado = await parceiros.editar(conn, parceiro_id, campos)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await registrar(conn, user["id"], "editar_parceiro", f"email.parceiro:{parceiro_id}",
                    {"campos": sorted(campos)})
    return editado


@router.delete("/parceiros/{parceiro_id}", status_code=204)
async def excluir_parceiro(
    parceiro_id: int,
    conn: AsyncConnection = Depends(get_conn),
    user: dict = Depends(require_perm("campanhas:manage")),
):
    """Apaga a ficha. Quem tinha descadastrado continua descadastrado."""
    if not await parceiros.excluir(conn, parceiro_id):
        raise HTTPException(404, "parceiro não encontrado")
    await registrar(conn, user["id"], "excluir_parceiro", f"email.parceiro:{parceiro_id}")
