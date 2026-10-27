"""Google Meu Negócio (Business Profile) — avaliações.

Três APIs do Google entram aqui, e a divisão é deles, não nossa:

  - Account Management   → quais contas o usuário conectado administra
  - Business Information → as unidades (locations) de cada conta
  - My Business v4       → as avaliações e as respostas

A autenticação é OAuth: um admin clica em "Conectar Google", consente, e o
refresh_token fica em `integra.tokens`. Dali em diante o CRM renova o acesso
sozinho. Não há senha nem chave de conta de serviço — a API de avaliações só
funciona em nome de uma pessoa que administra o perfil.

Diferente do iFood, aqui a resposta **pode ser editada**: publicar de novo
substitui o texto anterior.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import jwt
from psycopg import AsyncConnection

from app.config import settings
from app.services.integracoes.comum import momento

ESCOPO = "https://www.googleapis.com/auth/business.manage"

URL_AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"
URL_REVOGAR = "https://oauth2.googleapis.com/revoke"

API_CONTAS = "https://mybusinessaccountmanagement.googleapis.com/v1"
API_LOCAIS = "https://mybusinessbusinessinformation.googleapis.com/v1"
API_AVALIACOES = "https://mybusiness.googleapis.com/v4"

# Teto de itens por página na listagem de avaliações.
MAX_PAGE_SIZE = 50

# Limite do Google para o texto da resposta, em BYTES (acento conta dois).
MAX_BYTES = 4096

_MARGEM_TOKEN = timedelta(minutes=5)

# O `state` do OAuth vale pouco tempo: é só o intervalo entre clicar em
# "Conectar" e voltar do consentimento.
_VALIDADE_STATE = timedelta(minutes=10)
_AUDIENCIA_STATE = "integracoes-google-oauth"

ESTRELAS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


class ErroGoogle(Exception):
    """Erro devolvido pelo Google, com a mensagem original e uma dica quando dá."""

    def __init__(self, status: int, corpo: str = ""):
        self.status = status
        self.corpo = (corpo or "").strip()
        super().__init__(self._mensagem())

    def _mensagem(self) -> str:
        detalhe = self.corpo
        try:
            erro = json.loads(self.corpo).get("error")
            if isinstance(erro, dict):
                detalhe = erro.get("message") or detalhe
            elif isinstance(erro, str):
                detalhe = json.loads(self.corpo).get("error_description") or erro
        except (ValueError, AttributeError):
            pass

        base = f"Google respondeu HTTP {self.status}"
        if detalhe:
            base += f": {detalhe}"

        baixo = (detalhe or "").lower()
        # Os dois tropeços clássicos de projeto novo no Google Cloud. A mensagem
        # do Google não diz o que fazer; a dica diz.
        if self.status == 429 or "quota" in baixo:
            base += (" — o projeto do Google Cloud provavelmente ainda não teve o "
                     "acesso à Business Profile API aprovado (cota zero).")
        elif "has not been used" in baixo or "is disabled" in baixo:
            base += " — ative esta API no projeto do Google Cloud."
        return base


class NaoConfigurado(Exception):
    def __str__(self) -> str:
        return ("Google não configurado: defina GOOGLE_CLIENT_ID e "
                "GOOGLE_CLIENT_SECRET no .env")


class NaoConectado(Exception):
    def __init__(self, motivo: str = ""):
        self.motivo = motivo
        super().__init__(motivo)

    def __str__(self) -> str:
        return self.motivo or "nenhuma conta Google conectada"


# ---------------------------------------------------------------------------
# OAuth: ida e volta do consentimento
# ---------------------------------------------------------------------------

def gerar_state(usuario_id: str) -> str:
    """Assina quem iniciou a conexão.

    O callback é uma rota pública — o Google redireciona o navegador para ela
    sem o token do CRM. O `state` assinado é o que garante que aquele retorno
    nasceu de um clique de um admin logado, e não de um link montado por fora.
    """
    return jwt.encode(
        {
            "sub": usuario_id,
            "aud": _AUDIENCIA_STATE,
            "exp": datetime.now(timezone.utc) + _VALIDADE_STATE,
        },
        settings.supabase_jwt_secret,
        algorithm="HS256",
    )


def ler_state(state: str) -> str | None:
    """Devolve o id de quem iniciou, ou None se o state não vale."""
    try:
        claims = jwt.decode(
            state, settings.supabase_jwt_secret,
            algorithms=["HS256"], audience=_AUDIENCIA_STATE,
        )
    except jwt.PyJWTError:
        return None
    return claims.get("sub")


def url_autorizacao(state: str) -> str:
    return URL_AUTORIZAR + "?" + urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_callback_url,
        "response_type": "code",
        "scope": f"{ESCOPO} openid email",
        # offline + consent: sem os dois o Google não devolve refresh_token
        # quando a pessoa já autorizou este aplicativo antes.
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })


# ---------------------------------------------------------------------------
# Leitura do que a API devolve
# ---------------------------------------------------------------------------

def original(comentario: str | None) -> str:
    """Tira a tradução automática e fica com o que o cliente escreveu.

    Quando o idioma da avaliação difere do da conta, o Google devolve
    "(Translated by Google) ... (Original) ...". Responder à tradução é
    responder a um texto que o cliente não escreveu.
    """
    if not comentario:
        return ""
    i = comentario.find("(Original)")
    if i >= 0:
        return comentario[i + len("(Original)"):].strip()
    return comentario.replace("(Translated by Google)", "").strip()


def normalizar(raw: dict) -> dict:
    """Traduz a avaliação crua para o formato comum que a tela consome."""
    autor = raw.get("reviewer") or {}
    resposta = raw.get("reviewReply") or {}
    texto_resposta = (resposta.get("comment") or "").strip()
    return {
        "id": raw.get("reviewId") or "",
        "nota": ESTRELAS.get(raw.get("starRating") or "", 0),
        "score": None,
        "comentario": original(raw.get("comment")),
        "autor": None if autor.get("isAnonymous") else (autor.get("displayName") or None),
        "criada_em": momento(raw.get("createTime")),
        "atualizada_em": momento(raw.get("updateTime")),
        "status": None,
        "pendente": not texto_resposta,
        "respostas": [{
            "texto": texto_resposta,
            "de": "MERCHANT",
            "criada_em": momento(resposta.get("updateTime")),
        }] if texto_resposta else [],
        # O Google não tem prazo para responder; estes campos só existem no iFood.
        "prazo_seg": None,
        "prazo_perc": None,
        "urgencia": "",
        "pedido": None,
        "campos": {},
    }


def validar_resposta(texto: str) -> str:
    """O texto como vai ao Google, ou ValueError se ele não aceitaria.

    Vale para os dois caminhos — direto pela API ou pelo NichoChat —, porque
    quem recusa no fim é o Google.
    """
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("escreva a resposta antes de publicar")
    tamanho = len(texto.encode("utf-8"))
    if tamanho > MAX_BYTES:
        raise ValueError(
            f"a resposta passou do limite do Google ({tamanho} de {MAX_BYTES} bytes)")
    return texto


def id_de(nome: str | None) -> str:
    """'accounts/123' → '123'; 'locations/456' → '456'."""
    return (nome or "").rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------

class Google:
    def __init__(self, conn: AsyncConnection, http: httpx.AsyncClient | None = None):
        self.conn = conn
        self._http = http
        # Guardado na instância para que chamadas em paralelo (o resumo das 14
        # unidades) não disputem a mesma conexão de banco.
        self._tok: str | None = None

    @property
    def configurado(self) -> bool:
        return bool(settings.google_client_id and settings.google_client_secret)

    async def _pedir(self, metodo: str, url: str, **kw) -> httpx.Response:
        if self._http is not None:
            return await self._http.request(metodo, url, **kw)
        async with httpx.AsyncClient(timeout=30) as cli:
            return await cli.request(metodo, url, **kw)

    # ------------------------------- conexão -------------------------------

    async def conexao(self) -> dict | None:
        """Quem está conectado, sem expor token nenhum."""
        row = await (await self.conn.execute(
            """SELECT conta_email, conectado_em, refresh_token IS NOT NULL AS ok
                 FROM integra.tokens WHERE origem = 'google'"""
        )).fetchone()
        if not row or not row["ok"]:
            return None
        return {"conta_email": row["conta_email"], "conectado_em": row["conectado_em"]}

    async def trocar_codigo(self, code: str, usuario_id: str | None) -> str | None:
        """Troca o `code` do callback pelos tokens e guarda a conexão."""
        if not self.configurado:
            raise NaoConfigurado()

        res = await self._pedir("POST", URL_TOKEN, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_callback_url,
            "grant_type": "authorization_code",
        })
        if res.status_code != 200:
            raise ErroGoogle(res.status_code, res.text)

        corpo = res.json()
        refresh = corpo.get("refresh_token")
        if not refresh:
            # Acontece quando a conta já tinha autorizado e o consent não foi
            # reapresentado. Sem refresh a conexão morreria em uma hora.
            raise NaoConectado(
                "o Google não devolveu a autorização permanente. Remova o acesso "
                "deste aplicativo em myaccount.google.com/permissions e conecte de novo.")

        email = None
        if corpo.get("id_token"):
            try:
                # Sem verificar a assinatura: o token acabou de chegar do próprio
                # Google por TLS, e só usamos o e-mail para mostrar na tela.
                email = jwt.decode(
                    corpo["id_token"], options={"verify_signature": False}
                ).get("email")
            except jwt.PyJWTError:
                email = None

        expira = datetime.now(timezone.utc) + timedelta(seconds=int(corpo.get("expires_in") or 0))
        await self.conn.execute(
            """INSERT INTO integra.tokens
                 (origem, access_token, expira_em, refresh_token, conta_email,
                  conectado_em, conectado_por)
               VALUES ('google', %s, %s, %s, %s, now(), %s)
               ON CONFLICT (origem) DO UPDATE
                 SET access_token  = EXCLUDED.access_token,
                     expira_em     = EXCLUDED.expira_em,
                     refresh_token = EXCLUDED.refresh_token,
                     conta_email   = EXCLUDED.conta_email,
                     conectado_em  = EXCLUDED.conectado_em,
                     conectado_por = EXCLUDED.conectado_por""",
            (corpo.get("access_token"), expira, refresh, email, usuario_id),
        )
        await self.conn.commit()
        return email

    async def desconectar(self) -> None:
        """Revoga no Google (se der) e apaga a conexão daqui."""
        row = await (await self.conn.execute(
            "SELECT refresh_token FROM integra.tokens WHERE origem = 'google'"
        )).fetchone()
        if row and row["refresh_token"]:
            try:
                await self._pedir("POST", URL_REVOGAR, data={"token": row["refresh_token"]})
            except httpx.HTTPError:
                # A revogação é cortesia. Sem ela o token continua válido no
                # Google, mas sai do nosso banco, que é o que importa aqui.
                pass
        await self.conn.execute("DELETE FROM integra.tokens WHERE origem = 'google'")
        await self.conn.commit()

    async def token(self) -> str:
        if not self.configurado:
            raise NaoConfigurado()
        if self._tok:
            return self._tok

        row = await (await self.conn.execute(
            """SELECT access_token, expira_em, refresh_token
                 FROM integra.tokens WHERE origem = 'google'"""
        )).fetchone()
        if not row or not row["refresh_token"]:
            raise NaoConectado()

        agora = datetime.now(timezone.utc)
        if row["access_token"] and row["expira_em"] \
                and row["expira_em"] - agora > _MARGEM_TOKEN:
            self._tok = row["access_token"]
            return self._tok

        res = await self._pedir("POST", URL_TOKEN, data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": row["refresh_token"],
            "grant_type": "refresh_token",
        })
        if res.status_code in (400, 401) and "invalid_grant" in res.text:
            # A autorização foi revogada ou expirou do lado do Google. Limpar
            # aqui faz a tela mostrar "desconectado" em vez de um erro críptico
            # a cada clique.
            await self.conn.execute(
                "UPDATE integra.tokens SET refresh_token = NULL, access_token = NULL "
                "WHERE origem = 'google'")
            await self.conn.commit()
            raise NaoConectado(
                "a conexão com o Google expirou ou foi revogada — conecte de novo")
        if res.status_code != 200:
            raise ErroGoogle(res.status_code, res.text)

        corpo = res.json()
        tok = corpo["access_token"]
        expira = agora + timedelta(seconds=int(corpo.get("expires_in") or 0))
        await self.conn.execute(
            "UPDATE integra.tokens SET access_token = %s, expira_em = %s "
            "WHERE origem = 'google'", (tok, expira))
        await self.conn.commit()
        self._tok = tok
        return tok

    async def _chamar(self, metodo: str, url: str, *, params: dict | None = None,
                      corpo: dict | None = None) -> dict:
        tok = await self.token()
        res = await self._pedir(
            metodo, url, params=params, json=corpo,
            headers={"Authorization": f"Bearer {tok}"},
        )
        if not 200 <= res.status_code < 300:
            raise ErroGoogle(res.status_code, res.text)
        return res.json() if res.content else {}

    # ------------------------------- unidades ------------------------------

    async def listar_contas(self) -> list[dict]:
        contas, pagina = [], None
        for _ in range(20):
            dados = await self._chamar(
                "GET", f"{API_CONTAS}/accounts",
                params={"pageSize": 20, **({"pageToken": pagina} if pagina else {})})
            contas.extend(dados.get("accounts") or [])
            pagina = dados.get("nextPageToken")
            if not pagina:
                break
        return contas

    async def listar_locais(self, conta: str) -> list[dict]:
        """`conta` no formato 'accounts/123'."""
        locais, pagina = [], None
        for _ in range(50):
            dados = await self._chamar(
                "GET", f"{API_LOCAIS}/{conta}/locations",
                params={
                    "readMask": "name,title,storefrontAddress",
                    "pageSize": 100,
                    **({"pageToken": pagina} if pagina else {}),
                })
            locais.extend(dados.get("locations") or [])
            pagina = dados.get("nextPageToken")
            if not pagina:
                break
        return locais

    async def descobrir(self) -> list[dict]:
        """Todas as unidades que a conta conectada enxerga, com a conta dona.

        É daqui que sai o `conta_id` de cada loja — a API de avaliações exige
        accounts/{conta}/locations/{loja}, e esse par não é adivinhável.
        """
        achadas: dict[str, dict] = {}
        for conta in await self.listar_contas():
            for loc in await self.listar_locais(conta.get("name") or ""):
                loja_id = id_de(loc.get("name"))
                if not loja_id or loja_id in achadas:
                    continue
                endereco = loc.get("storefrontAddress") or {}
                achadas[loja_id] = {
                    "loja_id": loja_id,
                    "conta_id": id_de(conta.get("name")),
                    "conta_nome": conta.get("accountName"),
                    "nome": loc.get("title") or "",
                    "cidade": endereco.get("locality"),
                }
        return list(achadas.values())

    # ------------------------------ avaliações -----------------------------

    async def listar_pagina(self, conta_id: str, loja_id: str, *,
                            page_size: int = MAX_PAGE_SIZE,
                            page_token: str | None = None) -> dict:
        dados = await self._chamar(
            "GET", f"{API_AVALIACOES}/accounts/{conta_id}/locations/{loja_id}/reviews",
            params={
                "pageSize": min(max(1, page_size), MAX_PAGE_SIZE),
                "orderBy": "updateTime desc",
                **({"pageToken": page_token} if page_token else {}),
            })
        return {
            "reviews": dados.get("reviews") or [],
            "media": dados.get("averageRating"),
            "total": dados.get("totalReviewCount") or 0,
            "proxima": dados.get("nextPageToken") or None,
        }

    async def obter(self, conta_id: str, loja_id: str, review_id: str) -> dict:
        return await self._chamar(
            "GET",
            f"{API_AVALIACOES}/accounts/{conta_id}/locations/{loja_id}/reviews/{review_id}")

    async def responder(self, conta_id: str, loja_id: str, review_id: str, texto: str) -> None:
        """Publica a resposta direto pela API do Google. Se já havia uma, substitui.

        A tela NÃO usa mais este caminho: a resposta da atendente sai pelo
        NichoChat (ver nichochat.py). Fica para quando o projeto do Google do
        CRM tiver a cota da API de avaliações liberada.
        """
        texto = validar_resposta(texto)
        await self._chamar(
            "PUT",
            f"{API_AVALIACOES}/accounts/{conta_id}/locations/{loja_id}/reviews/{review_id}/reply",
            corpo={"comment": texto})
