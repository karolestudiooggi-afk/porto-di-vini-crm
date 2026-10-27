"""Integrações — avaliações do iFood e do Google Meu Negócio.

Tudo exige sessão, menos o retorno do OAuth do Google (`/google/callback`), que
o navegador abre sem o token do CRM e é validado pelo `state` assinado.

Duas permissões:
  - `integracoes:manage` — ver a fila, pedir sugestão, responder, ver histórico,
    pedir a busca do Google agora;
  - `integracoes:config` — mudar o modo e o prompt, ligar o automático do iFood e
    a conexão direta (opcional) com o Google. Lojas e unidades são cadastradas no
    servidor, por SQL.

Google: as avaliações chegam e as respostas saem pelo NichoChat (ver
leitor_google.py e nichochat.py). A conexão própria do CRM com o Google é
opcional e só serve para conferir uma avaliação na hora em que ela é aberta.

As rotas de leitura (fila, detalhe) devolvem o erro da plataforma DENTRO do
corpo, com status 200, em vez de estourar: a tela mostra a mensagem como veio e
continua de pé. É assim que o painel antigo se comportava, e é o que a
homologação do iFood exige — ações de tela gerando requisição real, inclusive
as que terminam em erro. As rotas que publicam devolvem 400 com a mensagem.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from psycopg import AsyncConnection

from app.audit import registrar
from app.auth import require_perm
from app.config import settings
from app.db import get_conn
from app.schemas.integracoes import ConfigPatch, Origem, RespostaIn
from app.services.integracoes import (
    agente, google, ifood, leitor_google, nichochat, notificar, redator, store,
)

router = APIRouter(prefix="/integracoes", tags=["integracoes"])

_FUSO = ZoneInfo("America/Sao_Paulo")

# Consultas em paralelo ao montar o resumo. Mais que isso esbarra no limite de
# requisições das plataformas; uma por vez faria a tela demorar proporcional ao
# número de lojas.
_PARALELO = 6
_TEMPO_RESUMO_SEG = 20

_ERROS_IFOOD = (ifood.ErroIfood, ifood.NaoConfigurado, httpx.HTTPError)
_ERROS_GOOGLE = (google.ErroGoogle, google.NaoConfigurado, google.NaoConectado, httpx.HTTPError)


def _nao_chegou() -> str:
    """A avaliação que a tela pediu não chegou pelo NichoChat."""
    return ("esta avaliação ainda não chegou do Google. A busca roda a cada "
            f"{leitor_google.intervalo_min()} minutos; para não esperar, use "
            "\"Ler agora\" na visão geral.")


async def _google_direto(conn: AsyncConnection, loja: dict) -> google.Google | None:
    """A conexão DIRETA com o Google, quando ela existe de fato (opcional).

    Não basta a unidade ter `conta_id`: ele sobra de uma conexão antiga mesmo
    depois de desconectar. Sem cliente OAuth configurado e conta conectada, o
    CRM nem tenta — senão cada avaliação aberta mostraria um erro do Google que
    não tem nada a ver com o trabalho da atendente.
    """
    if not loja.get("conta_id"):
        return None
    api = google.Google(conn)
    if not api.configurado or await api.conexao() is None:
        return None
    return api

# Quanto tempo o NichoChat tem para a resposta aparecer no Google. Até lá a
# avaliação sai da fila como "aguardando o Google"; passado isso sem aparecer,
# volta para a fila com aviso — o fluxo de lá travou ou recusou.
_PRAZO_ENCAMINHADA = timedelta(minutes=15)


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------

async def _loja(conn: AsyncConnection, origem: str, loja_id: str) -> dict:
    achada = await store.loja(conn, origem, loja_id)
    if achada is None:
        raise HTTPException(404, "loja não encontrada")
    return achada


def _sem_espaco(texto: str | None) -> str:
    return " ".join((texto or "").split())


def _encaminhamento(av: dict, registro: dict | None,
                    agora: datetime | None = None) -> str | None:
    """Onde está uma resposta que o CRM entregou ao NichoChat (Google).

    - `publicada`: o texto enviado já está no Google;
    - `aguardando`: ainda não apareceu, mas está no prazo;
    - `sem_confirmacao`: passou o prazo e o Google não mostra o texto enviado.

    Nulo quando a avaliação não tem resposta encaminhada.
    """
    if not registro or registro.get("status") != "encaminhada":
        return None
    enviado = _sem_espaco(registro.get("resposta"))
    if enviado and any(_sem_espaco(r.get("texto")) == enviado for r in av.get("respostas") or []):
        return "publicada"
    quando = registro.get("atualizado_em")
    if quando and (agora or datetime.now(timezone.utc)) - quando < _PRAZO_ENCAMINHADA:
        return "aguardando"
    return "sem_confirmacao"


def _item(av: dict, registro: dict | None) -> dict:
    """Junta a avaliação da plataforma com o que o CRM registrou sobre ela.

    `respondida` considera também o nosso registro, porque o iFood demora a
    propagar o status depois da publicação e a tela ficaria contraditória. Pelo
    mesmo motivo, a resposta do Google que acabou de seguir para o NichoChat
    sai da fila enquanto o fluxo de lá publica.
    """
    encaminhamento = _encaminhamento(av, registro)
    respondida = ((not av["pendente"])
                  or bool(registro and registro["status"] == "enviada")
                  or encaminhamento in ("publicada", "aguardando"))
    return {
        **av,
        "respondida": respondida,
        "urgencia": "" if respondida else av.get("urgencia", ""),
        "registro": registro,
        "encaminhamento": encaminhamento,
    }


def _itens(avs: list[dict], vistas: dict[str, dict]) -> list[dict]:
    return [_item(a, vistas.get(a["id"])) for a in avs]


async def _confirmar_publicadas(conn: AsyncConnection, itens: list[dict]) -> None:
    """A resposta encaminhada já está no Google: o registro vira 'enviada'."""
    feitas = [i for i in itens if i.get("encaminhamento") == "publicada"]
    if not feitas:
        return
    await store.confirmar_publicadas(conn, "google", [i["id"] for i in feitas])
    for i in feitas:
        i["registro"] = {**i["registro"], "status": "enviada"}
        i["encaminhamento"] = None


def _fila_de_trabalho(itens: list[dict]) -> list[dict]:
    """Só o que ainda espera resposta — a coluna lateral da tela de responder."""
    return [i for i in itens if not i["respondida"]]


def _dia(valor: str | None, fim: bool = False) -> datetime | None:
    """'2026-10-07' no fuso de Brasília. `fim` leva ao último segundo do dia,
    senão o filtro cortaria o próprio dia escolhido."""
    if not valor:
        return None
    try:
        d = datetime.strptime(valor, "%Y-%m-%d").replace(tzinfo=_FUSO)
    except ValueError:
        return None
    return d + timedelta(days=1, seconds=-1) if fim else d


# ---------------------------------------------------------------------------
# Visão geral, configuração e lojas (comuns às duas origens)
# ---------------------------------------------------------------------------

@router.get("")
async def situacao(conn: AsyncConnection = Depends(get_conn),
                   _: dict = Depends(require_perm("integracoes:manage"))):
    """O estado de cada integração, para a tela saber o que mostrar."""
    cfg_ifood = await store.config(conn, "ifood")
    lojas_ifood = await store.lojas(conn, "ifood")
    lojas_google = await store.lojas(conn, "google")
    api_google = google.Google(conn)
    conexao = await api_google.conexao()

    return {
        "ifood": {
            "configurado": bool(settings.ifood_client_id and settings.ifood_client_secret),
            # Não é segredo (o segredo é o client_secret), e os vídeos de
            # homologação pedem o client_id do aplicativo visível na tela.
            "client_id": settings.ifood_client_id or None,
            "ativo": cfg_ifood["ativo"],
            "modo": cfg_ifood["modo"],
            "lojas": sum(1 for l in lojas_ifood if l["ativo"]),
            # O agente roda dentro da API; isto diz se ele subiu junto.
            "agente_agendado": settings.agente_ligado,
        },
        "google": {
            # O caminho de verdade: tudo passa pelo NichoChat.
            "nichochat": await _situacao_nichochat(conn),
            # Conexão DIRETA com o Google (OAuth) — opcional.
            "configurado": api_google.configurado,
            "conectado": conexao is not None,
            "conta_email": conexao["conta_email"] if conexao else None,
            "conectado_em": conexao["conectado_em"] if conexao else None,
            "lojas": sum(1 for l in lojas_google if l["ativo"]),
            "lojas_sem_conta": sum(1 for l in lojas_google if l["ativo"] and not l["conta_id"]),
            # O endereço que precisa estar cadastrado no Google Cloud. Mostrado
            # na tela para ninguém ter de adivinhar.
            "callback_url": settings.google_callback_url,
        },
        "ia": {
            "configurada": bool(settings.openai_api_key),
            "modelo": settings.openai_model,
        },
    }


async def _situacao_nichochat(conn: AsyncConnection) -> dict:
    """Tudo o que liga o Google ao CRM pelo NichoChat, para a Configuração."""
    disparo = await store.estado_disparo(conn, "google")
    ultimas = await store.execucoes(conn, "google", limite=1)
    base = settings.app_url.rstrip("/")
    return {
        "api_configurada": nichochat.busca_configurada(),
        "entrega_configurada": bool(settings.webhook_google_key.strip()),
        "contato_user_id": nichochat.contato_user_id(),
        "contato_resposta_user_id": nichochat.contato_resposta_user_id(),
        "subfluxo_busca": settings.nichochat_busca_google_subfluxo,
        "subfluxo_resposta": settings.nichochat_resposta_google_subfluxo,
        "intervalo_min": leitor_google.intervalo_min(),
        "busca_agendada": settings.agente_ligado,
        "ultimo_disparo_em": disparo["ultimo_disparo_em"],
        "ultimo_disparo_erro": disparo["ultimo_disparo_erro"],
        "ultima_entrega_em": ultimas[0]["iniciado_em"] if ultimas else None,
        # Os endereços que o fluxo do NichoChat chama. Não são segredo (a chave é).
        "url_entrega": f"{base}/api/webhooks/nichochat/avaliacoes-google",
        "url_confirmacao": f"{base}/api/webhooks/nichochat/resposta-google",
    }


@router.get("/{origem}/config")
async def ler_config(origem: Origem, conn: AsyncConnection = Depends(get_conn),
                     _: dict = Depends(require_perm("integracoes:manage"))):
    cfg = await store.config(conn, origem)
    return {**cfg, "prompt_padrao": redator.prompt_padrao(origem, cfg.get("tom"))}


@router.patch("/{origem}/config")
async def salvar_config(origem: Origem, patch: ConfigPatch,
                        conn: AsyncConnection = Depends(get_conn),
                        user: dict = Depends(require_perm("integracoes:config"))):
    campos = patch.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(422, "nada para atualizar")
    if origem == "google" and campos.get("modo") == "automatico":
        # Não há agente do Google no CRM: as respostas automáticas de lá já
        # saem pelo fluxo do NichoChat, e dois robôs se sobrescreveriam.
        raise HTTPException(422, "no Google a resposta pelo CRM é sempre manual")

    cfg = await store.salvar_config(conn, origem, campos, user["id"])
    # O prompt pode ser longo e a chave do webhook é sensível: a auditoria
    # guarda QUAIS campos mudaram, não o conteúdo.
    await registrar(conn, user["id"], "editar_config_integracao", f"integracoes:{origem}",
                    {"campos": sorted(campos), **{k: campos[k] for k in ("modo", "ativo", "nota_minima") if k in campos}})
    return {**cfg, "prompt_padrao": redator.prompt_padrao(origem, cfg.get("tom"))}


@router.get("/{origem}/lojas")
async def listar_lojas(origem: Origem, conn: AsyncConnection = Depends(get_conn),
                       _: dict = Depends(require_perm("integracoes:manage"))):
    lojas = await store.lojas(conn, origem)
    if origem == "google":
        # O vínculo de cada unidade é a leitura pelo NichoChat: quando chegou a última.
        leituras = await store.leituras_google(conn)
        for l in lojas:
            l["lida_em"] = (leituras.get(l["loja_id"]) or {}).get("lida_em")
    return lojas


# Lojas/unidades: só leitura pela API. O cadastro é no servidor, por migration
# SQL (ver backend/sql/017_lojas_no_servidor.sql) — a tela só mostra.


@router.get("/{origem}/historico")
async def historico(origem: Origem, loja: str | None = None, status: str | None = None,
                    limite: int = Query(default=200, ge=1, le=500),
                    conn: AsyncConnection = Depends(get_conn),
                    _: dict = Depends(require_perm("integracoes:manage"))):
    return await store.historico(conn, origem, loja_id=loja or None,
                                 status=status or None, limite=limite)


@router.get("/{origem}/resumo")
async def resumo(origem: Origem, conn: AsyncConnection = Depends(get_conn),
                 _: dict = Depends(require_perm("integracoes:manage"))):
    """Os números do topo e quantas avaliações esperam resposta em cada loja.

    iFood: consulta a plataforma ao vivo, loja por loja, em paralelo. Google:
    lê do banco o que a leitura automática guardou — abre na hora. Erro numa
    loja não derruba as outras: vem na linha dela.
    """
    numeros = await store.numeros(conn, origem)
    lojas = await store.lojas(conn, origem, apenas_ativas=True)
    linhas = [{"loja_id": l["loja_id"], "nome": l["nome"], "cidade": l["cidade"],
               "pendentes": None, "media": None, "total": None, "parcial": False,
               "erro": None} for l in lojas]
    ultimas = await store.execucoes(conn, origem, limite=1)
    saida = {**numeros, "lojas": linhas, "erro": None,
             "ultima_execucao": ultimas[0] if ultimas else None}
    if origem == "google":
        return await _resumo_google(conn, saida, linhas)
    if not lojas:
        return saida

    # Já respondemos, mas a plataforma ainda não propagou: sai da contagem pelo
    # nosso registro.
    enviadas = {r["review_id"] for r in await (await conn.execute(
        """SELECT review_id FROM integra.avaliacao_respostas
            WHERE origem = 'ifood' AND status = 'enviada'
              AND atualizado_em > now() - interval '7 days'""")).fetchall()}

    vagas = asyncio.Semaphore(_PARALELO)
    api_i = ifood.Ifood(conn)
    try:
        # Token antes do paralelo: depois disso ninguém toca na conexão.
        await api_i.token()
    except _ERROS_IFOOD as exc:
        return {**saida, "erro": str(exc)}

    async def contar(linha: dict) -> None:
        async with vagas:
            try:
                crus = await api_i.listar_pendentes(linha["loja_id"])
                linha["pendentes"] = sum(1 for r in crus if r.get("id") not in enviadas)
            except _ERROS_IFOOD as exc:
                linha["erro"] = str(exc)

    try:
        await asyncio.wait_for(
            asyncio.gather(*(contar(l) for l in linhas)), timeout=_TEMPO_RESUMO_SEG)
    except asyncio.TimeoutError:
        for l in linhas:
            if l["pendentes"] is None and l["erro"] is None:
                l["erro"] = "a plataforma demorou demais para responder"
    return saida


def _falta_no_google() -> str | None:
    """O que impede a leitura do Google (pelo NichoChat) de funcionar, ou None."""
    if not nichochat.busca_configurada():
        return str(nichochat.NaoConfigurado())
    if not settings.webhook_google_key.strip():
        return ("falta WEBHOOK_GOOGLE_KEY no .env do servidor: sem ela o CRM recusa "
                "as avaliações que o NichoChat envia")
    return None


async def _resumo_google(conn: AsyncConnection, saida: dict, linhas: list[dict]) -> dict:
    leituras = await store.leituras_google(conn)
    pendentes = await store.pendentes_google_por_loja(conn, _PRAZO_ENCAMINHADA)
    for linha in linhas:
        lt = leituras.get(linha["loja_id"])
        if lt and lt["lida_em"]:
            linha["pendentes"] = pendentes.get(linha["loja_id"], 0)
            linha["media"] = float(lt["media"]) if lt["media"] is not None else None
            linha["total"] = lt["total"]
        if lt and lt["erro"]:
            linha["erro"] = f"última leitura falhou: {lt['erro']}"
        elif not (lt and lt["lida_em"]):
            linha["erro"] = "aguardando a primeira leitura"
    disparo = await store.estado_disparo(conn, "google")
    saida["erro"] = _falta_no_google() or (
        f"o último pedido de busca ao NichoChat falhou: {disparo['ultimo_disparo_erro']}"
        if disparo["ultimo_disparo_erro"] else None)
    saida["leitura"] = {
        "intervalo_min": leitor_google.intervalo_min(),
        "lendo": await store.rodando(conn, "google"),
        "agendada": settings.agente_ligado,
        "ultimo_disparo_em": disparo["ultimo_disparo_em"],
    }
    return saida


@router.post("/google/ler", status_code=202)
async def google_ler(tarefas: BackgroundTasks,
                     conn: AsyncConnection = Depends(get_conn),
                     user: dict = Depends(require_perm("integracoes:manage"))):
    """Pede a busca ao NichoChat agora, fora do horário. Responde na hora; as
    avaliações chegam quando o fluxo terminar (alguns segundos)."""
    falta = _falta_no_google()
    if falta:
        raise HTTPException(400, falta)
    if await store.rodando(conn, "google"):
        raise HTTPException(409, "já há uma leitura do Google em andamento")
    await registrar(conn, user["id"], "ler_google", "integracoes:google")
    tarefas.add_task(leitor_google.rodar_na_api)
    return {"iniciada": True}


# ---------------------------------------------------------------------------
# iFood: fila, detalhe, sugestão e resposta
# ---------------------------------------------------------------------------

@router.get("/ifood/lojas/{loja_id}/avaliacoes")
async def fila_ifood(loja_id: str, de: str | None = None, ate: str | None = None,
                     tamanho: int | None = None, pagina: int = 1,
                     conn: AsyncConnection = Depends(get_conn),
                     _: dict = Depends(require_perm("integracoes:manage"))):
    loja = await _loja(conn, "ifood", loja_id)
    agora = datetime.now(timezone.utc)
    pagina = max(1, pagina)

    # Janela padrão: a validade da avaliação. Sem dateFrom a API devolveria só
    # os últimos 7 dias. Uma data sozinha não vira requisição inválida: a outra
    # ponta é completada com o padrão.
    inicio = _dia(de) or agora - ifood.VALIDADE
    fim = _dia(ate, fim=True) or agora
    if fim < inicio:
        fim = inicio + ifood.VALIDADE

    # Valor acima do teto segue para a API de propósito: o cenário de
    # homologação é pedir mais de 50 e mostrar o 400 que ela devolve.
    page_size = tamanho if tamanho and tamanho > 0 else ifood.PAGE_SIZE_PADRAO

    saida = {
        "loja": loja,
        "filtro": {"de": de or "", "ate": ate or "", "tamanho": page_size, "pagina": pagina},
        "pagina": {"page": pagina, "size": 0, "total": 0, "page_count": 0},
        "avaliacoes": [],
        "max_por_pagina": ifood.MAX_PAGE_SIZE,
        "erro": None,
    }
    try:
        pg = await ifood.Ifood(conn).listar_pagina(
            loja_id, pagina=pagina, page_size=page_size, de=inicio, ate=fim, contar=True)
    except _ERROS_IFOOD as exc:
        return {**saida, "erro": str(exc)}

    avs = [ifood.normalizar(r, agora) for r in pg["reviews"]]
    vistas = await store.processadas(conn, "ifood", [a["id"] for a in avs])
    saida["pagina"] = {k: pg[k] for k in ("page", "size", "total", "page_count")}
    saida["avaliacoes"] = _itens(avs, vistas)
    return saida


@router.get("/ifood/lojas/{loja_id}/avaliacoes/{review_id}")
async def detalhe_ifood(loja_id: str, review_id: str,
                        conn: AsyncConnection = Depends(get_conn),
                        _: dict = Depends(require_perm("integracoes:manage"))):
    loja = await _loja(conn, "ifood", loja_id)
    api = ifood.Ifood(conn)
    saida = {"loja": loja, "review_id": review_id, "avaliacao": None,
             "fila": [], "erro": None}

    try:
        av = ifood.normalizar(await api.obter(loja_id, review_id))
        vistas = await store.processadas(conn, "ifood", [av["id"] or review_id])
        saida["avaliacao"] = _item(av, vistas.get(av["id"] or review_id))
    except _ERROS_IFOOD as exc:
        # O erro não interrompe a tela: consultar um id inexistente é um cenário
        # exigido na homologação, e o operador precisa ver o retorno.
        saida["erro"] = str(exc)

    # A fila ao lado transforma a tela em superfície de trabalho. Falha aqui
    # não impede responder: sem a coluna, a tela ainda funciona.
    try:
        pend = [ifood.normalizar(r) for r in await api.listar_pendentes(loja_id)]
        vistas = await store.processadas(conn, "ifood", [a["id"] for a in pend])
        saida["fila"] = _fila_de_trabalho(_itens(pend, vistas))
    except _ERROS_IFOOD:
        pass
    return saida


@router.post("/ifood/lojas/{loja_id}/avaliacoes/{review_id}/sugerir")
async def sugerir_ifood(loja_id: str, review_id: str,
                        conn: AsyncConnection = Depends(get_conn),
                        _: dict = Depends(require_perm("integracoes:manage"))):
    loja = await _loja(conn, "ifood", loja_id)
    cfg = await store.config_interna(conn, "ifood")
    try:
        av = ifood.normalizar(await ifood.Ifood(conn).obter(loja_id, review_id))
        texto = await redator.escrever("ifood", cfg, av["nota"], av["comentario"],
                                       store.assinatura_efetiva(loja, cfg))
    except _ERROS_IFOOD as exc:
        raise HTTPException(400, str(exc)) from exc
    except redator.ErroRedator as exc:
        raise HTTPException(400, f"a sugestão não pôde ser gerada: {exc}") from exc
    return {"texto": texto}


@router.post("/ifood/lojas/{loja_id}/avaliacoes/{review_id}/responder")
async def responder_ifood(loja_id: str, review_id: str, body: RespostaIn,
                          conn: AsyncConnection = Depends(get_conn),
                          user: dict = Depends(require_perm("integracoes:manage"))):
    """Publica a resposta no iFood. É definitiva: não dá para editar depois.

    Sem validação local, de propósito: a requisição sai como está e quem valida
    é a API. É assim que o operador vê o erro real.
    """
    loja = await _loja(conn, "ifood", loja_id)
    cfg = await store.config(conn, "ifood")
    api = ifood.Ifood(conn)
    texto = body.texto

    try:
        av = ifood.normalizar(await api.obter(loja_id, review_id))
        av["id"] = av["id"] or review_id
    except _ERROS_IFOOD:
        # Sem o detalhe ainda dá para publicar; só falta nota e comentário para
        # o registro e para o aviso.
        av = None
    registro = av or {"id": review_id}

    try:
        await api.responder_sem_validar(loja_id, review_id, texto)
    except _ERROS_IFOOD as exc:
        if av is not None:
            await store.registrar(conn, "ifood", loja_id, av, resposta=texto,
                                  status="erro", erro=str(exc), via="manual",
                                  usuario_id=user["id"])
            # Commit antes do raise: a exceção desfaz a transação da requisição,
            # e a tentativa que falhou sumiria do histórico.
            await conn.commit()
        raise HTTPException(400, str(exc)) from exc

    await store.registrar(conn, "ifood", loja_id, registro, resposta=texto,
                          status="enviada", via="manual", usuario_id=user["id"])
    await registrar(conn, user["id"], "responder_avaliacao",
                    f"integracoes:ifood:{review_id}", {"loja": loja["nome"]})
    # A resposta já é pública; o registro não pode depender do que vem depois.
    await conn.commit()

    if av is not None:
        await notificar.respondida(cfg, loja, av, texto, "manual")
    return {"ok": True}


# ---------------------------------------------------------------------------
# iFood: agente
# ---------------------------------------------------------------------------

@router.get("/ifood/agente")
async def agente_estado(conn: AsyncConnection = Depends(get_conn),
                        _: dict = Depends(require_perm("integracoes:manage"))):
    return {
        "rodando": await store.rodando(conn),
        # False = a API subiu com WORKER_DESLIGADO; só o "Rodar agora" funciona.
        "agendado": settings.agente_ligado,
        "intervalo_min": agente.INTERVALO_MIN,
        "execucoes": await store.execucoes(conn),
    }


@router.post("/ifood/agente/rodar", status_code=202)
async def agente_rodar(tarefas: BackgroundTasks,
                       conn: AsyncConnection = Depends(get_conn),
                       user: dict = Depends(require_perm("integracoes:manage"))):
    """Dispara uma passada agora. Responde na hora; ela segue em segundo plano,
    senão morreria junto com a requisição e deixaria avaliações pela metade."""
    if await store.rodando(conn):
        raise HTTPException(409, "já há uma passada em andamento")
    await registrar(conn, user["id"], "rodar_agente_ifood", "integracoes:ifood")
    tarefas.add_task(agente.rodar_na_api)
    return {"iniciado": True}


# ---------------------------------------------------------------------------
# Google: conexão
# ---------------------------------------------------------------------------

def _volta(situacao_: str, motivo: str = "") -> RedirectResponse:
    """Devolve o navegador à aba Integrações, com o desfecho na URL."""
    q = {"origem": "google", "google": situacao_}
    if motivo:
        q["motivo"] = motivo[:300]
    return RedirectResponse(
        f"{settings.app_url.rstrip('/')}/integracoes?{urlencode(q)}", status_code=302)


@router.get("/google/oauth/url")
async def google_oauth_url(conn: AsyncConnection = Depends(get_conn),
                           user: dict = Depends(require_perm("integracoes:config"))):
    """O endereço de consentimento do Google, para a tela redirecionar."""
    if not google.Google(conn).configurado:
        raise HTTPException(409, str(google.NaoConfigurado()))
    return {"url": google.url_autorizacao(google.gerar_state(user["id"]))}


@router.get("/google/callback", include_in_schema=False)
async def google_callback(code: str | None = None, state: str | None = None,
                          error: str | None = None,
                          conn: AsyncConnection = Depends(get_conn)):
    """Retorno do consentimento. PÚBLICA: quem chega é o navegador, vindo do
    Google, sem o token do CRM. A prova de origem é o `state` assinado."""
    usuario_id = google.ler_state(state or "")
    if usuario_id is None:
        return _volta("erro", "o pedido de conexão expirou; tente de novo")
    if error or not code:
        return _volta("erro", "o acesso não foi autorizado no Google")

    # O state prova que UM admin iniciou; aqui conferimos que ele ainda é.
    ainda_pode = await (await conn.execute(
        """SELECT 1 FROM app.usuarios u
             JOIN app.papel_permissoes pp ON pp.papel_id = u.papel_id
            WHERE u.id = %s AND u.status = 'ativo'
              AND pp.permissao = 'integracoes:config'""", (usuario_id,))).fetchone()
    if ainda_pode is None:
        return _volta("erro", "sem permissão para conectar a conta")

    api = google.Google(conn)
    try:
        email = await api.trocar_codigo(code, usuario_id)
    except _ERROS_GOOGLE as exc:
        return _volta("erro", str(exc))

    await registrar(conn, usuario_id, "conectar_google", "integracoes:google",
                    {"conta": email})
    await conn.commit()

    # Já tenta vincular as unidades. Se falhar (API ainda não liberada no
    # projeto, por exemplo), a conexão em si está feita e o botão "Sincronizar
    # unidades" mostra o erro com calma.
    try:
        await store.vincular_contas_google(conn, await api.descobrir())
    except _ERROS_GOOGLE:
        await conn.rollback()
    return _volta("conectado")


@router.post("/google/desconectar", status_code=204)
async def google_desconectar(conn: AsyncConnection = Depends(get_conn),
                             user: dict = Depends(require_perm("integracoes:config"))):
    await google.Google(conn).desconectar()
    await registrar(conn, user["id"], "desconectar_google", "integracoes:google")


@router.post("/google/sincronizar")
async def google_sincronizar(conn: AsyncConnection = Depends(get_conn),
                             user: dict = Depends(require_perm("integracoes:config"))):
    """Lê as unidades que a conta conectada administra e vincula as cadastradas.

    Devolve tudo o que achou, marcando o que já está no CRM — é a lista que a
    tela usa para oferecer "adicionar" nas que faltam.
    """
    try:
        achadas = await google.Google(conn).descobrir()
    except _ERROS_GOOGLE as exc:
        raise HTTPException(400, str(exc)) from exc

    vinculadas = await store.vincular_contas_google(conn, achadas)
    cadastradas = {l["loja_id"] for l in await store.lojas(conn, "google")}
    await registrar(conn, user["id"], "sincronizar_google", "integracoes:google",
                    {"achadas": len(achadas), "vinculadas": vinculadas})
    return {
        "vinculadas": vinculadas,
        "achadas": [{**a, "cadastrada": a["loja_id"] in cadastradas} for a in achadas],
        # Cadastrada aqui mas invisível para a conta conectada: quase sempre é
        # a conta errada, ou alguém perdeu o acesso de gerente àquele perfil.
        "nao_encontradas": sorted(cadastradas - {a["loja_id"] for a in achadas}),
    }


# ---------------------------------------------------------------------------
# Google: fila, detalhe, sugestão e resposta
# ---------------------------------------------------------------------------

_POR_PAGINA_GOOGLE = 50


@router.get("/google/lojas/{loja_id}/avaliacoes")
async def fila_google(loja_id: str, filtro: str = "pendentes", page_token: str | None = None,
                      conn: AsyncConnection = Depends(get_conn),
                      _: dict = Depends(require_perm("integracoes:manage"))):
    """A fila da unidade, do que a leitura automática guardou (não consulta o
    Google). `filtro=pendentes`: só as sem resposta; `filtro=todas`: todas.
    `page_token` é o deslocamento da próxima página, devolvido em `proxima`."""
    loja = await _loja(conn, "google", loja_id)
    saida = {"loja": loja, "filtro": filtro, "media": None, "total": 0,
             "avaliacoes": [], "proxima": None, "varridas": 0, "erro": None}

    lt = (await store.leituras_google(conn)).get(loja_id)
    if not (lt and lt["lida_em"]):
        # Nunca lida: diz por quê, em vez de mostrar uma fila vazia enganosa.
        motivo = _falta_no_google() or (
            await store.estado_disparo(conn, "google"))["ultimo_disparo_erro"]
        saida["erro"] = (f"as avaliações desta unidade ainda não chegaram: {motivo}" if motivo else
                         "as avaliações desta unidade ainda não chegaram do Google; a "
                         f"busca roda a cada {leitor_google.intervalo_min()} minutos")
        return saida

    desloc = int(page_token) if page_token and page_token.isdigit() else 0
    avs, n_filtro = await store.avaliacoes_google(
        conn, loja_id, sem_resposta=filtro != "todas",
        limite=_POR_PAGINA_GOOGLE, deslocamento=desloc)
    _, guardadas = await store.avaliacoes_google(conn, loja_id, sem_resposta=False, limite=0)
    vistas = await store.processadas(conn, "google", [a["id"] for a in avs])
    saida.update(
        media=float(lt["media"]) if lt["media"] is not None else None,
        total=lt["total"] or 0,
        varridas=guardadas,
        proxima=str(desloc + _POR_PAGINA_GOOGLE) if desloc + _POR_PAGINA_GOOGLE < n_filtro else None,
        avaliacoes=_itens(avs, vistas),
        lida_em=lt["lida_em"],
    )
    await _confirmar_publicadas(conn, saida["avaliacoes"])
    return saida


async def _fila_lateral_google(conn: AsyncConnection, loja_id: str) -> list[dict]:
    pend, _n = await store.avaliacoes_google(conn, loja_id, sem_resposta=True, limite=100)
    vistas = await store.processadas(conn, "google", [a["id"] for a in pend])
    return _fila_de_trabalho(_itens(pend, vistas))


async def _avaliacao_google(conn: AsyncConnection, loja: dict, review_id: str) -> dict:
    """A avaliação que chegou pelo NichoChat. Se ainda não chegou e houver
    conexão direta com o Google (opcional), busca lá e guarda."""
    av = await store.avaliacao_google(conn, review_id)
    if av is not None:
        return av
    api = await _google_direto(conn, loja)
    if api is None:
        raise HTTPException(404, _nao_chegou())
    try:
        av = google.normalizar(await api.obter(loja["conta_id"], loja["loja_id"], review_id))
    except _ERROS_GOOGLE as exc:
        raise HTTPException(404, _nao_chegou()) from exc
    await store.gravar_google(conn, loja["loja_id"], [av])
    return av


@router.get("/google/lojas/{loja_id}/avaliacoes/{review_id}")
async def detalhe_google(loja_id: str, review_id: str,
                         conn: AsyncConnection = Depends(get_conn),
                         _: dict = Depends(require_perm("integracoes:manage"))):
    """A avaliação como chegou pelo NichoChat.

    Com a conexão direta com o Google (opcional) ligada, ela é conferida lá na
    hora, para a atendente ver se alguém já respondeu; se o Google falhar,
    vale a guardada, sem alarde.
    """
    loja = await _loja(conn, "google", loja_id)
    saida = {"loja": loja, "review_id": review_id, "avaliacao": None,
             "fila": [], "erro": None}

    av = None
    api = await _google_direto(conn, loja)
    if api is not None:
        try:
            av = google.normalizar(await api.obter(loja["conta_id"], loja_id, review_id))
            await store.gravar_google(conn, loja_id, [av])
        except _ERROS_GOOGLE:
            av = None
    if av is None:
        av = await store.avaliacao_google(conn, review_id)
        if av is None:
            saida["erro"] = _nao_chegou()
    if av is not None:
        vistas = await store.processadas(conn, "google", [av["id"]])
        saida["avaliacao"] = _item(av, vistas.get(av["id"]))
        await _confirmar_publicadas(conn, [saida["avaliacao"]])
    saida["fila"] = await _fila_lateral_google(conn, loja_id)
    return saida


@router.post("/google/lojas/{loja_id}/avaliacoes/{review_id}/sugerir")
async def sugerir_google(loja_id: str, review_id: str,
                         conn: AsyncConnection = Depends(get_conn),
                         _: dict = Depends(require_perm("integracoes:manage"))):
    loja = await _loja(conn, "google", loja_id)
    cfg = await store.config_interna(conn, "google")
    av = await _avaliacao_google(conn, loja, review_id)
    try:
        texto = await redator.escrever("google", cfg, av["nota"], av["comentario"],
                                       store.assinatura_efetiva(loja, cfg))
    except redator.ErroRedator as exc:
        raise HTTPException(400, f"a sugestão não pôde ser gerada: {exc}") from exc
    return {"texto": texto}


@router.post("/google/lojas/{loja_id}/avaliacoes/{review_id}/responder")
async def responder_google(loja_id: str, review_id: str, body: RespostaIn,
                           conn: AsyncConnection = Depends(get_conn),
                           user: dict = Depends(require_perm("integracoes:manage"))):
    """Entrega a resposta ao NichoChat, que publica no Google.

    O CRM não publica direto: grava unidade, avaliação e texto no contato do
    NichoChat e dispara o subfluxo "Responder Comentários - Google My Business" (ver
    services/integracoes/nichochat.py). O registro fica 'encaminhada' até a
    resposta aparecer no Google; aí vira 'enviada'. Se já havia resposta, a
    nova substitui.
    """
    loja = await _loja(conn, "google", loja_id)
    try:
        # Texto vazio ou longo demais: nem sai daqui.
        texto = google.validar_resposta(body.texto)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not nichochat.configurado():
        raise HTTPException(400, str(nichochat.NaoConfigurado()))
    # Da leitura automática: publicar não depende de o Google responder agora.
    av = await _avaliacao_google(conn, loja, review_id)

    try:
        await nichochat.enviar_resposta_google(loja_id, av["id"] or review_id, texto)
    except nichochat.ErroNichoChat as exc:
        await store.registrar(conn, "google", loja_id, av, resposta=texto,
                              status="erro", erro=str(exc), via="manual",
                              usuario_id=user["id"])
        await conn.commit()
        raise HTTPException(400, f"a resposta não foi entregue ao NichoChat: {exc}") from exc

    await store.registrar(conn, "google", loja_id, av, resposta=texto,
                          status="encaminhada", via="manual", usuario_id=user["id"])
    await registrar(conn, user["id"], "responder_avaliacao",
                    f"integracoes:google:{review_id}",
                    {"loja": loja["nome"], "via": "nichochat"})
    return {"ok": True, "encaminhada": True}
