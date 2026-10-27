"""Abre um e-mail (os bytes MIME, como chegam do IMAP ou de um .eml) e devolve
o que o monitor de reputação precisa: quem mandou, assunto, data, o texto
corrido, os links e o texto alternativo das imagens.

Não sabe nada de Tripadvisor nem de Reclame Aqui — isso fica em
`monitor_regras`. Aqui é só transformar um e-mail em texto confiável.

Três cuidados que o e-mail real exige:
  * as plataformas mandam HTML; o texto sai daí, com quebra de linha nos
    blocos, sem CSS nem script;
  * a nota do Tripadvisor costuma estar na IMAGEM das bolhas (no `alt` ou no
    nome do arquivo), não no texto — por isso `alts` e o HTML ficam guardados;
  * e-mail encaminhado: se o original veio anexado (message/rfc822), é ele que
    conta, com o remetente e a data dele.
"""

from __future__ import annotations

import email
import email.policy
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import unquote

_BLOCOS = {"p", "div", "br", "tr", "li", "ul", "ol", "table", "h1", "h2", "h3",
           "h4", "h5", "h6", "blockquote", "section", "article", "header", "footer"}
_IGNORAR = {"style", "script", "head", "title", "noscript"}


@dataclass
class Email:
    message_id: str
    remetente: str
    remetente_nome: str
    assunto: str
    enviado_em: datetime | None
    texto: str
    html: str = ""
    # (texto do link, url) — a url já com os %XX decodificados.
    links: list[tuple[str, str]] = field(default_factory=list)
    alts: list[str] = field(default_factory=list)

    @property
    def tudo(self) -> str:
        """Tudo o que dá para procurar padrão: texto, links, alts e o HTML."""
        return "\n".join([self.assunto, self.texto,
                          *(u for _, u in self.links), *self.alts, self.html])


