"""O CRM e o NichoChat no Google: buscar avaliações novas e publicar respostas.

Cada uma num contato do NichoChat:

  - **busca**: `disparar_busca_google` dispara o subfluxo de busca
    (`NICHOCHAT_BUSCA_GOOGLE_SUBFLUXO`) no contato `NICHOCHAT_CONTATO_USER_ID`;
    ele lê o Google e devolve as avaliações novas por POST ao CRM (ver
    leitor_google.py);
  - **resposta**: `enviar_resposta_google`, descrita abaixo, no contato
    `NICHOCHAT_RESPOSTA_CONTATO_USER_ID` (pode ser o mesmo da busca).

Contato que não existe no NichoChat é criado na hora (`POST /subscriber/create`,
só com o telefone e um nome que diz para que serve).

O CRM não publica a resposta direto no Google. Ele entrega ao NichoChat o que a
atendente escreveu, e o subfluxo de resposta (`NICHOCHAT_RESPOSTA_GOOGLE_SUBFLUXO`)
publica pela conexão Google do canal.

Pela API do NichoChat, com a chave do `.env` (nunca pela tela):

  1. acha o contato fixo que carrega os dados (e o cria, se não existir)
     `GET  /subscriber/get-info-by-user-id`
  2. grava nele os três campos numa chamada só
     `PUT  /subscriber/set-user-fields`  {"user_ns", "data": [{"var_ns", "value"}, …]}
       ID_localizacao_resposta = id da unidade no Google (o location id)
       review_id_resposta      = reviewId da avaliação
       resposta_comentario     = o texto da atendente
  3. dispara o subfluxo nesse contato
     `POST /subscriber/send-sub-flow-by-user-id`  {"user_id", "sub_flow_ns"}

A gravação é PUT: com POST o NichoChat responde 405.

Os campos são achados pelo NOME (`GET /flow/user-fields`): se alguém recriar um
deles no NichoChat com o mesmo nome, continua funcionando.

**Um envio por vez.** O contato é o mesmo para todas as respostas. Se duas
saíssem juntas, a segunda poderia trocar os campos antes de o fluxo ler a
primeira, e uma avaliação receberia a resposta da outra. Por isso os envios
passam por uma trava e respeitam um intervalo mínimo
(`NICHOCHAT_RESPOSTA_INTERVALO_SEG`). A trava é do processo: vale porque a API
roda com um worker só (ver docs/systemd/crm-api.service).

O `{"status": "ok"}` do NichoChat quer dizer "fluxo disparado", não "publicado
no Google". Quem confirma é o próprio subfluxo de resposta, depois de publicar:
ele avisa o CRM em /webhooks/nichochat/resposta-google (ver
leitor_google.confirmar_resposta). Sem aviso em 15 minutos, a avaliação volta
para a fila (ver `_encaminhamento` em routers/integracoes.py).
"""

from __future__ import annotations

import asyncio
import time

import httpx

from app.config import settings

# Os campos de contato que o subfluxo de resposta lê — o contrato com o fluxo
# do NichoChat (ver docs/INTEGRACOES.md). A avaliação vai em review_id_resposta,
# campo só da resposta, para não brigar com outros fluxos do canal.
CAMPO_LOCALIZACAO = "ID_localizacao_resposta"
CAMPO_REVIEW = "review_id_resposta"
CAMPO_RESPOSTA = "resposta_comentario"

_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
_TENTATIVAS = 3

# var_ns de cada campo, pelo nome. Esvazia quando uma gravação falha, para um
# campo recriado no NichoChat ser achado de novo.
_var_ns: dict[str, str] = {}


class ErroNichoChat(Exception):
    """O NichoChat recusou ou não respondeu. A mensagem vai para a tela."""

    def __init__(self, mensagem: str, status: int | None = None):
        self.status = status
        super().__init__(mensagem)


class NaoConfigurado(ErroNichoChat):
    def __init__(self) -> None:
        super().__init__(
            "a ligação com o NichoChat não está configurada: faltam "
            "DOMANI_API_URL e DOMANI_API_KEY no .env do servidor")


def _api_configurada() -> bool:
    return bool(settings.domani_api_url.strip() and settings.domani_api_key.strip())


def configurado() -> bool:
    """Dá para entregar resposta do Google ao NichoChat?"""
    return (_api_configurada() and bool(contato_resposta_user_id())
            and bool(settings.nichochat_resposta_google_subfluxo.strip()))


def busca_configurada() -> bool:
    """Dá para disparar a busca de avaliações novas no NichoChat?"""
    return (_api_configurada() and bool(contato_user_id())
            and bool(settings.nichochat_busca_google_subfluxo.strip()))


