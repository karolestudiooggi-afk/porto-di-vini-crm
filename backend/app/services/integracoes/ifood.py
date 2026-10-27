"""Cliente da Merchant API do iFood — avaliações.

Avaliação não tem webhook: o iFood só entrega evento para pedido. Por isso tudo
aqui é consulta sob demanda, e quem transforma isso em rotina é o `agente`.

Portado do `internal/ifood` do Domani Avaliações (Go). As regras abaixo não são
preferência de estilo — quebrar qualquer uma gera erro da API ou dano permanente,
já que **resposta publicada não pode ser editada nem removida**:

| Regra                                         | Onde está aqui                |
|-----------------------------------------------|-------------------------------|
| Texto entre 10 e 300 caracteres               | `responder`                   |
| Só responder avaliação `NOT_REPLIED`          | `pendente`                    |
| Máximo de 50 itens por página                 | `MAX_PAGE_SIZE`               |
| Sem `dateFrom` a API devolve só 7 dias        | `VALIDADE`, janela de 85 dias |
| Janela `dateFrom`–`dateTo` de até 90 dias     | `VALIDADE`                    |
| `score` vem como decimal                      | `nota`                        |
| Prazo de 5 dias para responder                | `PRAZO_RESPOSTA`, `restante`  |
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from psycopg import AsyncConnection

from app.config import settings
from app.services.integracoes.comum import momento

BASE_URL = "https://merchant-api.ifood.com.br"

# Janela que a loja tem para responder. Passado o prazo a avaliação é publicada
# sem a resposta, e o cliente nunca vê o que a loja escreveu.
PRAZO_RESPOSTA = timedelta(days=5)

# Janela padrão da listagem. O teto aceito entre dateFrom e dateTo é de 90 dias
# exatos, e pedir 90 cheios chega a estourar por arredondamento — 85 dá margem.
VALIDADE = timedelta(days=85)

MIN_CARACTERES = 10
MAX_CARACTERES = 300

# Teto de itens por página. Pedir mais devolve 400.
MAX_PAGE_SIZE = 50
PAGE_SIZE_PADRAO = 20
_MAX_PAGINAS = 40

# Margem para o token não expirar no meio de uma passada.
_MARGEM_TOKEN = timedelta(minutes=10)


class ErroIfood(Exception):
    """Erro devolvido pelo iFood, com o status e o corpo originais.

    A tela mostra a mensagem como veio. É o que a homologação do iFood exige das
    ações de tela, e é também o que ajuda a entender um erro de verdade.
    """

    def __init__(self, status: int, corpo: str = ""):
        self.status = status
        self.corpo = (corpo or "").strip()
        super().__init__(
            f"iFood respondeu HTTP {status}: {self.corpo}" if self.corpo
            else f"iFood respondeu HTTP {status}")


class SemPermissao(ErroIfood):
    """403: a loja ainda não autorizou o aplicativo no Portal do Parceiro."""

    def __init__(self, corpo: str = ""):
        super().__init__(403, corpo)

    def __str__(self) -> str:
        return "a loja não autorizou este aplicativo no Portal do Parceiro (HTTP 403)"


class NaoEncontrada(ErroIfood):
    def __init__(self):
        super().__init__(404)

    def __str__(self) -> str:
        return "iFood respondeu HTTP 404: avaliação não encontrada para este id."


class NaoConfigurado(Exception):
    def __str__(self) -> str:
        return "iFood não configurado: defina IFOOD_CLIENT_ID e IFOOD_CLIENT_SECRET no .env"


# ---------------------------------------------------------------------------
# Leitura tolerante do que a API devolve
# ---------------------------------------------------------------------------

def nota(score) -> int:
    """Arredonda o score para exibição. A API devolve decimal.

    `floor(x + 0.5)` e não `round`: o round do Python arredonda 2.5 para 2
    (bancário), e o painel antigo mostrava 3.
    """
    try:
        return int(math.floor(float(score) + 0.5))
    except (TypeError, ValueError):
        return 0


def respostas_da_loja(raw: dict) -> list[dict]:
    """O que a loja já escreveu, em qualquer versão da API (V1 ou V2)."""
    saida = []
    for rep in raw.get("replies") or []:
        de = rep.get("from") or ""
        if de in ("", "MERCHANT"):
            saida.append({
                "texto": rep.get("text") or "",
                "de": de or "MERCHANT",
                "criada_em": momento(rep.get("createdAt")),
            })
    if not saida and (raw.get("reply") or "").strip():
        saida.append({"texto": raw["reply"], "de": "MERCHANT", "criada_em": None})
    return saida


def pendente(raw: dict) -> bool:
    """A avaliação ainda aceita resposta?

    Responder uma já publicada devolve 422 e não há como desfazer.
    """
    status = raw.get("status") or ""
    if raw.get("discarded") or status == "DISCARDED":
        return False
    if status:
        return status == "NOT_REPLIED"
    # V1 não traz status: avaliação já respondida vem com reply.
    return not respostas_da_loja(raw)


def restante(criada_em: datetime | None, agora: datetime | None = None) -> timedelta:
    """Quanto sobra do prazo de resposta."""
    if criada_em is None:
        return PRAZO_RESPOSTA
    agora = agora or datetime.now(timezone.utc)
    sobra = criada_em + PRAZO_RESPOSTA - agora
    return sobra if sobra > timedelta(0) else timedelta(0)


def urgencia(sobra: timedelta, respondida: bool) -> str:
    """Faixa de prazo que a espinha colorida da fila usa."""
    if respondida:
        return ""
    if sobra < timedelta(hours=24):
        return "quente"
    if sobra < timedelta(hours=48):
        return "morno"
    return "frio"


def normalizar(raw: dict, agora: datetime | None = None) -> dict:
    """Traduz a avaliação crua para o formato comum que a tela consome."""
    criada = momento(raw.get("createdAt"))
    pedido = raw.get("order") or {}
    sobra = restante(criada, agora)
    esta_pendente = pendente(raw)
    usado = PRAZO_RESPOSTA - sobra
    return {
        "id": raw.get("id") or "",
        "nota": nota(raw.get("score")),
        "score": raw.get("score"),
        "comentario": (raw.get("comment") or "").strip(),
        "autor": None,  # o iFood não identifica quem avaliou
        "criada_em": criada,
        "atualizada_em": None,
        "status": raw.get("status") or None,
        "pendente": esta_pendente,
        "respostas": respostas_da_loja(raw),
        "prazo_seg": int(sobra.total_seconds()),
        "prazo_perc": max(0, min(100, int(usado / PRAZO_RESPOSTA * 100))),
        "urgencia": urgencia(sobra, not esta_pendente),
        "pedido": pedido.get("shortId") or None,
        "campos": {
            "pedido_id": pedido.get("id"),
            "pedido_em": momento(pedido.get("createdAt")),
            "questionario": raw.get("surveyId"),
            "descartada": bool(raw.get("discarded")),
            "moderada": bool(raw.get("moderated")),
            "publicada": bool(raw.get("published")),
            "visibilidade": raw.get("visibility"),
            "versao": raw.get("version"),
        },
    }


def montar_query(*, pagina: int = 1, page_size: int = 0, de: datetime | None = None,
                 ate: datetime | None = None, contar: bool = False) -> str:
    """Monta a query da listagem.

    `page_size` acima do teto NÃO é corrigido, de propósito: um dos cenários de
    homologação é pedir mais de 50 e mostrar o 400 que a API devolve.
    """
    q: dict[str, str] = {"page": str(max(1, pagina))}
    if page_size > 0:
        q["pageSize"] = str(page_size)
    if de is not None:
        q["dateFrom"] = de.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if ate is not None:
        q["dateTo"] = ate.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if contar:
        q["addCount"] = "true"
    return urlencode(q)


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------

class Ifood:
    """Uma instância por requisição (ou por passada do agente).

    Recebe a conexão porque o token mora no banco: a API pode reiniciar a
    qualquer momento, o token vale 6 horas, e o agente roda em outro processo.
    """

    def __init__(self, conn: AsyncConnection, http: httpx.AsyncClient | None = None):
        self.conn = conn
        self._http = http
        self.client_id = settings.ifood_client_id
        self._segredo = settings.ifood_client_secret
        # Guardado na instância para que chamadas em paralelo (a contagem de
        # pendentes de várias lojas) não disputem a mesma conexão de banco.
        # O vencimento vem junto: uma passada dura até 10 minutos, a mesma
        # margem do token, e sem reconferir o fim da passada sairia com um
        # token morto — gerando 401 em série bem onde ninguém está olhando.
        self._tok: str | None = None
        self._tok_expira: datetime | None = None

    @property
    def configurado(self) -> bool:
        return bool(self.client_id and self._segredo)

    async def _pedir(self, metodo: str, url: str, **kw) -> httpx.Response:
        if self._http is not None:
            return await self._http.request(metodo, url, **kw)
        async with httpx.AsyncClient(timeout=30) as cli:
            return await cli.request(metodo, url, **kw)

    async def token(self) -> str:
        """Access token válido. Dura 6h e não vem refresh — renova sozinho."""
        if not self.configurado:
            raise NaoConfigurado()

        agora = datetime.now(timezone.utc)
        if self._tok and self._tok_expira and self._tok_expira - agora > _MARGEM_TOKEN:
            return self._tok

        row = await (await self.conn.execute(
            "SELECT access_token, expira_em FROM integra.tokens WHERE origem = 'ifood'"
        )).fetchone()
        if row and row["access_token"] and row["expira_em"] \
                and row["expira_em"] - agora > _MARGEM_TOKEN:
            self._tok = row["access_token"]
            self._tok_expira = row["expira_em"]
            return self._tok

        res = await self._pedir(
            "POST", f"{BASE_URL}/authentication/v1.0/oauth/token",
            data={
                "grantType": "client_credentials",
                "clientId": self.client_id,
                "clientSecret": self._segredo,
            },
        )
        if res.status_code != 200:
            raise ErroIfood(res.status_code, res.text)

        corpo = res.json()
        tok = corpo["accessToken"]
        expira = agora + timedelta(seconds=int(corpo.get("expiresIn") or 0))
        await self.conn.execute(
            """INSERT INTO integra.tokens (origem, access_token, expira_em)
               VALUES ('ifood', %s, %s)
               ON CONFLICT (origem) DO UPDATE
                 SET access_token = EXCLUDED.access_token,
                     expira_em    = EXCLUDED.expira_em""",
            (tok, expira),
        )
        # Commit já: se a requisição que pediu o token terminar em erro (e a do
        # iFood termina, com frequência), o rollback levaria o token junto e a
        # próxima chamada pediria outro à toa.
        await self.conn.commit()
        self._tok = tok
        self._tok_expira = expira
        return tok

    async def _chamar(self, metodo: str, caminho: str, corpo: dict | None = None) -> httpx.Response:
        tok = await self.token()
        return await self._pedir(
            metodo, BASE_URL + caminho, json=corpo,
            headers={"Authorization": f"Bearer {tok}"},
        )

    async def listar_pagina(self, merchant_id: str, *, pagina: int = 1,
                            page_size: int = PAGE_SIZE_PADRAO,
                            de: datetime | None = None, ate: datetime | None = None,
                            contar: bool = False) -> dict:
        """Uma página crua, preservando o erro da API."""
        query = montar_query(pagina=pagina, page_size=page_size, de=de, ate=ate, contar=contar)
        res = await self._chamar("GET", f"/review/v2.0/merchants/{merchant_id}/reviews?{query}")
        if res.status_code == 403:
            raise SemPermissao(res.text)
        if res.status_code != 200:
            raise ErroIfood(res.status_code, res.text)
        dados = res.json() or {}
        return {
            "page": dados.get("page") or pagina,
            "size": dados.get("size") or 0,
            "total": dados.get("total") or 0,
            "page_count": dados.get("pageCount") or 0,
            "reviews": dados.get("reviews") or [],
        }

    async def listar_avaliacoes(self, merchant_id: str) -> list[dict]:
        """Percorre todas as páginas dentro da janela de validade.

        Sem dateFrom a API devolveria só os últimos 7 dias, e o agente perderia
        avaliação antiga ainda dentro do prazo.
        """
        agora = datetime.now(timezone.utc)
        todas: list[dict] = []
        for p in range(1, _MAX_PAGINAS + 1):
            pg = await self.listar_pagina(
                merchant_id, pagina=p, page_size=MAX_PAGE_SIZE,
                de=agora - VALIDADE, ate=agora,
            )
            todas.extend(pg["reviews"])
            if len(pg["reviews"]) < MAX_PAGE_SIZE:
                break
            await asyncio.sleep(0.3)
        return todas

    async def listar_pendentes(self, merchant_id: str) -> list[dict]:
        return [r for r in await self.listar_avaliacoes(merchant_id) if pendente(r)]

    async def obter(self, merchant_id: str, review_id: str) -> dict:
        """Detalhe de uma avaliação.

        O 404 sobe como `NaoEncontrada` em vez de ser mascarado: consultar um id
        inexistente e ver o erro é um dos cenários de homologação.
        """
        res = await self._chamar(
            "GET", f"/review/v2.0/merchants/{merchant_id}/reviews/{review_id}")
        if res.status_code == 404:
            raise NaoEncontrada()
        if res.status_code == 403:
            raise SemPermissao(res.text)
        if res.status_code != 200:
            raise ErroIfood(res.status_code, res.text)
        return res.json() or {}

    async def responder(self, merchant_id: str, review_id: str, texto: str) -> None:
        """Valida o tamanho antes de chamar a API.

        É a versão do agente, onde não há ninguém para ler a mensagem de erro.
        """
        n = len(texto)
        if n < MIN_CARACTERES or n > MAX_CARACTERES:
            raise ValueError(
                f"a resposta precisa ter entre {MIN_CARACTERES} e {MAX_CARACTERES} "
                f"caracteres, tem {n}")
        await self.responder_sem_validar(merchant_id, review_id, texto)

    async def responder_sem_validar(self, merchant_id: str, review_id: str, texto: str) -> None:
        """Envia o texto como está e deixa a API decidir.

        A tela usa esta versão, para que a validação mostrada seja a do iFood,
        com requisição real acontecendo — e não um bloqueio local.
        """
        res = await self._chamar(
            "POST", f"/review/v2.0/merchants/{merchant_id}/reviews/{review_id}/answers",
            {"text": texto},
        )
        if not 200 <= res.status_code < 300:
            raise ErroIfood(res.status_code, res.text)
