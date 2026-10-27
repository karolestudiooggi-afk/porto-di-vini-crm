"""Renderização da mensagem de cada destinatário.

Três coisas acontecem aqui, e as três são obrigatórias para um envio em volume:

1. **Variáveis** — `{{nome}}` vira o nome da pessoa. O valor sai do snapshot em
   `recipients.vars`, não da ficha atual: assim o relatório de uma campanha
   antiga continua mostrando o que foi realmente enviado, mesmo que a ficha mude
   ou o contato seja apagado depois.

2. **Rastreio** — pixel de abertura e reescrita de links. Sem isso não há
   relatório; com isso é possível saber o que funcionou.

3. **Descadastro** — rodapé visível E cabeçalho `List-Unsubscribe`. Não é
   cortesia: Gmail e Yahoo passaram a exigir descadastro em um clique de quem
   envia em volume, e mensagem sem ele vai direto para spam.
"""

import html
import re
from urllib.parse import quote

from app.config import settings

_VAR = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
_HREF = re.compile(r'href="(https?://[^"]+)"', re.IGNORECASE)


def vars_de_contato(row: dict) -> dict:
    """Snapshot das variáveis disponíveis no template.

    Acrescentar uma chave aqui a torna utilizável como `{{chave}}` no editor.
    Tudo vira string porque o snapshot é guardado como jsonb e reusado no render.
    """
    tags = row.get("tags") or []
    nome = (row.get("nome") or "").strip()
    return {
        "nome": nome,
        # Primeiro nome é o que soa natural numa saudação. Cai para o nome
        # completo, e depois para algo neutro — "Olá, !" é pior que "Olá!".
        "primeiro_nome": (row.get("primeiro_nome") or nome.split(" ")[0] or "").strip(),
        "email": row.get("email") or "",
        "canal": row.get("canal") or "",
        "idioma": row.get("idioma") or "",
        "tags": ", ".join(tags) if isinstance(tags, list) else str(tags or ""),
    }


def aplicar_vars(texto: str, vars_: dict) -> str:
    """Substitui `{{chave}}`. Chave desconhecida vira string vazia.

    Vazio, e não a marcação crua: um `{{nome_do_pet}}` esquecido no template
    apareceria literalmente na caixa de entrada do cliente.

    O valor é escapado: nome com `&` ou `<` (acontece em base importada) quebraria
    o HTML do e-mail.
    """
    return _VAR.sub(lambda m: html.escape(str(vars_.get(m.group(1), ""))), texto or "")


def _base() -> str:
    return settings.app_url.rstrip("/")


def link_descadastro(recipient_id: str) -> str:
    return f"{_base()}/api/unsubscribe?r={quote(recipient_id)}"


def reescrever_links(html_str: str, recipient_id: str) -> str:
    """Passa cada link por /track/click para registrar o clique.

    Links de descadastro e `mailto:` ficam de fora: rastrear o clique de quem
    está saindo é desnecessário, e um redirecionamento a mais entre a pessoa e o
    descadastro é exatamente o tipo de atrito que gera denúncia de spam.
    """
    rid = quote(recipient_id)

    def troca(m: re.Match[str]) -> str:
        url = m.group(1)
        if "/unsubscribe" in url:
            return m.group(0)
        return f'href="{_base()}/api/track/click?r={rid}&u={quote(url, safe="")}"'

    return _HREF.sub(troca, html_str)


def _rodape(recipient_id: str) -> str:
    """Rodapé de descadastro. Discreto, mas legível — cinza claro demais é
    considerado ocultação por alguns filtros anti-spam."""
    url = link_descadastro(recipient_id)
    return (
        '<div style="margin-top:32px;padding-top:16px;border-top:1px solid #e5e5e5;'
        'font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#666;'
        'text-align:center">'
        f'Você recebe este e-mail porque é cliente cadastrado. '
        f'<a href="{url}" style="color:#666;text-decoration:underline">'
        "Descadastrar</a>."
        "</div>"
    )


def _pixel(recipient_id: str) -> str:
    """Pixel de abertura. `width/height=1` e `alt` vazio para não deixar um ícone
    de imagem quebrada visível quando o cliente bloqueia imagens."""
    return (
        f'<img src="{_base()}/api/track/open/{quote(recipient_id)}.gif" '
        'width="1" height="1" alt="" style="display:block;border:0" />'
    )


def montar_html(html_base: str, recipient_id: str, vars_: dict) -> str:
    """HTML final de um destinatário: variáveis, links, rodapé e pixel."""
    corpo = aplicar_vars(html_base, vars_)
    corpo = reescrever_links(corpo, recipient_id)
    return corpo + _rodape(recipient_id) + _pixel(recipient_id)


def montar_texto(html_final: str) -> str:
    """Versão em texto puro.

    Toda mensagem sai como multipart (texto + HTML). Enviar só HTML é sinal
    clássico de spam para os filtros, e alguns clientes de e-mail corporativo
    exibem apenas o texto.
    """
    texto = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", html_final, flags=re.I)
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = html.unescape(texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()