def _cliente(transporte: httpx.AsyncBaseTransport | None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.domani_api_url.strip().rstrip("/"),
        headers={"Authorization": f"Bearer {settings.domani_api_key.strip()}",
                 "Accept": "application/json"},
        timeout=_TIMEOUT, transport=transporte)


async def _disparar(http: httpx.AsyncClient, user_id: str, sub_flow_ns: str) -> None:
    """`send-sub-flow-by-user-id` no contato.

    Fica marcado na fila mesmo se a resposta se perdeu no caminho: o fluxo pode
    ter rodado, e o próximo uso do contato espera do mesmo jeito.
    """
    try:
        await _chamar(http, "POST", "/subscriber/send-sub-flow-by-user-id",
                      corpo={"user_id": user_id, "sub_flow_ns": sub_flow_ns})
    finally:
        _fila.ultimo = _fila.relogio()


def contato_user_id() -> str:
    """O contato em que o CRM dispara a busca, como a API usa."""
    return _user_id(settings.nichochat_contato_user_id)


def contato_resposta_user_id() -> str:
    """O contato em que o CRM grava a resposta e dispara o subfluxo que publica."""
    return _user_id(settings.nichochat_resposta_contato_user_id)


def _user_id(valor: str) -> str:
    # O NichoChat guarda o contato sem o "+" (5521999990000). Com ele, a busca
    # devolve "subscriber not found" — então tira, venha como vier do .env.
    return (valor or "").strip().lstrip("+")


# ---------------------------------------------------------------------------
# Um envio por vez
# ---------------------------------------------------------------------------