class _Extrator(HTMLParser):
    """HTML → texto com quebras nos blocos, links e alts de imagem."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.alts: list[str] = []
        self._ignorando = 0
        self._href: str | None = None
        self._texto_link: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in _IGNORAR:
            self._ignorando += 1
        elif tag in _BLOCOS:
            self.partes.append("\n")
        elif tag == "td":
            self.partes.append(" ")
        if tag == "a" and a.get("href"):
            self._href = a["href"]
            self._texto_link = []
        if tag == "img":
            for chave in ("alt", "title"):
                if a.get(chave):
                    self.alts.append(a[chave].strip())
            if a.get("src"):
                # O nome do arquivo também diz a nota ("bubble_40", "ss4.0").
                self.alts.append(a["src"])
        # Classe com a nota ("ui_bubble_rating bubble_40") vale como alt.
        if "bubble" in (a.get("class") or ""):
            self.alts.append(a["class"])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in _IGNORAR and self._ignorando:
            self._ignorando -= 1
        elif tag in _BLOCOS:
            self.partes.append("\n")
        if tag == "a" and self._href is not None:
            self.links.append((" ".join("".join(self._texto_link).split()), self._href))
            self._href = None

    def handle_data(self, data):
        if self._ignorando:
            return
        self.partes.append(data)
        if self._href is not None:
            self._texto_link.append(data)


def html_para_texto(html: str) -> tuple[str, list[tuple[str, str]], list[str]]:
    ex = _Extrator()
    try:
        ex.feed(html)
        ex.close()
    except Exception:  # HTML quebrado: fica o que deu para ler
        pass
    return _limpar("".join(ex.partes)), ex.links, ex.alts


def _limpar(texto: str) -> str:
    """Uma linha por parágrafo, sem espaço sobrando nem linhas vazias seguidas."""
    texto = texto.replace("\xa0", " ").replace("‌", "").replace("​", "")
    linhas = [" ".join(l.split()) for l in texto.splitlines()]
    saida: list[str] = []
    for l in linhas:
        if l or (saida and saida[-1]):
            saida.append(l)
    return "\n".join(saida).strip()


def _desembrulhar(url: str) -> str:
    """Tira o %XX (até duas camadas) dos links de rastreio.

    Os e-mails de plataforma passam todo link por um redirecionador
    ("…/click?url=https%3A%2F%2Fwww.tripadvisor…"). Decodificado, o destino
    aparece dentro dele, e é nele que estão os ids da avaliação.
    """
    atual = (url or "").strip()
    for _ in range(2):
        novo = unquote(atual)
        if novo == atual:
            break
        atual = novo
    return atual.replace("&amp;", "&")


def _corpo(msg: EmailMessage) -> tuple[str, str]:
    """(html, texto puro) da parte de conteúdo."""
    html = texto = ""
    for parte in msg.walk():
        if parte.is_multipart() or parte.get_content_disposition() == "attachment":
            continue
        tipo = parte.get_content_type()
        if tipo not in ("text/html", "text/plain"):
            continue
        try:
            conteudo = parte.get_content()
        except Exception:
            bruto = parte.get_payload(decode=True) or b""
            conteudo = bruto.decode(parte.get_content_charset() or "utf-8", errors="replace")
        if tipo == "text/html" and not html:
            html = conteudo
        elif tipo == "text/plain" and not texto:
            texto = conteudo
    return html, texto


def _anexado(msg: EmailMessage) -> EmailMessage | None:
    """O e-mail original, quando o encaminhamento veio como anexo."""
    for parte in msg.walk():
        if parte.get_content_type() == "message/rfc822":
            interno = parte.get_payload()
            if isinstance(interno, list) and interno:
                interno = interno[0]
            if isinstance(interno, EmailMessage):
                return interno
    return None


def _data(msg: EmailMessage) -> datetime | None:
    try:
        d = parsedate_to_datetime(str(msg.get("date", "")))
    except (TypeError, ValueError, IndexError):
        return None
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def ler(bruto: bytes, *, preferir_anexado: bool = True) -> Email:
    """Os bytes do e-mail → `Email`. Nunca levanta por conteúdo estranho."""
    msg = email.message_from_bytes(bruto, policy=email.policy.default)
    if preferir_anexado:
        interno = _anexado(msg)
        if interno is not None and interno.get("from"):
            externo_id = str(msg.get("message-id", "")).strip()
            lido = ler(interno.as_bytes(), preferir_anexado=False)
            # O Message-ID que vale é o do e-mail que chegou na caixa: o mesmo
            # original encaminhado duas vezes é o mesmo aviso, mas o id do
            # encaminhamento é o que a caixa conhece.
            if externo_id:
                lido.message_id = externo_id
            return lido

    nome, endereco = parseaddr(str(msg.get("from", "")))
    html, texto_puro = _corpo(msg)
    links: list[tuple[str, str]] = []
    alts: list[str] = []
    if html:
        texto, links, alts = html_para_texto(html)
    else:
        texto = _limpar(texto_puro)
    if not html and texto_puro:
        # Texto puro: os links estão soltos no texto.
        links = [("", u) for u in re.findall(r"https?://[^\s<>\"')]+", texto_puro)]
    links = [(t, _desembrulhar(u)) for t, u in links]

    message_id = str(msg.get("message-id", "")).strip()
    if not message_id:
        # Sem Message-ID (acontece em .eml exportado à mão): o próprio conteúdo
        # vira a identidade, para subir o mesmo arquivo duas vezes não duplicar.
        message_id = "sha1:" + hashlib.sha1(bruto).hexdigest()

    return Email(
        message_id=message_id[:500],
        remetente=(endereco or "").strip().lower(),
        remetente_nome=(nome or "").strip(),
        assunto=" ".join(str(msg.get("subject", "")).split()),
        enviado_em=_data(msg),
        texto=texto,
        html=html,
        links=links,
        alts=alts,
    )
