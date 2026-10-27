"""Renderização: variáveis, reescrita de links, rodapé e cabeçalhos.

São funções puras — rodam sem banco e sem SMTP. É onde moram as regras que, se
quebrarem, chegam ao cliente final: link torto, nome com HTML, descadastro sumido.
"""

import pytest

from app.services import render


def test_substitui_variaveis():
    out = render.aplicar_variaveis("Olá {{primeiro_nome}}!", {"primeiro_nome": "Ana"})
    assert out == "Olá Ana!"


def test_variavel_desconhecida_vira_vazio():
    """Melhor um espaço vazio que `{{fulano}}` visível na caixa do cliente."""
    assert render.aplicar_variaveis("Oi {{fulano}}", {}) == "Oi "


def test_escapa_html_do_contato():
    """Nome com `<` não pode quebrar a marcação nem injetar tag."""
    out = render.aplicar_variaveis("<p>{{nome}}</p>", {"nome": "<script>x</script>"})
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_assunto_nao_escapa():
    """Assunto é texto puro: escapar mostraria `&amp;` para o destinatário."""
    out = render.aplicar_variaveis("Promo {{nome}} & cia", {"nome": "Ana"}, escapar=False)
    assert out == "Promo Ana & cia"


def test_reescreve_link_preservando_destino():
    html = '<a href="https://clienteexemplo.com.br/menu">Ver</a>'
    out = render.reescrever_links(html, "rid-1")
    assert "/track/click/rid-1?u=" in out
    assert "https%3A%2F%2Fclienteexemplo.com.br%2Fmenu" in out


def test_nao_reescreve_mailto_nem_ancora():
    html = '<a href="mailto:oi@x.com">m</a><a href="#topo">t</a>'
    assert render.reescrever_links(html, "rid-1") == html


def test_nao_reescreve_descadastro():
    """Clique em descadastro não pode contar como engajamento."""
    html = '<a href="https://crm.x/unsubscribe?r=rid-1">sair</a>'
    assert "/track/click/" not in render.reescrever_links(html, "rid-1")


def test_montar_inclui_rodape_e_pixel():
    assunto, corpo = render.montar("<p>Oi {{nome}}</p>", "Olá {{nome}}",
                                   {"nome": "Ana"}, "rid-9")
    assert assunto == "Olá Ana"
    assert "unsubscribe?r=rid-9" in corpo      # saída visível: obrigatória
    assert "track/open/rid-9.gif" in corpo     # pixel de abertura


def test_cabecalhos_de_descadastro_rfc8058():
    """Sem os DOIS cabeçalhos, Gmail e Outlook rebaixam a entregabilidade."""
    h = render.cabecalhos_unsubscribe("rid-9")
    assert h["List-Unsubscribe"].startswith("<http")
    assert h["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_variaveis_de_contato_usa_primeiro_nome_do_nome_completo():
    v = render.variaveis_de({"nome": "Ana Paula Souza", "primeiro_nome": None})
    assert v["primeiro_nome"] == "Ana"


def test_uuid_invalido_nao_derruba_o_descadastro():
    """Link truncado pelo cliente de e-mail não pode virar erro 500.

    `recipient_id` é uuid no banco: sem validar antes, o Postgres recusa o cast e
    a rota quebra justamente quando a pessoa tenta sair da lista — o que empurra
    ela para o botão "marcar como spam".
    """
    from app.routers.tracking import _uuid_valido

    assert _uuid_valido("6b1e1f6a-6f0a-4f8e-9d9b-2b6a1a4c5d6e") is True
    for ruim in ("x", "", "123", "não-é-uuid", None):
        assert _uuid_valido(ruim) is False