class _Fila:
    """Trava + hora do último envio.

    A trava é criada no primeiro uso dentro do loop que está rodando: um
    asyncio.Lock preso a um loop que já acabou (o de um teste anterior, por
    exemplo) não serve para o próximo.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._trava: asyncio.Lock | None = None
        self.ultimo: float | None = None
        self.relogio = time.monotonic

    def trava(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._trava is None or self._loop is not loop:
            self._loop, self._trava = loop, asyncio.Lock()
        return self._trava

    async def esperar_a_vez(self) -> None:
        if self.ultimo is None:
            return
        falta = settings.nichochat_resposta_intervalo_seg - (self.relogio() - self.ultimo)
        if falta > 0:
            await asyncio.sleep(falta)


_fila = _Fila()


# ---------------------------------------------------------------------------
# Chamadas
# ---------------------------------------------------------------------------

def _mensagem(r: httpx.Response, dados: object) -> str:
    detalhe = ""
    if isinstance(dados, dict):
        detalhe = str(dados.get("message") or dados.get("error") or "").strip()
    if not detalhe:
        detalhe = (r.text or "").strip()[:300]
    base = f"NichoChat respondeu HTTP {r.status_code}"
    if detalhe:
        base += f": {detalhe}"
    if r.status_code in (401, 403):
        base += (" — confira a DOMANI_API_KEY do .env; ela precisa do escopo "
                 "\"Manage Flow\" para disparar subfluxo")
    return base


async def _chamar(http: httpx.AsyncClient, metodo: str, caminho: str, *,
                  params: dict | None = None, corpo: dict | None = None) -> dict:
    r: httpx.Response | None = None
    for tentativa in range(1, _TENTATIVAS + 1):
        try:
            r = await http.request(metodo, caminho, params=params, json=corpo)
        except httpx.TransportError as exc:
            if tentativa == _TENTATIVAS:
                raise ErroNichoChat(
                    f"o NichoChat não respondeu ({exc.__class__.__name__})") from exc
            await asyncio.sleep(1.5 * tentativa)
            continue
        # 429 e 5xx são passageiros. Repetir o disparo do subfluxo, no pior
        # caso, publica de novo o MESMO texto: no Google isso só substitui.
        if (r.status_code == 429 or r.status_code >= 500) and tentativa < _TENTATIVAS:
            await asyncio.sleep(2.0 * tentativa)
            continue
        break

    assert r is not None
    try:
        dados = r.json()
    except ValueError:
        dados = {}
    if r.status_code >= 400:
        raise ErroNichoChat(_mensagem(r, dados), r.status_code)
    if isinstance(dados, dict) and dados.get("status") not in (None, "ok"):
        raise ErroNichoChat(_mensagem(r, dados), r.status_code)
    return dados if isinstance(dados, dict) else {}


async def _info_do_contato(http: httpx.AsyncClient, uid: str) -> dict | None:
    """O contato pelo user_id; None quando o NichoChat diz que não existe."""
    try:
        dados = await _chamar(http, "GET", "/subscriber/get-info-by-user-id",
                              params={"user_id": uid})
    except ErroNichoChat as exc:
        # Só a frase exata: um 404 de rota também diz "not found", e aí o
        # problema é outro.
        if "subscriber not found" in str(exc).lower():
            return None
        raise
    return dados.get("data") or {}


async def _contato(http: httpx.AsyncClient, uid: str, para_que: str) -> str:
    """O user_ns do contato. Se ele não existir no NichoChat, cria — só com o
    telefone e um nome que diz para que serve ("CRM <para_que>")."""
    info = await _info_do_contato(http, uid)
    if info is None:
        try:
            criado = await _chamar(http, "POST", "/subscriber/create", corpo={
                "phone": f"+{uid}", "first_name": "CRM", "last_name": para_que})
        except ErroNichoChat as exc:
            raise ErroNichoChat(
                f"o contato {uid} não existe no NichoChat e não deu para criá-lo: {exc}",
                exc.status) from exc
        info = criado.get("data") if isinstance(criado.get("data"), dict) else {}
        if not info.get("user_ns"):
            info = await _info_do_contato(http, uid) or {}
    user_ns = info.get("user_ns")
    if not user_ns:
        raise ErroNichoChat(f"o NichoChat não devolveu o contato {uid}")
    return user_ns


async def _var_ns_de(http: httpx.AsyncClient, nome: str) -> str:
    if nome in _var_ns:
        return _var_ns[nome]
    # A busca por nome é "contém": "resposta" também traz
    # "Resposta_avaliacao_google". Só vale o nome exato.
    dados = await _chamar(http, "GET", "/flow/user-fields", params={"name": nome, "limit": 100})
    for campo in dados.get("data") or []:
        if (campo.get("name") or "").lower() == nome.lower() and campo.get("var_ns"):
            _var_ns[nome] = campo["var_ns"]
            return campo["var_ns"]
    raise ErroNichoChat(
        f"o campo {nome} não existe no NichoChat (Campos personalizados do contato)")


def _conferir_gravacao(resposta: dict, campos: list[dict]) -> None:
    """O NichoChat devolve em `matched_items` os campos que ele achou.

    Campo que ficou de fora não foi gravado — e disparar o fluxo assim
    publicaria no Google o valor da resposta ANTERIOR. Melhor parar aqui.
    """
    achados = resposta.get("matched_items")
    if not isinstance(achados, list):
        return  # resposta sem a lista: vale o "ok"
    gravados = {item.get("var_ns") for item in achados if isinstance(item, dict)}
    faltou = [c["var_ns"] for c in campos if c["var_ns"] not in gravados]
    if faltou:
        raise ErroNichoChat(
            "o NichoChat não gravou todos os campos no contato "
            f"(faltou {', '.join(faltou)}); o fluxo não foi disparado")


async def enviar_resposta_google(location_id: str, review_id: str, texto: str, *,
                                 transporte: httpx.AsyncBaseTransport | None = None) -> None:
    """Entrega a resposta ao NichoChat e dispara o subfluxo que publica.

    Volta sem erro quando o NichoChat aceitou o disparo. Levanta
    `ErroNichoChat` com a mensagem de lá quando não. `transporte` é para os
    testes simularem a API.
    """
    if not configurado():
        raise NaoConfigurado()
    valores = {
        CAMPO_LOCALIZACAO: (location_id or "").strip(),
        CAMPO_REVIEW: (review_id or "").strip(),
        CAMPO_RESPOSTA: (texto or "").strip(),
    }
    vazios = [nome for nome, valor in valores.items() if not valor]
    if vazios:
        raise ValueError(f"faltou {', '.join(vazios)}")

    async with _cliente(transporte) as http:
        async with _fila.trava():
            await _fila.esperar_a_vez()
            uid = contato_resposta_user_id()
            user_ns = await _contato(http, uid, "Respostas Google")
            campos = [{"var_ns": await _var_ns_de(http, nome), "value": valor}
                      for nome, valor in valores.items()]
            try:
                gravado = await _chamar(http, "PUT", "/subscriber/set-user-fields",
                                        corpo={"user_ns": user_ns, "data": campos})
                _conferir_gravacao(gravado, campos)
            except ErroNichoChat:
                _var_ns.clear()
                raise
            await _disparar(http, uid, settings.nichochat_resposta_google_subfluxo.strip())


async def disparar_busca_google(*, transporte: httpx.AsyncBaseTransport | None = None) -> None:
    """Dispara "Buscar Novos comentários" no contato padrão.

    O subfluxo lê as unidades pela conexão Google do NichoChat e devolve as
    avaliações novas por POST ao CRM (rota /webhooks/nichochat/avaliacoes-google).
    Passa pela mesma fila das respostas: um disparo por vez no NichoChat.
    """
    if not busca_configurada():
        raise NaoConfigurado()
    async with _cliente(transporte) as http:
        async with _fila.trava():
            await _fila.esperar_a_vez()
            uid = contato_user_id()
            await _contato(http, uid, "Busca Google")
            await _disparar(http, uid, settings.nichochat_busca_google_subfluxo.strip())
