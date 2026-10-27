"""Montagem do e-mail que sai: variáveis, rastreio e descadastro.

Cada destinatário recebe um HTML próprio — o mesmo template, mas com as variáveis
substituídas e os links reescritos para o `recipient_id` dele. É isso que permite
saber quem abriu e quem clicou.
"""

import html
import re
from urllib.parse import quote

from app.config import settings

# {{variavel}} com espaços opcionais.
_VAR = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
# href="..." em aspas simples ou duplas.
_HREF = re.compile(r'href=(["\'])(.*?)\1', re.IGNORECASE)


def variaveis_de(contato: dict) -> dict[str, str]:
    """Valores disponíveis no template, a partir da ficha.

    Tudo vira string e é guardado em `recipients.vars` como snapshot: o e-mail
    enviado mostra o que era verdade no momento do disparo, mesmo que a ficha
    mude depois. Um relatório que diverge do que a pessoa recebeu é pior que
    nenhum relatório.

    Acrescentar uma chave aqui a torna disponível como {{chave}} no editor.
    """
    nome = (contato.get("nome") or "").strip()
    primeiro = (contato.get("primeiro_nome") or "").strip() or nome.split(" ")[0]
    return {
        "nome": nome,
        "primeiro_nome": primeiro,
        "email": contato.get("email") or "",
        "canal": contato.get("canal") or "",
        "status": contato.get("status") or "",
        "origem": contato.get("origem") or "",
        # Só parceiros têm empresa; no e-mail de cliente fica vazia.
        "empresa": contato.get("empresa") or "",
    }


def aplicar_variaveis(texto: str, vars_: dict[str, str], escapar: bool = True) -> str:
    """Substitui {{chave}} pelos valores.

    `escapar=True` no HTML: um contato com `<` no nome (acontece, por importação
    torta) quebraria a marcação — ou pior, injetaria tag. No assunto, que é texto
    puro, não se escapa.

    Variável desconhecida vira string vazia, e não fica `{{fulano}}` visível no
    e-mail do cliente.
    """
    def troca(m: re.Match) -> str:
        valor = vars_.get(m.group(1), "")
        return html.escape(valor) if escapar else valor

    return _VAR.sub(troca, texto or "")


def reescrever_links(html_body: str, recipient_id: str) -> str:
    """Troca cada href por /track/click, preservando o destino.

    Só links http(s) são reescritos. `mailto:`, `tel:` e âncoras passam intactos —
    reescrevê-los quebraria o comportamento e não geraria métrica nenhuma.

    O link de descadastro também fica de fora: contabilizar clique em descadastro
    inflaria a taxa de cliques com o oposto de engajamento.
    """
    base = settings.app_url.rstrip("/")

    def troca(m: re.Match) -> str:
        aspas, url = m.group(1), m.group(2)
        if not url.lower().startswith(("http://", "https://")):
            return m.group(0)
        if "/unsubscribe" in url:
            return m.group(0)
        destino = quote(url, safe="")
        return f'href={aspas}{base}/track/click/{recipient_id}?u={destino}{aspas}'

    return _HREF.sub(troca, html_body or "")


# Por que a pessoa está recebendo. O parceiro não é "cadastrado" no cliente —
# dizer isso a quem nunca se cadastrou é o caminho mais curto para o botão de
# spam. O nome vem de CLIENTE_NOME.
def _motivo(lista: str) -> str:
    nome = settings.cliente_nome
    if lista == "parceiros":
        return f"Você recebeu este e-mail porque sua empresa está na lista de parceiros de {nome}."
    return f"Você recebeu este e-mail porque está cadastrado em {nome}."


def _rodape(recipient_id: str, lista: str = "clientes") -> str:
    """Rodapé de descadastro.

    Obrigatório: sem uma saída visível, o destinatário usa o botão "marcar como
    spam" do provedor — que é muito pior, porque conta contra o domínio inteiro.
    """
    base = settings.app_url.rstrip("/")
    motivo = _motivo(lista)
    return (
        '<div style="margin-top:32px;padding-top:16px;border-top:1px solid #e5e5e5;'
        'font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#888;'
        'text-align:center;">'
        f"<p style=\"margin:0 0 6px;\">{motivo}</p>"
        f'<p style="margin:0;"><a href="{base}/unsubscribe?r={recipient_id}" '
        'style="color:#888;text-decoration:underline;">Não quero mais receber</a></p>'
        "</div>"
    )


def _pixel(recipient_id: str) -> str:
    """Pixel de abertura. 1x1 transparente, com alt vazio para leitor de tela."""
    base = settings.app_url.rstrip("/")
    return (
        f'<img src="{base}/track/open/{recipient_id}.gif" width="1" height="1" '
        'alt="" style="display:block;border:0;" />'
    )


def montar(
    html_template: str, assunto: str, vars_: dict[str, str], recipient_id: str,
    lista: str = "clientes",
) -> tuple[str, str]:
    """Devolve (assunto, html) prontos para envio a um destinatário."""
    corpo = aplicar_variaveis(html_template, vars_, escapar=True)
    corpo = reescrever_links(corpo, recipient_id)
    corpo = f"{corpo}{_rodape(recipient_id, lista)}{_pixel(recipient_id)}"
    return aplicar_variaveis(assunto, vars_, escapar=False), corpo


def cabecalhos_unsubscribe(recipient_id: str) -> dict[str, str]:
    """Cabeçalhos de descadastro em um clique (RFC 8058).

    Gmail e Outlook exigem isto de quem envia em volume desde 2024. Sem os dois
    cabeçalhos, a campanha perde entregabilidade mesmo com SPF e DKIM corretos —
    e o provedor pode classificar o remetente como não conforme.

    O `List-Unsubscribe-Post` é o que habilita o botão nativo do cliente de
    e-mail: ele faz um POST direto, sem abrir o navegador.
    """
    base = settings.app_url.rstrip("/")
    return {
        "List-Unsubscribe": f"<{base}/unsubscribe?r={recipient_id}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
